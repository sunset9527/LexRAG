"""Bootstrap collection switching must isolate legacy collections."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.knowledge_base import KnowledgeBase
from app.models.organization import Organization  # noqa: F401 - registers FK target


class _Parser:
    def parse_law_content(self, content, _name):
        return [{"content": content}]


class _Chunker:
    def chunk_articles(self, articles):
        return articles


def _service_with_legacy_default_collection():
    from app.services.knowledge_base_service import KnowledgeBaseService

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(Organization(id=1, name="system", slug="system"))
        session.add(
            KnowledgeBase(
                name="中华人民共和国民法典",
                slug="civil-code",
                type="statute",
                law_area="civil",
                collection_name="law_articles",
                status="READY",
                document_count=1,
                chunk_count=1,
                organization_id=1,
                is_system_shared=True,
            )
        )
        session.commit()
    return factory, KnowledgeBaseService


def test_bootstrap_rebuild_switches_away_from_legacy_default_without_deleting_it():
    """A legacy default collection is neither read nor deleted during a bootstrap rebuild."""
    from src.ingestion.statute_catalog import StatuteIndexIdentity

    factory, service_class = _service_with_legacy_default_collection()
    built_collections: list[str] = []
    service = service_class(
        factory,
        parser=_Parser(),
        chunker=_Chunker(),
        indexer_factory=lambda collection_name: type(
            "Indexer",
            (), {"rebuild_index": lambda _self, chunks: built_collections.append(collection_name) or len(chunks)},
        )(),
    )
    identity = StatuteIndexIdentity("civil-code", "a" * 64, "b" * 64, 1)

    result = service.rebuild_bootstrap_statute("civil-code", content="new text", identity=identity)

    assert built_collections == [identity.collection_name]
    assert result["bootstrap_action"] == "rebuilt"
    assert result["collection_name"] == identity.collection_name
    assert result["source_hash"] == "a" * 64
    assert result["embedding_fingerprint"] == "b" * 64
    with factory() as session:
        item = session.query(KnowledgeBase).filter_by(slug="civil-code").one()
        assert item.collection_name == identity.collection_name
        assert item.status == "READY"


def test_bootstrap_rebuild_skips_only_when_current_pointer_has_full_identity():
    """Matching hashes alone cannot make a legacy collection look bootstrap-ready."""
    from src.ingestion.statute_catalog import StatuteIndexIdentity

    factory, service_class = _service_with_legacy_default_collection()
    built_collections: list[str] = []
    service = service_class(
        factory,
        parser=_Parser(),
        chunker=_Chunker(),
        indexer_factory=lambda collection_name: type(
            "Indexer",
            (), {"rebuild_index": lambda _self, chunks: built_collections.append(collection_name) or len(chunks)},
        )(),
    )
    identity = StatuteIndexIdentity("civil-code", "a" * 64, "b" * 64, 1)

    service.rebuild_bootstrap_statute("civil-code", content="new text", identity=identity)
    result = service.rebuild_bootstrap_statute("civil-code", content="new text", identity=identity)

    assert built_collections == [identity.collection_name]
    assert result["bootstrap_action"] == "skipped"
