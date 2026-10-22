"""文档解析、分块和索引的 Worker 业务编排。"""

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document_job import DocumentJob
from app.models.document_page import DocumentPage
from app.models.knowledge_base import KnowledgeBase
from app.security.uploads import validate_parsed_document_limits
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_structure_service import DocumentStructureService
from src.ingestion.rich_document_parser import ParsedDocument, ParsedPage

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """在异步 Worker 中推进单个文档任务的状态机。"""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        parsed_root: Path,
        parser: Callable[[Path], list[dict[str, Any]]],
        chunker: Callable[[list[dict[str, Any]], int, int], list[dict[str, Any]]],
        indexer_factory: Callable[[str], Any],
        relation_service_factory: Callable[[], Any] | None = None,
        max_pages: int | None = None,
        max_characters: int | None = None,
    ):
        self._session_factory = session_factory
        self._parsed_root = Path(parsed_root)
        self._parser = parser
        self._chunker = chunker
        self._indexer_factory = indexer_factory
        self._relation_service_factory = relation_service_factory
        self._max_pages = max_pages
        self._max_characters = max_characters

    def process(self, job_id: str) -> dict[str, Any]:
        """执行一次完整的解析、分块和索引。"""
        with self._session_factory() as session:
            job = self._get_job(session, job_id)
            knowledge_base = self._get_knowledge_base(session, job.knowledge_base_slug)
            job.status = "PARSING"
            job.progress = 20
            job.started_at = datetime.now()
            session.commit()
            source_path = Path(job.storage_path)
            original_filename = job.original_filename
            chunk_size = job.chunk_size
            chunk_overlap = job.chunk_overlap
            knowledge_base_slug = job.knowledge_base_slug
            collection_name = knowledge_base.collection_name

        parsed_result = self._parser(source_path)
        if isinstance(parsed_result, ParsedDocument):
            validate_parsed_document_limits(
                parsed_result,
                max_pages=self._max_pages or 2_000,
                max_characters=self._max_characters or 10_000_000,
            )
        segments, rich_pages = self._to_index_segments(parsed_result)
        parsed_text = "\n\n".join(
            str(segment.get("text", "")).strip()
            for segment in segments
            if str(segment.get("text", "")).strip()
        )
        parsed_path = self._parsed_root / knowledge_base_slug / "parsed" / f"{job_id}.txt"
        parsed_path.parent.mkdir(parents=True, exist_ok=True)
        parsed_path.write_text(parsed_text, encoding="utf-8")
        page_count = (
            len(rich_pages)
            if rich_pages is not None
            else max((int(segment.get("page", 0)) for segment in segments), default=0)
        )

        with self._session_factory() as session:
            job = self._get_job(session, job_id)
            if rich_pages is not None:
                self._replace_pages(session, job_id, rich_pages)
            job.status = "CHUNKING"
            job.progress = 45
            job.parsed_text_path = str(parsed_path.resolve())
            job.page_count = page_count or None
            job.character_count = len(parsed_text)
            session.commit()

        if rich_pages is not None:
            try:
                DocumentStructureService(self._session_factory).process(job_id)
            except Exception:
                logger.exception("文档结构化失败，不阻断索引主链路: %s", job_id)

        raw_chunks = self._chunker(segments, chunk_size, chunk_overlap)
        chunks = [
            {
                "content": chunk["content"],
                "metadata": {
                    "document_id": job_id,
                    "original_filename": original_filename,
                    "knowledge_base_slug": knowledge_base_slug,
                    "page": chunk.get("page"),
                    "paragraph": chunk.get("paragraph"),
                },
            }
            for chunk in raw_chunks
        ]

        with self._session_factory() as session:
            job = self._get_job(session, job_id)
            job.status = "INDEXING"
            job.progress = 70
            session.commit()

        indexed_count = self._indexer_factory(collection_name).upsert_chunks(chunks)

        with self._session_factory() as session:
            job = self._get_job(session, job_id)
            knowledge_base = self._get_knowledge_base(session, knowledge_base_slug)
            job.status = "READY"
            job.progress = 100
            job.chunk_count = indexed_count
            job.completed_at = datetime.now()
            ready_jobs = session.scalars(
                select(DocumentJob).where(
                    DocumentJob.knowledge_base_slug == knowledge_base_slug,
                    DocumentJob.status == "READY",
                )
            ).all()
            knowledge_base.document_count = len(ready_jobs)
            knowledge_base.chunk_count = sum(item.chunk_count or 0 for item in ready_jobs)
            knowledge_base.last_indexed_at = datetime.now()
            session.commit()
            session.refresh(job)
            result = DocumentIngestionService._serialize(job)

        if self._relation_service_factory is not None:
            try:
                self._relation_service_factory().rebuild(job_id)
            except Exception:
                logger.exception("文档关联失败，不阻断已完成的索引任务: %s", job_id)
        return result

    def mark_failed(self, job_id: str, error_message: str) -> dict[str, Any]:
        """记录 Worker 异常，供前端展示并允许用户稍后重试。"""
        with self._session_factory() as session:
            job = self._get_job(session, job_id)
            job.status = "FAILED"
            job.error_message = error_message[:4000]
            job.completed_at = datetime.now()
            session.commit()
            session.refresh(job)
            return DocumentIngestionService._serialize(job)

    @staticmethod
    def _to_index_segments(
        parsed_result: list[dict[str, Any]] | ParsedDocument,
    ) -> tuple[list[dict[str, Any]], list[ParsedPage] | None]:
        if not isinstance(parsed_result, ParsedDocument):
            return parsed_result, None
        return (
            [
                {"text": page.search_text, "page": page.page_number}
                for page in parsed_result.pages
                if page.search_text.strip()
            ],
            parsed_result.pages,
        )

    @staticmethod
    def _replace_pages(session: Session, job_id: str, pages: list[ParsedPage]) -> None:
        session.execute(delete(DocumentPage).where(DocumentPage.document_id == job_id))
        session.add_all(
            [
                DocumentPage(
                    document_id=job_id,
                    page_number=page.page_number,
                    raw_text=page.raw_text,
                    search_text=page.search_text,
                    source=page.source,
                    ocr_confidence=page.ocr_confidence,
                    tables=[
                        {
                            "rows": table.rows,
                            "bbox": list(table.bbox),
                            "method": table.method,
                        }
                        for table in page.tables
                    ],
                    header=page.header,
                    footer=page.footer,
                    parse_warnings=page.warnings,
                )
                for page in pages
            ]
        )

    @staticmethod
    def _get_job(session: Session, job_id: str) -> DocumentJob:
        job = session.get(DocumentJob, job_id)
        if job is None:
            raise ValueError(f"文档任务不存在: {job_id}")
        return job

    @staticmethod
    def _get_knowledge_base(session: Session, slug: str) -> KnowledgeBase:
        knowledge_base = session.scalar(select(KnowledgeBase).where(KnowledgeBase.slug == slug))
        if knowledge_base is None:
            raise ValueError(f"知识库不存在: {slug}")
        return knowledge_base
