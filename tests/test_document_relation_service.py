"""跨文档关联的证据、隔离与幂等性测试。"""

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
from app.models.knowledge_base import KnowledgeBase
from app.services.document_relation_service import DocumentRelationService


def build_session_factory():
    engine = create_engine("sqlite:///:memory:")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as session:
        session.add_all(
            [
                KnowledgeBase(
                    name="甲库",
                    slug="library-a",
                    type="document",
                    law_area="civil",
                    collection_name="kb_a",
                ),
                KnowledgeBase(
                    name="乙库",
                    slug="library-b",
                    type="document",
                    law_area="civil",
                    collection_name="kb_b",
                ),
                DocumentJob(
                    id="source",
                    knowledge_base_slug="library-a",
                    original_filename="合同.pdf",
                    storage_path="C:/source.pdf",
                    file_type="pdf",
                    file_size=1,
                    sha256="a" * 64,
                    chunk_size=800,
                    chunk_overlap=120,
                ),
                DocumentJob(
                    id="peer",
                    knowledge_base_slug="library-a",
                    original_filename="同库.pdf",
                    storage_path="C:/peer.pdf",
                    file_type="pdf",
                    file_size=1,
                    sha256="b" * 64,
                    chunk_size=800,
                    chunk_overlap=120,
                ),
                DocumentJob(
                    id="outside",
                    knowledge_base_slug="library-b",
                    original_filename="跨库.pdf",
                    storage_path="C:/outside.pdf",
                    file_type="pdf",
                    file_size=1,
                    sha256="c" * 64,
                    chunk_size=800,
                    chunk_overlap=120,
                ),
                DocumentPage(
                    document_id="source",
                    page_number=1,
                    raw_text="甲方义务。依据《中华人民共和国劳动合同法》第十条订立书面合同。",
                    search_text="甲方义务。依据《中华人民共和国劳动合同法》第十条订立书面合同。",
                    source="text",
                ),
            ]
        )
        session.commit()
    return factory


def test_relation_service_creates_idempotent_exact_law_citation():
    """法条名和条号均匹配的候选可关联，重复运行不重复写入。"""
    factory = build_session_factory()
    looked_up = []
    service = DocumentRelationService(
        factory,
        law_lookup=lambda law_name, article_number: (
            looked_up.append((law_name, article_number))
            or [{"target_id": "labor-contract-law:10", "target_type": "law_article"}]
        ),
    )

    first = service.rebuild("source")
    second = service.rebuild("source")

    assert looked_up == [
        ("中华人民共和国劳动合同法", "10"),
        ("中华人民共和国劳动合同法", "10"),
    ]
    assert len(first) == len(second) == 1
    assert first[0]["relation_type"] == "exact_law_citation"
    assert first[0]["law_article"] == "中华人民共和国劳动合同法第10条"
    assert first[0]["evidence_text"] == "《中华人民共和国劳动合同法》第十条"
    with factory() as session:
        assert session.query(DocumentRelation).filter_by(source_document_id="source").count() == 1


def test_relation_service_rejects_cross_library_and_evidenceless_semantic_candidates():
    """语义候选只能关联同一文档库，且必须携带来源页中的证据文本。"""
    factory = build_session_factory()
    service = DocumentRelationService(
        factory,
        semantic_candidate_provider=lambda _job, _pages: [
            {
                "target_document_id": "peer",
                "source_page_number": 1,
                "evidence_text": "甲方义务",
                "similarity": 0.91,
            },
            {
                "target_document_id": "outside",
                "source_page_number": 1,
                "evidence_text": "甲方义务",
                "similarity": 0.95,
            },
            {
                "target_document_id": "peer",
                "source_page_number": 1,
                "evidence_text": "不存在的原文",
                "similarity": 0.88,
            },
        ],
    )

    relations = service.rebuild("source")

    assert len(relations) == 1
    assert relations[0]["target_id"] == "peer"
    assert relations[0]["relation_type"] == "semantic_candidate"
    assert relations[0]["similarity"] == 0.91
