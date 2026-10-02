"""v2.3 页面、结构化结果与关联边的数据模型测试。"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.db.base import Base
import app.models.document_job  # noqa: F401
import app.models.knowledge_base  # noqa: F401
from app.models.document_page import DocumentPage
from app.models.document_relation import DocumentRelation
from app.models.document_structure import DocumentStructure
from app.models.document_job import DocumentJob
from app.models.knowledge_base import KnowledgeBase


def build_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(
        KnowledgeBase(
            name="劳动仲裁材料",
            slug="labor-arbitration-materials",
            type="document",
            law_area="labor",
            collection_name="kb_labor_arbitration_materials",
        )
    )
    session.add(
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
        )
    )
    session.commit()
    return session


def test_document_page_allows_only_one_result_per_document_page():
    """同一文件同一页只能有一份可追溯的解析结果。"""
    session = build_session()
    session.add(
        DocumentPage(
            document_id="document-1",
            page_number=1,
            raw_text="第一页原文",
            search_text="第一页原文",
            source="text",
        )
    )
    session.commit()

    session.add(
        DocumentPage(
            document_id="document-1",
            page_number=1,
            raw_text="重复页",
            search_text="重复页",
            source="text",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_document_has_at_most_one_current_structure_result():
    """一份文档只能有一份当前结构化结果，避免详情接口返回冲突版本。"""
    session = build_session()
    session.add(
        DocumentStructure(
            document_id="document-1",
            document_type="contract",
            content_json={"clauses": []},
            parser_version="v2.3.1",
            status="READY",
        )
    )
    session.commit()

    session.add(
        DocumentStructure(
            document_id="document-1",
            document_type="contract",
            content_json={"clauses": []},
            parser_version="v2.3.1",
            status="READY",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_document_relation_requires_an_explainable_evidence_signal():
    """关联边没有法条号、相似度或原文证据时不得写入。"""
    session = build_session()
    session.add(
        DocumentRelation(
            source_document_id="document-1",
            source_locator="page:1",
            target_type="law_article",
            target_id="civil-code:509",
            relation_type="article_reference",
            created_by="rule",
            engine_version="v2.3.1",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
