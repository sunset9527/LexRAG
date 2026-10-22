"""Celery task entrypoint for uploaded documents."""

from app.db import session as db_session
from app.db.session import init_db
from app.services.document_processing_service import DocumentProcessingService
from app.services.document_relation_service import DocumentRelationService
from app.services.law_relation_lookup import build_lazy_law_lookup
from app.tasks.celery_app import celery_app
from config import settings
from src.ingestion.document_chunker import DocumentChunker
from src.ingestion.document_indexer import DocumentIndexer
from src.ingestion.indexer import LawIndexer
from src.ingestion.rich_document_parser import parse_document_details


@celery_app.task(
    name="lexrag.process_document",
    soft_time_limit=settings.document_task_soft_time_limit_seconds,
    time_limit=settings.document_task_time_limit_seconds,
)
def process_document_task(job_id: str) -> dict:
    """在独立 Worker 进程中处理一个已上传的文档。"""
    if db_session.SessionLocal is None:
        init_db()
    processor = DocumentProcessingService(
        db_session.SessionLocal,
        parsed_root=settings.document_uploads_path,
        parser=parse_document_details,
        chunker=DocumentChunker().chunk_segments,
        indexer_factory=DocumentIndexer,
        relation_service_factory=lambda: DocumentRelationService(
            db_session.SessionLocal,
            law_lookup=build_lazy_law_lookup(
                lambda: LawIndexer(
                    persist_directory=settings.chroma_persist_directory,
                    embedding_model=settings.embedding_model,
                    collection_name=settings.law_collection_name,
                )
            ),
        ),
        max_pages=settings.upload_max_pdf_pages,
        max_characters=settings.upload_max_extracted_characters,
    )
    try:
        return processor.process(job_id)
    except Exception:
        processor.mark_failed(job_id, "DOCUMENT_PROCESSING_FAILED")
        raise RuntimeError("DOCUMENT_PROCESSING_FAILED") from None
