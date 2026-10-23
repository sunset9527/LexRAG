"""年度案例的独立 Chroma 索引器。"""

from typing import Any

from langchain_core.documents import Document

from config import settings
from src.ingestion.index_identity import (
    collection_identity_from_settings,
    get_or_create_identity_collection,
)
from src.utils.embedding_factory import create_embeddings


class AnnualCaseIndexer:
    """将结构化案例写入 ``case_annual_2025``，与法规库物理隔离。"""

    collection_name = "case_annual_2025"

    def __init__(self, *, vectorstore: Any | None = None):
        if vectorstore is not None:
            self._vectorstore = vectorstore
            return

        from langchain_community.vectorstores import Chroma
        from chromadb import PersistentClient

        embeddings = create_embeddings(
            provider=settings.embedding_provider,
            model_path=settings.local_embedding_model_path,
            local_model_id=settings.local_embedding_model_id,
            zhipuai_api_key=settings.zhipuai_api_key,
            zhipuai_model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            normalize=settings.embedding_normalize,
            index_schema_version=settings.index_schema_version,
        )
        identity = collection_identity_from_settings(settings)
        client = PersistentClient(path=settings.chroma_persist_directory)
        get_or_create_identity_collection(client, self.collection_name, identity)
        self._vectorstore = Chroma(
            collection_name=self.collection_name,
            embedding_function=embeddings,
            persist_directory=settings.chroma_persist_directory,
            client=client,
            collection_metadata=identity.collection_metadata(),
        )

    @property
    def vectorstore(self) -> Any:
        return self._vectorstore

    def upsert_cases(self, cases: list[dict[str, Any]]) -> int:
        """以稳定 ``case:<UUID>`` 写入检索文本和可过滤元数据。"""
        if not cases:
            return 0

        documents = []
        ids = []
        for case in cases:
            case_id = case["id"]
            documents.append(
                Document(
                    page_content=self._build_content(case),
                    metadata={
                        "case_id": case_id,
                        "source_id": case["source_id"],
                        "domain": case["domain"],
                        "case_cause": case["case_cause"],
                        "source_start_page": case["source_start_page"],
                        "source_end_page": case["source_end_page"],
                    },
                )
            )
            ids.append(f"case:{case_id}")
        self._vectorstore.add_documents(documents, ids=ids)
        return len(documents)

    @staticmethod
    def _build_content(case: dict[str, Any]) -> str:
        fields = (
            ("案例名称", case.get("title")),
            ("案由", case.get("case_cause")),
            ("关键事实", case.get("key_facts")),
            ("案件焦点", case.get("issues")),
            ("法院裁判理由", case.get("court_reasoning")),
            ("裁判结果", case.get("judgment_result")),
        )
        return "\n".join(f"{label}：{value}" for label, value in fields if value)
