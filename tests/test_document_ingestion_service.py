"""文档上传任务的服务层测试。"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.db.base import Base
import app.models.document_job  # noqa: F401
import app.models.knowledge_base  # noqa: F401
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_processing_service import DocumentProcessingService
from app.services.knowledge_base_service import KnowledgeBaseService


def build_services(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    knowledge_bases = KnowledgeBaseService(session_factory)
    knowledge_bases.create_document_library(
        name="劳动仲裁材料",
        slug="labor-arbitration-materials",
        law_area="labor",
    )
    dispatched = []
    documents = DocumentIngestionService(
        session_factory,
        uploads_root=tmp_path / "uploads",
        task_dispatcher=dispatched.append,
    )
    return documents, dispatched


def test_submit_document_persists_upload_and_queues_uploaded_job(tmp_path):
    """上传文件后应保存原件、保存配置，并仅投递任务而不在请求内解析。"""
    documents, dispatched = build_services(tmp_path)
    source = tmp_path / "劳动仲裁证据.docx"
    source.write_bytes(b"sample-word-content")

    job = documents.submit_document(
        knowledge_base_slug="labor-arbitration-materials",
        source_path=source,
        original_filename=source.name,
        chunk_size=800,
        chunk_overlap=120,
    )

    assert job["status"] == "UPLOADED"
    assert job["file_type"] == "docx"
    assert job["chunk_size"] == 800
    assert job["chunk_overlap"] == 120
    assert Path(job["storage_path"]).read_bytes() == b"sample-word-content"
    assert len(job["sha256"]) == 64
    assert dispatched == [job["id"]]


def test_submit_document_rejects_a_duplicate_ready_or_running_file(tmp_path):
    """同库同内容的文件不能重复投递，避免产生重复向量。"""
    documents, _ = build_services(tmp_path)
    source = tmp_path / "劳动仲裁证据.docx"
    source.write_bytes(b"identical-content")
    documents.submit_document(
        knowledge_base_slug="labor-arbitration-materials",
        source_path=source,
        original_filename=source.name,
        chunk_size=800,
        chunk_overlap=120,
    )

    with pytest.raises(ValueError, match="相同文件"):
        documents.submit_document(
            knowledge_base_slug="labor-arbitration-materials",
            source_path=source,
            original_filename=source.name,
            chunk_size=800,
            chunk_overlap=120,
        )


def test_process_job_marks_document_and_library_ready_after_indexing(tmp_path):
    """Worker 完成解析、分块和索引后，任务与库的统计必须同步为 READY。"""
    documents, _ = build_services(tmp_path)
    source = tmp_path / "劳动仲裁证据.docx"
    source.write_bytes(b"sample-word-content")
    job = documents.submit_document(
        knowledge_base_slug="labor-arbitration-materials",
        source_path=source,
        original_filename=source.name,
        chunk_size=800,
        chunk_overlap=120,
    )
    indexed = []
    processor = DocumentProcessingService(
        documents._session_factory,
        parsed_root=tmp_path / "uploads",
        parser=lambda _path: [{"text": "劳动者主张加班费。", "page": 1}],
        chunker=lambda _segments, _size, _overlap: [
            {"content": "劳动者主张", "page": 1},
            {"content": "主张加班费", "page": 1},
        ],
        indexer_factory=lambda collection_name: (
            type("Indexer", (), {"upsert_chunks": lambda _, chunks: indexed.append((collection_name, chunks)) or len(chunks)})()
        ),
    )

    completed = processor.process(job["id"])

    assert completed["status"] == "READY"
    assert completed["progress"] == 100
    assert completed["page_count"] == 1
    assert completed["character_count"] == len("劳动者主张加班费。")
    assert completed["chunk_count"] == 2
    assert Path(completed["parsed_text_path"]).read_text(encoding="utf-8") == "劳动者主张加班费。"
    assert indexed[0][0] == "kb_labor_arbitration_materials"
    assert indexed[0][1][0]["metadata"]["document_id"] == job["id"]
