"""自定义文档 chunk 的 Chroma 索引器。"""

from typing import Any

from langchain_core.documents import Document

from config import settings
from src.utils.embedding_factory import create_embeddings


class DocumentIndexer:
    """向指定知识库 collection 写入带稳定 ID 的文档 chunk。"""

    def __init__(self, collection_name: str):
        from langchain_community.vectorstores import Chroma

        embeddings = create_embeddings(
            model_path=settings.local_embedding_model_path,
            zhipuai_api_key=settings.zhipuai_api_key,
            zhipuai_model=settings.embedding_model,
        )
        self._vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=settings.chroma_persist_directory,
        )

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """以 document_id + 序号作为稳定 ID，重试不会产生重复向量。"""
        if not chunks:
            return 0
        documents = []
        ids = []
        for index, chunk in enumerate(chunks):
            metadata = {
                key: value for key, value in chunk.get("metadata", {}).items() if value is not None
            }
            document_id = metadata["document_id"]
            documents.append(Document(page_content=chunk["content"], metadata=metadata))
            ids.append(f"{document_id}:{index}")
        self._vectorstore.add_documents(documents, ids=ids)
        return len(documents)
