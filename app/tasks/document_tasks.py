"""Celery task entrypoint for uploaded documents."""

from app.db import session as db_session
from app.db.session import init_db
from app.services.document_processing_service import DocumentProcessingService
from app.tasks.celery_app import celery_app
from config import settings
from src.ingestion.document_chunker import DocumentChunker
from src.ingestion.document_indexer import DocumentIndexer
from src.ingestion.document_parser import parse_document


@celery_app.task(name="lexrag.process_document")
def process_document_task(job_id: str) -> dict:
    """在独立 Worker 进程中处理一个已上传的文档。"""
    if db_session.SessionLocal is None:
        init_db()
    processor = DocumentProcessingService(
        db_session.SessionLocal,
        parsed_root=settings.document_uploads_path,
        parser=parse_document,
        chunker=DocumentChunker().chunk_segments,
        indexer_factory=DocumentIndexer,
    )
    try:
        return processor.process(job_id)
    except Exception as exc:
        processor.mark_failed(job_id, str(exc))
        raise
