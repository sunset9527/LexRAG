"""Bootstrap collection switching must isolate legacy collections."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.knowledge_base import KnowledgeBase
from app.models.organization import Organization  # noqa: F401 - registers FK target


class _CollectionStore:
    """In-memory stand-in for the collection facts Chroma must prove."""

    def __init__(self, collections=None):
        self.collections = collections or {}

    def verify(self, collection_name, _identity):
        return self.collections.get(collection_name)


def _indexer_factory(store, built_collections):
    from app.services.knowledge_base_service import BootstrapCollectionCounts

    def factory(collection_name):
        return type(
            "Indexer",
            (),
            {
                "rebuild_index": lambda _self, chunks: (
                    built_collections.append(collection_name),
                    store.collections.__setitem__(
                        collection_name,
                        BootstrapCollectionCounts(article_count=1, chunk_count=len(chunks)),
                    ),
                    len(chunks),
                )[-1]
            },
        )()

    return factory


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
    store = _CollectionStore()
    service = service_class(
        factory,
        parser=_Parser(),
        chunker=_Chunker(),
        indexer_factory=_indexer_factory(store, built_collections),
        bootstrap_collection_verifier=store.verify,
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
    store = _CollectionStore()
    service = service_class(
        factory,
        parser=_Parser(),
        chunker=_Chunker(),
        indexer_factory=_indexer_factory(store, built_collections),
        bootstrap_collection_verifier=store.verify,
    )
    identity = StatuteIndexIdentity("civil-code", "a" * 64, "b" * 64, 1)

    service.rebuild_bootstrap_statute("civil-code", content="new text", identity=identity)
    result = service.rebuild_bootstrap_statute("civil-code", content="new text", identity=identity)

    assert built_collections == [identity.collection_name]
    assert result["bootstrap_action"] == "skipped"


def test_bootstrap_rebuilds_missing_active_collection_into_isolated_candidate():
    """A READY pointer alone cannot skip when its Chroma collection is gone."""
    from src.ingestion.statute_catalog import StatuteIndexIdentity

    factory, service_class = _service_with_legacy_default_collection()
    identity = StatuteIndexIdentity("civil-code", "a" * 64, "b" * 64, 1)
    store = _CollectionStore()
    with factory() as session:
        item = session.query(KnowledgeBase).filter_by(slug="civil-code").one()
        item.collection_name = identity.collection_name
        item.source_hash = identity.source_hash
        item.embedding_fingerprint = identity.embedding_fingerprint
        item.index_schema_version = identity.index_schema_version
        session.commit()

    built_collections: list[str] = []
    service = service_class(
        factory,
        parser=_Parser(),
        chunker=_Chunker(),
        indexer_factory=_indexer_factory(store, built_collections),
        bootstrap_collection_verifier=store.verify,
    )

    result = service.rebuild_bootstrap_statute("civil-code", content="new text", identity=identity)

    assert result["bootstrap_action"] == "rebuilt"
    assert len(built_collections) == 1
    assert built_collections[0] != identity.collection_name
    assert built_collections[0].startswith(f"{identity.collection_name}_candidate_")
    assert result["collection_name"] == built_collections[0]


def test_bootstrap_rebuilds_corrupt_active_collection_instead_of_skipping():
    """A collection whose identity cannot be verified must be treated as unavailable."""
    from src.ingestion.statute_catalog import StatuteIndexIdentity

    factory, service_class = _service_with_legacy_default_collection()
    identity = StatuteIndexIdentity("civil-code", "a" * 64, "b" * 64, 1)
    store = _CollectionStore({identity.collection_name: None})
    with factory() as session:
        item = session.query(KnowledgeBase).filter_by(slug="civil-code").one()
        item.collection_name = identity.collection_name
        item.source_hash = identity.source_hash
        item.embedding_fingerprint = identity.embedding_fingerprint
        item.index_schema_version = identity.index_schema_version
        session.commit()

    rebuilt: list[str] = []

    service = service_class(
        factory,
        parser=_Parser(),
        chunker=_Chunker(),
        indexer_factory=_indexer_factory(store, rebuilt),
        bootstrap_collection_verifier=store.verify,
    )

    result = service.rebuild_bootstrap_statute("civil-code", content="new text", identity=identity)

    assert result["bootstrap_action"] == "rebuilt"
    assert rebuilt[0] != identity.collection_name
    assert store.collections[identity.collection_name] is None


def test_bootstrap_rebuilds_when_active_collection_counts_do_not_match_registry():
    """Registry counts must agree with Chroma before an idempotent bootstrap skip."""
    from app.services.knowledge_base_service import BootstrapCollectionCounts
    from src.ingestion.statute_catalog import StatuteIndexIdentity

    factory, service_class = _service_with_legacy_default_collection()
    identity = StatuteIndexIdentity("civil-code", "a" * 64, "b" * 64, 1)
    store = _CollectionStore(
        {identity.collection_name: BootstrapCollectionCounts(article_count=1, chunk_count=2)}
    )
    with factory() as session:
        item = session.query(KnowledgeBase).filter_by(slug="civil-code").one()
        item.collection_name = identity.collection_name
        item.source_hash = identity.source_hash
        item.embedding_fingerprint = identity.embedding_fingerprint
        item.index_schema_version = identity.index_schema_version
        item.document_count = 1
        item.chunk_count = 1
        session.commit()

    rebuilt: list[str] = []

    service = service_class(
        factory,
        parser=_Parser(),
        chunker=_Chunker(),
        indexer_factory=_indexer_factory(store, rebuilt),
        bootstrap_collection_verifier=store.verify,
    )

    result = service.rebuild_bootstrap_statute("civil-code", content="new text", identity=identity)

    assert result["bootstrap_action"] == "rebuilt"
    assert rebuilt[0] != identity.collection_name


def test_bootstrap_candidate_name_fits_registry_collection_name_column():
    """Recovery names remain storable even for the longest supported slug."""
    from app.services.knowledge_base_service import KnowledgeBaseService

    candidate = KnowledgeBaseService._candidate_collection_name("x" * 128)

    assert len(candidate) <= 128
    assert "_candidate_" in candidate


def test_bootstrap_does_not_switch_when_verified_collection_lost_a_chunk():
    """A successful index call cannot hide a collection smaller than the planned chunks."""
    from app.services.knowledge_base_service import (
        BootstrapCollectionCounts,
        BootstrapCollectionVerificationError,
    )
    from src.ingestion.statute_catalog import StatuteIndexIdentity

    factory, service_class = _service_with_legacy_default_collection()
    identity = StatuteIndexIdentity("civil-code", "a" * 64, "b" * 64, 1)
    store = _CollectionStore()

    class TwoChunker:
        def chunk_articles(self, _articles):
            return ["first", "second"]

    def indexer_factory(collection_name):
        return type(
            "Indexer",
            (),
            {
                "rebuild_index": lambda _self, _chunks: (
                    store.collections.__setitem__(
                        collection_name, BootstrapCollectionCounts(article_count=1, chunk_count=1)
                    )
                    or 1
                )
            },
        )()

    service = service_class(
        factory,
        parser=_Parser(),
        chunker=TwoChunker(),
        indexer_factory=indexer_factory,
        bootstrap_collection_verifier=store.verify,
    )

    with pytest.raises(BootstrapCollectionVerificationError):
        service.rebuild_bootstrap_statute("civil-code", content="new text", identity=identity)

    with factory() as session:
        item = session.query(KnowledgeBase).filter_by(slug="civil-code").one()
        assert item.collection_name == "law_articles"
