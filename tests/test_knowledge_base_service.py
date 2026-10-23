"""知识库服务测试：使用内存 SQLite，不依赖 MySQL 或 Chroma。"""

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from app.db.base import Base
from app.models.knowledge_base import KnowledgeBase
from app.models.organization import (
    Organization,  # noqa: F401 - registers FK target for SQLite metadata
)
from app.services.knowledge_base_service import KnowledgeBaseService
from src.ingestion.index_identity import LegacyCollectionIdentityError


def build_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return KnowledgeBaseService(sessionmaker(bind=engine, expire_on_commit=False))


def test_create_statute_knowledge_base_uses_slug_scoped_collection_name():
    """每个法规库根据 slug 获得唯一且稳定的 collection 名。"""
    service = build_service()

    knowledge_base = service.create_knowledge_base(
        name="中华人民共和国劳动合同法",
        slug="labor-contract-law",
        law_area="labor",
    )

    assert knowledge_base["collection_name"] == "kb_labor_contract_law"
    assert knowledge_base["status"] == "EMPTY"
    assert knowledge_base["document_count"] == 0
    assert service.list_knowledge_bases() == [knowledge_base]


def test_system_shared_statute_readiness_requires_ready_pointer_identity_and_collection_facts():
    """Readiness must reject a registry row that only claims bootstrap success."""
    from app.services.knowledge_base_service import BootstrapCollectionCounts
    from src.ingestion.statute_catalog import StatuteIndexIdentity

    base_service = build_service()
    identity = StatuteIndexIdentity("civil-code", "a" * 64, "b" * 64, 1)
    verified: list[tuple[str, StatuteIndexIdentity]] = []
    service = KnowledgeBaseService(
        base_service._session_factory,
        bootstrap_collection_verifier=lambda name, expected: (
            verified.append((name, expected))
            or BootstrapCollectionCounts(article_count=2, chunk_count=3)
        ),
    )
    service.create_knowledge_base(
        name="中华人民共和国民法典",
        slug="civil-code",
        law_area="civil",
        is_system_shared=True,
    )
    with service._session_factory() as session:
        item = session.query(KnowledgeBase).filter_by(slug="civil-code").one()
        item.status = "READY"
        item.collection_name = identity.collection_name
        item.source_hash = identity.source_hash
        item.embedding_fingerprint = identity.embedding_fingerprint
        item.index_schema_version = identity.index_schema_version
        item.document_count = 2
        item.chunk_count = 3
        session.commit()

    service.assert_system_shared_statutes_ready({"civil-code": identity})

    assert verified == [(identity.collection_name, identity)]


def test_system_shared_statute_readiness_rejects_a_non_shared_or_mismatched_pointer():
    """Public readiness verification must fail closed before a bad collection is queried."""
    from app.services.knowledge_base_service import BootstrapCollectionVerificationError
    from src.ingestion.statute_catalog import StatuteIndexIdentity

    service = build_service()
    identity = StatuteIndexIdentity("civil-code", "a" * 64, "b" * 64, 1)
    service.create_knowledge_base(name="中华人民共和国民法典", slug="civil-code", law_area="civil")

    with pytest.raises(BootstrapCollectionVerificationError, match="STATUTE_READINESS"):
        service.assert_system_shared_statutes_ready({"civil-code": identity})


class FakeParser:
    def parse_law_content(self, content, law_name):
        assert content == "法律原文"
        assert law_name == "中华人民共和国民法典"
        return ["article-1", "article-2"]


class FakeChunker:
    def chunk_articles(self, articles):
        assert articles == ["article-1", "article-2"]
        return ["chunk-1", "chunk-2", "chunk-3"]


class FakeIndexer:
    def __init__(self, collection_name):
        self.collection_name = collection_name

    def rebuild_index(self, chunks):
        assert chunks == ["chunk-1", "chunk-2", "chunk-3"]
        return len(chunks)


def test_rebuild_only_updates_the_target_knowledge_base():
    """重建 A 只能操作 A 的 collection，不能改写 B 的状态或统计。"""
    created_collections = []
    base_service = build_service()
    service = KnowledgeBaseService(
        base_service._session_factory,
        parser=FakeParser(),
        chunker=FakeChunker(),
        indexer_factory=lambda collection_name: (
            created_collections.append(collection_name) or FakeIndexer(collection_name)
        ),
    )
    civil_code = service.create_knowledge_base(
        name="中华人民共和国民法典", slug="civil-code", law_area="civil"
    )
    other = service.create_knowledge_base(
        name="中华人民共和国劳动合同法", slug="labor-contract-law", law_area="labor"
    )

    rebuilt = service.rebuild_knowledge_base("civil-code", content="法律原文")

    assert created_collections == ["kb_civil_code"]
    assert rebuilt["status"] == "READY"
    assert rebuilt["document_count"] == 2
    assert rebuilt["chunk_count"] == 3
    assert service.list_knowledge_bases()[1] == other
    assert civil_code["status"] == "EMPTY"


def test_rebuild_rejects_a_knowledge_base_that_is_already_indexing():
    """同一个库正在重建时必须拒绝第二个请求，防止并发清空索引。"""
    service = build_service()
    service.create_knowledge_base(name="民法典", slug="civil-code", law_area="civil")
    with service._session_factory() as session:
        item = session.query(KnowledgeBase).filter_by(slug="civil-code").one()
        item.status = "INDEXING"
        session.commit()

    with pytest.raises(ValueError, match="正在重建"):
        service.rebuild_knowledge_base("civil-code", content="法律原文")


def test_rebuild_preserves_ready_status_when_current_collection_requires_identity_rebuild():
    """旧 collection 身份不兼容时，不能把仍可用的知识库标记为 FAILED。"""
    base_service = build_service()

    class IdentityFailingIndexer:
        def rebuild_index(self, _chunks):
            raise LegacyCollectionIdentityError()

    service = KnowledgeBaseService(
        base_service._session_factory,
        parser=FakeParser(),
        chunker=FakeChunker(),
        indexer_factory=lambda _collection_name: IdentityFailingIndexer(),
    )
    service.create_knowledge_base(name="中华人民共和国民法典", slug="civil-code", law_area="civil")
    with service._session_factory() as session:
        knowledge_base = session.query(KnowledgeBase).filter_by(slug="civil-code").one()
        knowledge_base.status = "READY"
        knowledge_base.error_message = None
        session.commit()

    with pytest.raises(LegacyCollectionIdentityError):
        service.rebuild_knowledge_base("civil-code", content="法律原文")

    assert service.list_knowledge_bases()[0]["status"] == "READY"
    assert service.list_knowledge_bases()[0]["error_message"] is None


def test_list_law_articles_reads_only_the_selected_collection():
    """法规浏览必须从选定知识库的独立 collection 读取真实条文。"""
    base_service = build_service()
    collections = []
    service = KnowledgeBaseService(
        base_service._session_factory,
        article_reader=lambda collection_name: (
            collections.append(collection_name)
            or [{"article_id": "民法典第1条", "content": "为了保护民事主体的合法权益。"}]
        ),
    )
    service.create_knowledge_base(name="民法典", slug="civil-code", law_area="civil")

    result = service.list_law_articles("civil-code")

    assert collections == ["kb_civil_code"]
    assert result == [{"id": "民法典第1条", "content": "为了保护民事主体的合法权益。"}]


def test_list_law_articles_filters_by_article_number_range():
    """法规目录选择一个编时，只返回该编法条号范围内的真实条文。"""
    base_service = build_service()
    service = KnowledgeBaseService(
        base_service._session_factory,
        article_reader=lambda _collection_name: [
            {"article_id": "民法典第1条", "article_number": "1", "content": "总则"},
            {"article_id": "民法典第463条", "article_number": "463", "content": "合同编"},
            {"article_id": "民法典第989条", "article_number": "989", "content": "人格权编"},
        ],
    )
    service.create_knowledge_base(name="民法典", slug="civil-code", law_area="civil")

    result = service.list_law_articles("civil-code", start_article=463, end_article=988)

    assert result == [{"id": "民法典第463条", "article_number": 463, "content": "合同编"}]


def test_list_law_articles_keeps_inserted_article_number_for_browsing():
    """增设条款应参与所属条号范围，并以可读的稳定编号返回前端。"""
    base_service = build_service()
    service = KnowledgeBaseService(
        base_service._session_factory,
        article_reader=lambda _collection_name: [
            {
                "article_id": "刑法第17条之一",
                "article_number": "17-1",
                "content": "已满七十五周岁的人的刑事责任。",
            }
        ],
    )
    service.create_knowledge_base(name="刑法", slug="criminal-law", law_area="criminal")

    result = service.list_law_articles("criminal-law", start_article=17, end_article=17)

    assert result == [
        {
            "id": "刑法第17条之一",
            "article_number": "17-1",
            "content": "已满七十五周岁的人的刑事责任。",
        }
    ]


def test_delete_knowledge_base_removes_only_its_collection_and_registration():
    """删除法规库应删除其专属 collection 和注册记录。"""
    base_service = build_service()
    deleted = []
    service = KnowledgeBaseService(
        base_service._session_factory,
        collection_deleter=deleted.append,
    )
    service.create_knowledge_base(name="民法典", slug="civil-code", law_area="civil")
    service.create_knowledge_base(name="劳动法", slug="labor-law", law_area="labor")

    service.delete_knowledge_base("civil-code")

    assert deleted == ["kb_civil_code"]
    assert [item["slug"] for item in service.list_knowledge_bases()] == ["labor-law"]
