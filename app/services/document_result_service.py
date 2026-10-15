"""文档深度解析结果的只读查询服务。"""

from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document_job import DocumentJob
from app.models.document_page import DocumentPage
from app.models.document_relation import DocumentRelation
from app.models.document_structure import DocumentStructure


class DocumentResultService:
    """集中序列化可展示结果，避免 API 暴露内部存储字段。"""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def get_result(self, document_id: str) -> dict[str, Any]:
        """返回单份文档的概览及当前结构化状态。"""
        with self._session_factory() as session:
            job = self._get_job(session, document_id)
            pages = session.scalars(
                select(DocumentPage).where(DocumentPage.document_id == document_id)
            ).all()
            structure = session.scalar(
                select(DocumentStructure).where(DocumentStructure.document_id == document_id)
            )
            relations_count = session.scalar(
                select(func.count(DocumentRelation.id)).where(
                    DocumentRelation.source_document_id == document_id
                )
            )
            return {
                "id": job.id,
                "knowledge_base_slug": job.knowledge_base_slug,
                "original_filename": job.original_filename,
                "file_type": job.file_type,
                "status": job.status,
                "page_count": len(pages),
                "table_count": sum(len(item.tables or []) for item in pages),
                "relations_count": relations_count or 0,
                "structure": self._serialize_structure(structure),
            }

    def get_knowledge_base_slug(self, document_id: str) -> str:
        """仅返回归属库 slug，供 API 在读取正文前执行组织授权。"""
        with self._session_factory() as session:
            return self._get_job(session, document_id).knowledge_base_slug

    def list_pages(self, document_id: str, *, page: int, page_size: int) -> dict[str, Any]:
        """按页码稳定分页读取一份文档的逐页解析结果。"""
        if page < 1:
            raise ValueError("页码必须大于等于 1")
        if not 1 <= page_size <= 100:
            raise ValueError("每页数量必须在 1 到 100 之间")
        with self._session_factory() as session:
            self._get_job(session, document_id)
            total = session.scalar(
                select(func.count(DocumentPage.id)).where(DocumentPage.document_id == document_id)
            )
            pages = session.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return {
                "total": total or 0,
                "page": page,
                "page_size": page_size,
                "items": [self._serialize_page(item) for item in pages],
            }

    def list_relations(self, document_id: str) -> dict[str, Any]:
        """返回当前文档的可解释关联边，不混入其他文档。"""
        with self._session_factory() as session:
            self._get_job(session, document_id)
            relations = session.scalars(
                select(DocumentRelation)
                .where(DocumentRelation.source_document_id == document_id)
                .order_by(DocumentRelation.id)
            ).all()
            return {"items": [self._serialize_relation(item) for item in relations]}

    @staticmethod
    def _get_job(session: Session, document_id: str) -> DocumentJob:
        job = session.get(DocumentJob, document_id)
        if job is None:
            raise ValueError(f"文档任务不存在: {document_id}")
        return job

    @staticmethod
    def _serialize_page(page: DocumentPage) -> dict[str, Any]:
        return {
            "page_number": page.page_number,
            "raw_text": page.raw_text,
            "search_text": page.search_text,
            "source": page.source,
            "ocr_confidence": page.ocr_confidence,
            "tables": page.tables or [],
            "header": page.header,
            "footer": page.footer,
            "parse_warnings": page.parse_warnings or [],
        }

    @staticmethod
    def _serialize_structure(structure: DocumentStructure | None) -> dict[str, Any] | None:
        if structure is None:
            return None
        return {
            "document_type": structure.document_type,
            "content": structure.content_json,
            "parser_version": structure.parser_version,
            "status": structure.status,
            "error_message": structure.error_message,
        }

    @staticmethod
    def _serialize_relation(relation: DocumentRelation) -> dict[str, Any]:
        return {
            "source_locator": relation.source_locator,
            "target_type": relation.target_type,
            "target_id": relation.target_id,
            "relation_type": relation.relation_type,
            "law_article": relation.law_article,
            "similarity": relation.similarity,
            "evidence_text": relation.evidence_text,
            "created_by": relation.created_by,
            "engine_version": relation.engine_version,
        }
