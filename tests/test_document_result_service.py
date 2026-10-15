"""文档解析结果的只读服务测试。"""

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import app.models.document_job  # noqa: F401
import app.models.knowledge_base  # noqa: F401
from app.db.base import Base
from app.models.document_job import DocumentJob
from app.models.document_page import DocumentPage
from app.models.document_relation import DocumentRelation
from app.models.document_structure import DocumentStructure
from app.models.knowledge_base import KnowledgeBase
from app.services.document_result_service import DocumentResultService


def build_service():
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with session_factory() as session:
        session.add(
            KnowledgeBase(
                name="劳动仲裁材料",
                slug="labor-arbitration-materials",
                type="document",
                law_area="labor",
                collection_name="kb_labor_arbitration_materials",
            )
        )
        session.add_all(
            [
                DocumentJob(
                    id="document-1",
                    knowledge_base_slug="labor-arbitration-materials",
                    original_filename="劳动合同.pdf",
                    storage_path="C:/private/labor-contract.pdf",
                    file_type="pdf",
                    file_size=100,
                    sha256="a" * 64,
                    chunk_size=800,
                    chunk_overlap=120,
                ),
                DocumentJob(
                    id="document-2",
                    knowledge_base_slug="labor-arbitration-materials",
                    original_filename="无关材料.pdf",
                    storage_path="C:/private/other.pdf",
                    file_type="pdf",
                    file_size=100,
                    sha256="b" * 64,
                    chunk_size=800,
                    chunk_overlap=120,
                ),
            ]
        )
        session.add_all(
            [
                DocumentPage(
                    document_id="document-1",
                    page_number=1,
                    raw_text="第一页原文",
                    search_text="第一页原文",
                    source="text",
                    tables=[{"rows": [["岗位", "研发"]]}],
                ),
                DocumentPage(
                    document_id="document-1",
                    page_number=2,
                    raw_text="第二页原文",
                    search_text="第二页原文",
                    source="ocr",
                    ocr_confidence=0.88,
                    parse_warnings=["表格结构未经验证"],
                ),
                DocumentPage(
                    document_id="document-2",
                    page_number=1,
                    raw_text="其他文档",
                    search_text="其他文档",
                    source="text",
                ),
            ]
        )
        session.add(
            DocumentStructure(
                document_id="document-1",
                document_type="contract",
                content_json={
                    "parties": {
                        "value": "甲公司与乙员工",
                        "page_number": 1,
                        "evidence_text": "甲方：甲公司；乙方：乙员工",
                        "extraction_method": "rule",
                    }
                },
                parser_version="v2.3.1",
                status="READY",
            )
        )
        session.add(
            DocumentRelation(
                source_document_id="document-1",
                source_locator="page:1",
                target_type="law_article",
                target_id="labor-contract-law:3",
                relation_type="article_reference",
                law_article="劳动合同法第3条",
                created_by="rule",
                engine_version="v2.3.1",
            )
        )
        session.commit()
    return DocumentResultService(session_factory)


def test_result_exposes_traceable_summary_without_internal_storage_path():
    """详情返回来源与结构化结果，但不泄露服务端绝对文件路径。"""
    result = build_service().get_result("document-1")

    assert result["id"] == "document-1"
    assert result["knowledge_base_slug"] == "labor-arbitration-materials"
    assert result["page_count"] == 2
    assert result["table_count"] == 1
    assert "storage_path" not in result
    assert result["structure"]["content"]["parties"]["page_number"] == 1
    assert result["relations_count"] == 1


def test_page_listing_is_sorted_paginated_and_scoped_to_document():
    """页面列表按页码稳定分页，绝不混入其他文档页面。"""
    result = build_service().list_pages("document-1", page=2, page_size=1)

    assert result["total"] == 2
    assert result["page"] == 2
    assert result["items"] == [
        {
            "page_number": 2,
            "raw_text": "第二页原文",
            "search_text": "第二页原文",
            "source": "ocr",
            "ocr_confidence": 0.88,
            "tables": [],
            "header": None,
            "footer": None,
            "parse_warnings": ["表格结构未经验证"],
        }
    ]


def test_relation_listing_returns_only_traceable_source_document_edges():
    """关联列表应只返回当前文档的关联及其证据说明。"""
    result = build_service().list_relations("document-1")

    assert result == {
        "items": [
            {
                "source_locator": "page:1",
                "target_type": "law_article",
                "target_id": "labor-contract-law:3",
                "relation_type": "article_reference",
                "law_article": "劳动合同法第3条",
                "similarity": None,
                "evidence_text": None,
                "created_by": "rule",
                "engine_version": "v2.3.1",
            }
        ]
    }
