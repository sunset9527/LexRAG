"""
向量索引构建器

使用Chroma构建法律文档向量索引
"""

import logging
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path

from langchain_community.embeddings import ZhipuAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from config import settings
from .chunker import LawChunk, StructuredLawChunker

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
        collection_name: str = "law_articles"
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
        
        # 初始化嵌入模型（智谱AI Embedding API）
        self.embeddings = ZhipuAIEmbeddings(
            model=embedding_model,
            api_key=settings.zhipuai_api_key,
        )
        
        # 初始化向量存储
        self.vectorstore: Optional[Chroma] = None
        self._initialize_vectorstore()
    
    def _initialize_vectorstore(self):
        """初始化向量存储"""
        try:
            self.vectorstore = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self.embeddings,
                collection_name=self.collection_name
            )
            logger.info(f"向量存储已初始化: {self.persist_directory}")
        except Exception as e:
            logger.warning(f"初始化向量存储失败: {e}，将创建新的向量存储")
            self.vectorstore = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self.embeddings,
                collection_name=self.collection_name,
                create_collection_if_not_exists=True
            )
    
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
章节：{chunk.chapter or '无'}{f' - {chunk.section}' if chunk.section else ''}
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
        }
        
        return Document(page_content=page_content, metadata=metadata)
    
    def _chunks_to_documents(self, chunks: List[LawChunk]) -> List[Document]:
        """
        将LawChunk列表转换为Document列表
        
        Args:
            chunks: 法律文档块列表
            
        Returns:
            Document列表
        """
        return [self._chunk_to_document(chunk) for chunk in chunks]
    
    def build_index(self, chunks: List[LawChunk], clear_existing: bool = False) -> int:
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

        # 分批添加（智谱AI Embedding API 限制每次最多64条，加限流延迟）
        import time
        batch_size = 32
        total = len(documents)
        for i in range(0, total, batch_size):
            batch = documents[i:i + batch_size]
            # 重试最多3次
            for attempt in range(3):
                try:
                    self.vectorstore.add_documents(batch)
                    break
                except Exception as e:
                    if attempt < 2:
                        wait = (attempt + 1) * 5
                        logger.warning(f"批次 {i//batch_size + 1} 失败({e})，{wait}s 后重试...")
                        time.sleep(wait)
                    else:
                        raise
            logger.info(f"索引进度: {min(i + batch_size, total)}/{total}")
            time.sleep(1)  # 批次间延迟，避免触发限流

        self.vectorstore.persist()

        logger.info(f"索引构建完成，共索引 {len(documents)} 个文档")
        return len(documents)
    
    def add_chunks(self, chunks: List[LawChunk]) -> int:
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
        filter_metadata: Optional[Dict[str, Any]] = None,
        include_relevance_score: bool = True
    ) -> List[Dict[str, Any]]:
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
        
        # 构建检索器
        retriever = self.vectorstore.as_retriever(
            search_kwargs={
                "k": top_k,
                "filter": filter_metadata
            }
        )
        
        # 执行检索
        docs = retriever.get_relevant_documents(query)
        
        results = []
        for i, doc in enumerate(docs):
            result = {
                "rank": i + 1,
                "content": doc.page_content,
                "metadata": doc.metadata,
            }
            if include_relevance_score and hasattr(doc, 'similarity_score'):
                result["score"] = doc.similarity_score
            results.append(result)
        
        return results
    
    def search_by_law_name(self, query: str, law_name: str, top_k: int = 5) -> List[Dict[str, Any]]:
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
    
    def search_by_chapter(self, query: str, chapter: str, top_k: int = 5) -> List[Dict[str, Any]]:
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
        self, 
        query: str, 
        start_article: str, 
        end_article: str, 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
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
                    filtered_results.append({
                        "rank": len(filtered_results) + 1,
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "score": score
                    })
                    if len(filtered_results) >= top_k:
                        break
            except ValueError:
                continue
        
        return filtered_results
    
    def get_document_by_chunk_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
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
                "metadata": results.get("metadatas", [{}])[0] if results.get("metadatas") else {}
            }
        return None
    
    def clear_index(self):
        """清除索引数据"""
        if self.vectorstore:
            self.vectorstore.delete_collection()
            self._initialize_vectorstore()
            logger.info("索引已清除")
    
    def get_collection_info(self) -> Dict[str, Any]:
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
            logger.error(f"获取集合信息失败: {e}")
            return {"error": str(e)}
    
    def rebuild_index(self, chunks: List[LawChunk]) -> int:
        """
        重建索引
        
        Args:
            chunks: 新的法律文档块列表
            
        Returns:
            索引的文档数量
        """
        self.clear_index()
        return self.build_index(chunks)
