"""场景任务的无状态运行时依赖。

这里不接收也不保存用户 API Key：Celery worker 只做受控规则、检索和证据校验。
需要模型润色的合同建议仍由请求线程在已验证证据后生成。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.db import session as db_session
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.scenario_service import ScenarioService
from config import settings
from src.ingestion.indexer import LawIndexer
from src.retrieval.law_retriever import LawRetriever


def create_runtime_scenario_service(
    *,
    advice_generator: Callable[[str, list[str]], str] | None = None,
    case_provider: Callable[[str], list[dict[str, Any]]] | None = None,
) -> ScenarioService:
    """构造可在 API 进程和 Celery worker 共用的场景服务。"""
    if db_session.SessionLocal is None:
        raise RuntimeError("场景服务数据库未初始化")
    knowledge_base_service = KnowledgeBaseService(db_session.SessionLocal)

    def evidence_provider(query: str, knowledge_base_slug: str) -> list[dict[str, Any]]:
        try:
            collection_name = knowledge_base_service.get_ready_collection_name(knowledge_base_slug)
            indexer = LawIndexer(
                persist_directory=settings.chroma_persist_directory,
                embedding_model=settings.embedding_model,
                collection_name=collection_name,
            )
            retriever = LawRetriever(
                vectorstore=indexer.vectorstore,
                api_key=None,
                base_url=settings.deepseek_base_url,
                model=settings.deepseek_model,
            )
            rows = retriever.retrieve(query, top_k=3) or []
        except Exception:
            return []
        return [
            {
                "source_id": str(getattr(row, "chunk_id", "") or getattr(row, "article_id", "")),
                "law_name": str(getattr(row, "law_name", "")),
                "article_id": str(
                    getattr(row, "article_number", "") or getattr(row, "article_id", "")
                ),
                "content": str(getattr(row, "full_content", "") or getattr(row, "content", "")),
                "score": float(getattr(row, "score", 0) or 0),
                "knowledge_base_slug": knowledge_base_slug,
            }
            for row in rows
        ]

    return ScenarioService(
        db_session.SessionLocal,
        evidence_provider=evidence_provider,
        advice_generator=advice_generator,
        case_provider=case_provider,
    )
