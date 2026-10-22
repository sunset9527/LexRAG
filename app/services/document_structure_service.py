"""将已解析页面保存为可回指的文档结构化结果。"""

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document_job import DocumentJob
from app.models.document_page import DocumentPage
from app.models.document_structure import DocumentStructure
from src.ingestion.legal_document_structure import (
    StructuredDocument,
    apply_verified_supplement,
    structure_document,
)

logger = logging.getLogger(__name__)


class DocumentStructureService:
    """规则结构化的持久化边界；失败不影响文档入库主状态。"""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        parser: Callable[[list[tuple[int, str]]], StructuredDocument] = structure_document,
        supplementer: Callable[[StructuredDocument], list[dict[str, Any]]] | None = None,
    ):
        self._session_factory = session_factory
        self._parser = parser
        self._supplementer = supplementer

    def process(self, document_id: str) -> dict[str, Any]:
        """读取已持久化页面，写入或更新该文档唯一的结构化记录。"""
        with self._session_factory() as session:
            self._get_job(session, document_id)
            pages = session.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            ).all()
            source_pages = [
                (page.page_number, page.search_text) for page in pages if page.search_text
            ]
            try:
                parsed = self._parser(source_pages)
                if self._supplementer is not None:
                    try:
                        parsed = apply_verified_supplement(parsed, self._supplementer(parsed))
                    except Exception:
                        logger.exception("文档结构化补充失败，保留规则结果: %s", document_id)
                structure = self._upsert(
                    session,
                    document_id=document_id,
                    document_type=parsed.document_type,
                    content=parsed.content,
                    parser_version=parsed.parser_version,
                    status="READY",
                    error_message=None,
                )
            except Exception as exc:
                structure = self._upsert(
                    session,
                    document_id=document_id,
                    document_type="general",
                    content={},
                    parser_version="v2.3.2-rule",
                    status="FAILED",
                    error_message=f"STRUCTURE_FAILED:{type(exc).__name__}",
                )
            session.commit()
            session.refresh(structure)
            return self._serialize(structure)

    @staticmethod
    def _get_job(session: Session, document_id: str) -> DocumentJob:
        job = session.get(DocumentJob, document_id)
        if job is None:
            raise ValueError(f"文档任务不存在: {document_id}")
        return job

    @staticmethod
    def _upsert(
        session: Session,
        *,
        document_id: str,
        document_type: str,
        content: dict,
        parser_version: str,
        status: str,
        error_message: str | None,
    ) -> DocumentStructure:
        structure = session.scalar(
            select(DocumentStructure).where(DocumentStructure.document_id == document_id)
        )
        if structure is None:
            structure = DocumentStructure(document_id=document_id)
            session.add(structure)
        structure.document_type = document_type
        structure.content_json = content
        structure.parser_version = parser_version
        structure.status = status
        structure.error_message = error_message
        return structure

    @staticmethod
    def _serialize(structure: DocumentStructure) -> dict[str, Any]:
        return {
            "document_type": structure.document_type,
            "content": structure.content_json,
            "parser_version": structure.parser_version,
            "status": structure.status,
            "error_message": structure.error_message,
        }
