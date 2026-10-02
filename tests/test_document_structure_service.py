"""文档结构化结果持久化与降级测试。"""

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.db.base import Base
import app.models.document_job  # noqa: F401
import app.models.knowledge_base  # noqa: F401
from app.models.document_job import DocumentJob
from app.models.document_page import DocumentPage
from app.models.document_structure import DocumentStructure
from app.models.knowledge_base import KnowledgeBase
from app.services.document_structure_service import DocumentStructureService


def build_session_factory():
    engine = create_engine("sqlite:///:memory:")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as session:
        session.add(
            KnowledgeBase(
                name="合同材料",
                slug="contracts",
                type="document",
                law_area="civil",
                collection_name="kb_contracts",
            )
        )
        session.add(
            DocumentJob(
                id="contract-1",
                knowledge_base_slug="contracts",
                original_filename="合同.pdf",
                storage_path="C:/private/contract.pdf",
                file_type="pdf",
                file_size=100,
                sha256="a" * 64,
                chunk_size=800,
                chunk_overlap=120,
            )
        )
        session.add(
            DocumentPage(
                document_id="contract-1",
                page_number=1,
                raw_text="履行时间为签约后7日\n第一条 当事人\n甲方：甲公司\n乙方：张三\n第二条 期限\n本合同期限为一年。",
                search_text="履行时间为签约后7日\n第一条 当事人\n甲方：甲公司\n乙方：张三\n第二条 期限\n本合同期限为一年。",
                source="text",
            )
        )
        session.commit()
    return factory


def test_structure_service_persists_rule_result_with_page_evidence():
    """服务从页面读取文本，持久化单一、可回指的合同结构化结果。"""
    factory = build_session_factory()

    result = DocumentStructureService(factory).process("contract-1")

    assert result["status"] == "READY"
    assert result["document_type"] == "contract"
    assert result["content"]["parties"]["page_number"] == 1
    with factory() as session:
        stored = session.query(DocumentStructure).filter_by(document_id="contract-1").one()
        assert stored.parser_version == "v2.3.2-rule"


def test_structure_service_records_failure_without_changing_document_job_status():
    """结构化异常必须可见，但不能把已入库文档主任务改成失败。"""
    factory = build_session_factory()

    result = DocumentStructureService(factory, parser=lambda _pages: (_ for _ in ()).throw(ValueError("解析器异常"))).process("contract-1")

    assert result["status"] == "FAILED"
    assert "解析器异常" in result["error_message"]
    with factory() as session:
        assert session.get(DocumentJob, "contract-1").status == "UPLOADED"


def test_structure_service_only_persists_llm_candidates_with_page_evidence():
    """LLM 候选默认不能覆盖规则结果，且没有原文依据的字段必须被丢弃。"""
    factory = build_session_factory()
    supplementer = lambda _parsed: [
        {
            "field": "performance",
            "value": "签约后7日",
            "page_number": 1,
            "evidence_text": "履行时间为签约后7日",
            "confidence": 0.8,
        },
        {
            "field": "remuneration",
            "value": "每月十万元",
            "page_number": 1,
            "evidence_text": "模型推断",
        },
    ]

    result = DocumentStructureService(factory, supplementer=supplementer).process("contract-1")

    assert result["status"] == "READY"
    assert result["content"]["performance"]["value"] == "签约后7日"
    assert result["content"]["performance"]["extraction_method"] == "llm_verified"
    assert result["content"]["remuneration"] is None
    assert result["parser_version"] == "v2.3.2-rule+llm-verified"


def test_structure_service_keeps_rule_result_when_llm_supplementer_fails():
    """可选 LLM 失败时只降级，不能把规则解析改成失败。"""
    factory = build_session_factory()

    result = DocumentStructureService(
        factory,
        supplementer=lambda _parsed: (_ for _ in ()).throw(RuntimeError("LLM 不可用")),
    ).process("contract-1")

    assert result["status"] == "READY"
    assert result["parser_version"] == "v2.3.2-rule"
    assert result["content"]["parties"]["extraction_method"] == "rule"
