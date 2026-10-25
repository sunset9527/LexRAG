"""确认法规新版本时，必须先在新 collection 成功建索引，才能切换线上指针。"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.models.knowledge_base import KnowledgeBase
from app.models.organization import Organization
from app.services.knowledge_base_service import KnowledgeBaseService


class Parser:
    def parse_law_content(self, content, name):
        return [{"id": "1", "content": content}]


class Chunker:
    def chunk_articles(self, articles):
        return articles


def setup(indexer_factory):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(Organization(id=1, name="甲", slug="a"))
        db.add(
            KnowledgeBase(
                name="民法典",
                slug="civil",
                type="statute",
                law_area="civil",
                collection_name="kb_civil_old",
                status="READY",
                document_count=1,
                chunk_count=1,
                organization_id=1,
            )
        )
        db.commit()
    return factory


def test_confirmed_rebuild_switches_collection_only_after_new_index_succeeds():
    seen = []
    factory = setup(None)
    service = KnowledgeBaseService(
        factory,
        parser=Parser(),
        chunker=Chunker(),
        indexer_factory=lambda collection: type(
            "I", (), {"rebuild_index": lambda _, chunks: seen.append(collection) or len(chunks)}
        )(),
    )
    result = service.rebuild_confirmed_law_version(
        "civil", organization_id=1, content="新法条", version_hash="abcdef123456"
    )
    assert seen == ["kb_civil_v_abcdef123456"]
    assert result["collection_name"] == "kb_civil_v_abcdef123456"


def test_confirmed_rebuild_passes_verified_version_provenance_to_isolated_index():
    seen = []
    factory = setup(None)
    provenance = {
        "version_id": "civil-code@2020-05-28",
        "effective_from": "2021-01-01",
        "effective_to": "",
        "source_url": "https://flk.npc.gov.cn/example",
        "content_hash": "a" * 64,
    }
    service = KnowledgeBaseService(
        factory,
        parser=Parser(),
        chunker=Chunker(),
        indexer_factory=lambda _: pytest.fail("must use versioned indexer factory"),
        versioned_indexer_factory=lambda collection, metadata: type(
            "I", (), {"rebuild_index": lambda _, chunks: seen.append((collection, metadata)) or len(chunks)}
        )(),
    )

    service.rebuild_confirmed_law_version(
        "civil",
        organization_id=1,
        content="新法条",
        version_hash="abcdef123456",
        provenance_metadata=provenance,
    )

    assert seen == [("kb_civil_v_abcdef123456", provenance)]


def test_confirmed_rebuild_does_not_switch_or_mark_ready_library_failed_when_new_index_fails():
    factory = setup(None)
    service = KnowledgeBaseService(
        factory,
        parser=Parser(),
        chunker=Chunker(),
        indexer_factory=lambda _: type(
            "I",
            (),
            {
                "rebuild_index": lambda _, chunks: (_ for _ in ()).throw(
                    RuntimeError("index failed")
                )
            },
        )(),
    )
    with pytest.raises(RuntimeError):
        service.rebuild_confirmed_law_version(
            "civil", organization_id=1, content="新法条", version_hash="abcdef123456"
        )
    with factory() as db:
        item = db.query(KnowledgeBase).one()
        assert item.collection_name == "kb_civil_old"
        assert item.status == "READY"


def test_historical_rebuild_keeps_active_collection_pointer_unchanged():
    seen = []
    factory = setup(None)
    service = KnowledgeBaseService(
        factory,
        parser=Parser(),
        chunker=Chunker(),
        indexer_factory=lambda collection: type(
            "I", (), {"rebuild_index": lambda _, chunks: seen.append(collection) or len(chunks)}
        )(),
    )

    result = service.rebuild_confirmed_law_version(
        "civil",
        organization_id=1,
        content="历史法条",
        version_hash="123456789abc",
        activate=False,
    )

    assert result["collection_name"] == "kb_civil_v_123456789abc"
    with factory() as db:
        assert db.query(KnowledgeBase).one().collection_name == "kb_civil_old"


def test_confirmed_version_collection_requires_an_existing_isolated_collection():
    factory = setup(None)
    service = KnowledgeBaseService(
        factory,
        collection_exists=lambda collection: collection == "kb_civil_v_abcdef123456",
    )

    assert service.get_confirmed_version_collection_name_for_organization(
        "civil", organization_id=1, content_hash="abcdef1234567890"
    ) == "kb_civil_v_abcdef123456"
    with pytest.raises(ValueError, match="VERSION_COLLECTION_NOT_READY"):
        service.get_confirmed_version_collection_name_for_organization(
            "civil", organization_id=1, content_hash="0" * 64
        )
