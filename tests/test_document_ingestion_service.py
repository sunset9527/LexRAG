"""文档上传任务的服务层测试。"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import app.models.document_job  # noqa: F401
import app.models.knowledge_base  # noqa: F401
from app.db.base import Base
from app.models.document_job import DocumentJob
from app.models.document_page import DocumentPage
from app.models.document_structure import DocumentStructure
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_processing_service import DocumentProcessingService
from app.services.knowledge_base_service import KnowledgeBaseService
from src.ingestion.rich_document_parser import ExtractedTable, ParsedDocument, ParsedPage


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
    with documents._session_factory() as session:
        stored_job = session.get(DocumentJob, job["id"])
        assert stored_job is not None
        assert Path(stored_job.storage_path).read_bytes() == b"sample-word-content"
    assert len(job["sha256"]) == 64
    assert dispatched == [job["id"]]


def test_submit_document_does_not_expose_internal_storage_path(tmp_path):
    """上传响应不得向 API 使用方暴露服务器文件系统绝对路径。"""
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

    assert "storage_path" not in job
    assert "parsed_text_path" not in job


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
        indexer_factory=lambda collection_name: type(
            "Indexer",
            (),
            {
                "upsert_chunks": lambda _, chunks: (
                    indexed.append((collection_name, chunks)) or len(chunks)
                )
            },
        )(),
    )

    completed = processor.process(job["id"])

    assert completed["status"] == "READY"
    assert completed["progress"] == 100
    assert completed["page_count"] == 1
    assert completed["character_count"] == len("劳动者主张加班费。")
    assert completed["chunk_count"] == 2
    with documents._session_factory() as session:
        stored_job = session.get(DocumentJob, job["id"])
        assert stored_job is not None
        assert Path(stored_job.parsed_text_path).read_text(encoding="utf-8") == "劳动者主张加班费。"
    assert indexed[0][0] == "kb_labor_arbitration_materials"
    assert indexed[0][1][0]["metadata"]["document_id"] == job["id"]


def test_process_job_persists_rich_pages_and_chunks_only_search_text(tmp_path):
    """深度解析页应入库，页眉页脚不能污染后续向量分块。"""
    documents, _ = build_services(tmp_path)
    source = tmp_path / "劳动合同.pdf"
    source.write_bytes(b"sample-pdf-content")
    job = documents.submit_document(
        knowledge_base_slug="labor-arbitration-materials",
        source_path=source,
        original_filename=source.name,
        chunk_size=800,
        chunk_overlap=120,
    )
    captured_segments = []
    indexed = []
    processor = DocumentProcessingService(
        documents._session_factory,
        parsed_root=tmp_path / "uploads",
        parser=lambda _path: ParsedDocument(
            pages=[
                ParsedPage(
                    page_number=1,
                    raw_text="劳动合同\n劳动者主张加班费。\n第 1 页",
                    search_text="劳动者主张加班费。",
                    source="ocr",
                    ocr_confidence=0.93,
                    tables=[
                        ExtractedTable(
                            rows=[["岗位", "研发工程师"]],
                            bbox=(0.0, 0.0, 1.0, 1.0),
                        )
                    ],
                    header="劳动合同",
                    footer="第 1 页",
                    warnings=["表格结构未经验证"],
                )
            ]
        ),
        chunker=lambda segments, _size, _overlap: (
            captured_segments.extend(segments)
            or [{"content": segments[0]["text"], "page": segments[0]["page"]}]
        ),
        indexer_factory=lambda collection_name: type(
            "Indexer",
            (),
            {
                "upsert_chunks": lambda _, chunks: (
                    indexed.append((collection_name, chunks)) or len(chunks)
                )
            },
        )(),
    )

    completed = processor.process(job["id"])

    assert completed["status"] == "READY"
    assert captured_segments == [{"text": "劳动者主张加班费。", "page": 1}]
    assert indexed[0][1][0]["content"] == "劳动者主张加班费。"
    with documents._session_factory() as session:
        page = session.query(DocumentPage).filter_by(document_id=job["id"], page_number=1).one()
        assert page.source == "ocr"
        assert page.ocr_confidence == 0.93
        assert page.tables == [
            {"rows": [["岗位", "研发工程师"]], "bbox": [0.0, 0.0, 1.0, 1.0], "method": "pymupdf"}
        ]
        assert page.header == "劳动合同"
        assert page.footer == "第 1 页"
        assert page.parse_warnings == ["表格结构未经验证"]


def test_process_job_writes_rule_structure_without_blocking_chunking(tmp_path):
    """页面持久化后应触发结构化，但它不是文档索引主链路的阻塞点。"""
    documents, _ = build_services(tmp_path)
    source = tmp_path / "劳动合同.pdf"
    source.write_bytes(b"sample-pdf-content")
    job = documents.submit_document(
        knowledge_base_slug="labor-arbitration-materials",
        source_path=source,
        original_filename=source.name,
        chunk_size=800,
        chunk_overlap=120,
    )
    processor = DocumentProcessingService(
        documents._session_factory,
        parsed_root=tmp_path / "uploads",
        parser=lambda _path: ParsedDocument(
            pages=[
                ParsedPage(
                    page_number=1,
                    raw_text="甲方：甲公司\n乙方：张三\n第一条 工作内容",
                    search_text="甲方：甲公司\n乙方：张三\n第一条 工作内容",
                    source="text",
                    ocr_confidence=None,
                    tables=[],
                    header=None,
                    footer=None,
                    warnings=[],
                )
            ]
        ),
        chunker=lambda segments, _size, _overlap: [
            {"content": segments[0]["text"], "page": segments[0]["page"]}
        ],
        indexer_factory=lambda _collection_name: type(
            "Indexer", (), {"upsert_chunks": lambda _, chunks: len(chunks)}
        )(),
    )

    completed = processor.process(job["id"])

    assert completed["status"] == "READY"
    with documents._session_factory() as session:
        page = session.query(DocumentPage).filter_by(document_id=job["id"], page_number=1).one()
        assert page.search_text == "甲方：甲公司\n乙方：张三\n第一条 工作内容"
        structure = session.query(DocumentStructure).filter_by(document_id=job["id"]).one()
        assert structure.status == "READY"
        assert structure.document_type == "contract"
        assert structure.content_json["parties"]["value"] == "甲方：甲公司\n乙方：张三"
        assert structure.content_json["parties"]["page_number"] == 1


def test_process_job_triggers_optional_relation_rebuild_after_ready(tmp_path):
    """关系建立位于 READY 后，异常或缺省关系服务不能阻塞索引主链路。"""
    documents, _ = build_services(tmp_path)
    source = tmp_path / "材料.pdf"
    source.write_bytes(b"sample-pdf-content")
    job = documents.submit_document(
        knowledge_base_slug="labor-arbitration-materials",
        source_path=source,
        original_filename=source.name,
        chunk_size=800,
        chunk_overlap=120,
    )
    relation_calls = []

    class FakeRelationService:
        def rebuild(self, document_id):
            relation_calls.append(document_id)

    processor = DocumentProcessingService(
        documents._session_factory,
        parsed_root=tmp_path / "uploads",
        parser=lambda _path: [{"text": "劳动者主张加班费。", "page": 1}],
        chunker=lambda segments, _size, _overlap: [
            {"content": segments[0]["text"], "page": segments[0]["page"]}
        ],
        indexer_factory=lambda _collection_name: type(
            "Indexer", (), {"upsert_chunks": lambda _, chunks: len(chunks)}
        )(),
        relation_service_factory=lambda: FakeRelationService(),
    )

    completed = processor.process(job["id"])

    assert completed["status"] == "READY"
    assert relation_calls == [job["id"]]


def test_submit_documents_returns_independent_batch_outcomes(tmp_path):
    """批量中格式非法或重复的单文件不能回滚其他已创建任务。"""
    documents, dispatched = build_services(tmp_path)
    valid = tmp_path / "材料.pdf"
    invalid = tmp_path / "说明.txt"
    valid.write_bytes(b"valid")
    invalid.write_text("invalid", encoding="utf-8")

    result = documents.submit_documents(
        knowledge_base_slug="labor-arbitration-materials",
        submissions=[
            {"source_path": valid, "original_filename": valid.name},
            {"source_path": invalid, "original_filename": invalid.name},
        ],
        chunk_size=800,
        chunk_overlap=120,
    )

    assert result[0]["original_filename"] == "材料.pdf"
    assert result[0]["job"]["status"] == "UPLOADED"
    assert result[1] == {"original_filename": "说明.txt", "error": "仅支持 PDF 或 DOCX 文件"}
    assert len(dispatched) == 1
