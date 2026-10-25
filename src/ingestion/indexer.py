"""
向量索引构建器

使用Chroma构建法律文档向量索引
"""

import logging
from collections.abc import Mapping
from typing import Any

from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from config import settings

from ..utils.embedding_factory import create_embeddings
from .chunker import LawChunk
from .index_identity import collection_identity_from_settings, get_or_create_identity_collection

logger = logging.getLogger(__name__)


class LawIndexer:
    """
    法律文档向量索引构建器

    使用Chroma向量数据库构建法律文档索引
    支持：
    - 批量构建索引
    - 增量添加
    - 元数据过滤检索
    - 持久化存储
    """

    def __init__(
        self,
        persist_directory: str,
        embedding_model: str = "embedding-3",
        collection_name: str = "law_articles",
        source_hash: str | None = None,
        provenance_metadata: Mapping[str, str] | None = None,
    ):
        """
        初始化索引器

        Args:
            persist_directory: 持久化存储目录
            embedding_model: 嵌入模型名称
            collection_name: 集合名称
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.source_hash = source_hash
        self.provenance_metadata = dict(provenance_metadata or {})

        self.index_identity = collection_identity_from_settings(
            settings, zhipu_model=embedding_model
        )
        self.embeddings = create_embeddings(
            provider=settings.embedding_provider,
            model_path=settings.local_embedding_model_path,
            local_model_id=settings.local_embedding_model_id,
            zhipuai_api_key=settings.zhipuai_api_key,
            zhipuai_model=embedding_model,
            dimensions=settings.embedding_dimensions,
            normalize=settings.embedding_normalize,
            index_schema_version=settings.index_schema_version,
        )

        # 初始化向量存储
        self.vectorstore: Chroma | None = None
        self._initialize_vectorstore()

    def _initialize_vectorstore(self):
        """初始化向量存储"""
        import os

        # 确保持久化目录存在且有正确权限
        os.makedirs(self.persist_directory, exist_ok=True)

        from chromadb import PersistentClient

        client = PersistentClient(path=self.persist_directory)
        extra_metadata = (
            {"lexrag_statute_source_sha256": self.source_hash} if self.source_hash is not None else None
        )
        get_or_create_identity_collection(
            client,
            self.collection_name,
            self.index_identity,
            additional_metadata=extra_metadata,
        )
        self.vectorstore = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
            collection_name=self.collection_name,
            client=client,
            collection_metadata={
                **self.index_identity.collection_metadata(),
                **(extra_metadata or {}),
            },
        )
        logger.info(f"向量存储已初始化: {self.persist_directory}")

    def _chunk_to_document(self, chunk: LawChunk) -> Document:
        """
        将LawChunk转换为LangChain Document

        Args:
            chunk: 法律文档块

        Returns:
            LangChain Document对象
        """
        # 构建页面内容
        page_content = f"""【{chunk.article_id}】
章节：{chunk.chapter or "无"}{f" - {chunk.section}" if chunk.section else ""}
条文内容：{chunk.content}

【完整法条上下文】
{chunk.full_article_content}
"""

        # 构建元数据
        metadata = {
            "chunk_id": chunk.chunk_id,
            "chunk_type": chunk.chunk_type,
            "article_id": chunk.article_id,
            "article_number": chunk.article_number,
            "law_name": chunk.law_name,
            "chapter": chunk.chapter or "",
            "section": chunk.section or "",
            "effective_date": chunk.effective_date or "",
            "latest_amendment": chunk.latest_amendment or "",
            "version": chunk.version,
            "referenced_articles": str(chunk.metadata.get("referenced_articles", [])),
            **getattr(self, "provenance_metadata", {}),
        }

        return Document(page_content=page_content, metadata=metadata)

    def _chunks_to_documents(self, chunks: list[LawChunk]) -> list[Document]:
        """
        将LawChunk列表转换为Document列表

        Args:
            chunks: 法律文档块列表

        Returns:
            Document列表
        """
        return [self._chunk_to_document(chunk) for chunk in chunks]

    def build_index(self, chunks: list[LawChunk], clear_existing: bool = False) -> int:
        """
        构建向量索引

        Args:
            chunks: 法律文档块列表
            clear_existing: 是否清除现有数据

        Returns:
            索引的文档数量
        """
        if not chunks:
            logger.warning("没有文档块需要索引")
            return 0

        if clear_existing:
            self.clear_index()

        documents = self._chunks_to_documents(chunks)

        if self.vectorstore is None:
            self._initialize_vectorstore()

        # 云端 embedding 受 QPS 限流；本地 BGE-M3 不应沿用该等待策略。
        import time

        is_local_embedding = settings.embedding_provider == "local"
        # BGE-M3 is memory hungry on CPU.  Keep local batches modest so a full
        # statute rebuild does not get terminated by Windows at a batch boundary.
        batch_size = 8 if is_local_embedding else 4
        total = len(documents)
        for i in range(0, total, batch_size):
            batch = documents[i : i + batch_size]
            # 重试最多5次，逐次增加等待
            for attempt in range(5):
                try:
                    self.vectorstore.add_documents(batch)
                    break
                except Exception as e:
                    if attempt < 4:
                        wait = (attempt + 1) * 8  # 8s, 16s, 24s, 32s
                        logger.warning(
                            "批次 %s 失败，%s 秒后重试 error_type=%s",
                            i // batch_size + 1,
                            wait,
                            type(e).__name__,
                        )
                        time.sleep(wait)
                    else:
                        raise
            logger.info(f"索引进度: {min(i + batch_size, total)}/{total}")
            if not is_local_embedding:
                time.sleep(3)  # 云端限流：确保不超过 QPS 限制

        self.vectorstore.persist()

        logger.info(f"索引构建完成，共索引 {len(documents)} 个文档")
        return len(documents)

    def add_chunks(self, chunks: list[LawChunk]) -> int:
        """
        增量添加文档块

        Args:
            chunks: 新的法律文档块列表

        Returns:
            添加的文档数量
        """
        return self.build_index(chunks, clear_existing=False)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
        include_relevance_score: bool = True,
    ) -> list[dict[str, Any]]:
        """
        检索相似文档

        Args:
            query: 查询文本
            top_k: 返回的top_k结果
            filter_metadata: 元数据过滤条件
            include_relevance_score: 是否包含相关性分数

        Returns:
            检索结果列表
        """
        if self.vectorstore is None:
            logger.error("向量存储未初始化")
            return []

        # 执行检索（兼容新版 LangChain：similarity_search_with_relevance_scores 返回 (doc, score)）
        docs_with_scores = self.vectorstore.similarity_search_with_relevance_scores(
            query,
            k=top_k,
            filter=filter_metadata,
        )

        results = []
        for i, (doc, score) in enumerate(docs_with_scores):
            result = {
                "rank": i + 1,
                "content": doc.page_content,
                "metadata": doc.metadata,
            }
            if include_relevance_score:
                result["score"] = float(score)
            results.append(result)

        return results

    def search_by_law_name(self, query: str, law_name: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        按法律名称过滤检索

        Args:
            query: 查询文本
            law_name: 法律名称
            top_k: 返回的top_k结果

        Returns:
            检索结果列表
        """
        return self.search(query, top_k, filter_metadata={"law_name": law_name})

    def search_by_chapter(self, query: str, chapter: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        按章节过滤检索

        Args:
            query: 查询文本
            chapter: 章节名称
            top_k: 返回的top_k结果

        Returns:
            检索结果列表
        """
        return self.search(query, top_k, filter_metadata={"chapter": chapter})

    def search_by_article_range(
        self, query: str, start_article: str, end_article: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """
        按法条范围过滤检索

        Args:
            query: 查询文本
            start_article: 起始条号
            end_article: 结束条号
            top_k: 返回的top_k结果

        Returns:
            检索结果列表
        """
        # 转换为数字进行比较
        try:
            start_num = int(start_article)
            end_num = int(end_article)
        except ValueError:
            logger.error(f"法条编号格式错误: {start_article}, {end_article}")
            return []

        if self.vectorstore is None:
            return []

        # 获取所有文档并手动过滤
        results = self.vectorstore.similarity_search_with_score(query, k=top_k * 3)

        filtered_results = []
        for doc, score in results:
            article_num_str = doc.metadata.get("article_number", "0")
            try:
                article_num = int(article_num_str)
                if start_num <= article_num <= end_num:
                    filtered_results.append(
                        {
                            "rank": len(filtered_results) + 1,
                            "content": doc.page_content,
                            "metadata": doc.metadata,
                            "score": score,
                        }
                    )
                    if len(filtered_results) >= top_k:
                        break
            except ValueError:
                continue

        return filtered_results

    def get_document_by_chunk_id(self, chunk_id: str) -> dict[str, Any] | None:
        """
        根据chunk_id获取文档

        Args:
            chunk_id: chunk标识

        Returns:
            文档信息
        """
        if self.vectorstore is None:
            return None

        results = self.vectorstore.get(where={"chunk_id": chunk_id})
        if results and results.get("documents"):
            return {
                "content": results["documents"][0],
                "metadata": results.get("metadatas", [{}])[0] if results.get("metadatas") else {},
            }
        return None

    def clear_index(self):
        """清除索引数据"""
        if self.vectorstore:
            self.vectorstore.delete_collection()
            self._initialize_vectorstore()
            logger.info("索引已清除")

    def get_collection_info(self) -> dict[str, Any]:
        """获取集合信息"""
        if self.vectorstore is None:
            return {"error": "向量存储未初始化"}

        try:
            collection = self.vectorstore._collection
            count = collection.count()
            return {
                "name": self.collection_name,
                "document_count": count,
                "persist_directory": self.persist_directory,
            }
        except Exception as e:
            logger.error("获取集合信息失败 error_type=%s", type(e).__name__)
            return {"error": str(e)}

    def rebuild_index(self, chunks: list[LawChunk]) -> int:
        """
        重建索引

        Args:
            chunks: 新的法律文档块列表

        Returns:
            索引的文档数量
        """
        self.clear_index()
        return self.build_index(chunks)
