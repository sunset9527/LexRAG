from types import SimpleNamespace
import gzip
import hashlib
import json

import pytest

from src.retrieval.ephemeral_vectorstore import (
    EphemeralVectorStoreError,
    build_ephemeral_vectorstore,
    build_ephemeral_vectorstore_from_artifact,
    has_verified_runtime_collection,
)


class _SourceCollection:
    def __init__(self, events):
        self.events = events

    def get(self, *, include):
        self.events.append(("source_read", include))
        return {
            "ids": ["civil-17"],
            "documents": ["第十七条\n十八周岁以上的自然人为成年人。"],
            "metadatas": [{"article_id": "中华人民共和国民法典第17条", "law_name": "中华人民共和国民法典"}],
            "embeddings": [[0.1, 0.2]],
        }


class _RuntimeCollection:
    def __init__(self):
        self.added = None

    def add(self, **payload):
        self.added = payload

    def query(self, *, query_embeddings, n_results, where=None, include=None):
        assert query_embeddings == [[0.1, 0.2]]
        assert n_results == 2
        assert where == {"law_name": "中华人民共和国民法典"}
        assert include == ["documents", "metadatas", "distances"]
        return {
            "documents": [[self.added["documents"][0]]],
            "metadatas": [[self.added["metadatas"][0]]],
            "distances": [[0.2]],
        }

    def get(self, **_kwargs):
        return {"documents": [], "metadatas": []}


class _RuntimeClient:
    def __init__(self, collection):
        self.collection = collection

    def create_collection(self, *, name):
        assert name.startswith("runtime_")
        return self.collection


def test_runtime_store_reads_persistent_payload_before_loading_embedding_model():
    events = []
    source = _SourceCollection(events)
    runtime_collection = _RuntimeCollection()

    def embeddings_factory():
        events.append(("embedding_loaded",))
        return SimpleNamespace(embed_query=lambda _query: [0.1, 0.2])

    store = build_ephemeral_vectorstore(
        source_collection=source,
        collection_name="kb_civil_code_v_test",
        embeddings_factory=embeddings_factory,
        client_factory=lambda: _RuntimeClient(runtime_collection),
    )

    assert events == [
        ("source_read", ["documents", "metadatas", "embeddings"]),
        ("embedding_loaded",),
    ]
    assert runtime_collection.added["ids"] == ["civil-17"]
    result = store.similarity_search_with_relevance_scores(
        "成年人年龄", k=2, filter={"law_name": "中华人民共和国民法典"}
    )
    assert result[0][0].metadata["article_id"] == "中华人民共和国民法典第17条"
    assert result[0][1] == pytest.approx(1 - 0.2 / 2**0.5)


def test_runtime_store_rejects_misaligned_persistent_payload_before_embedding_load():
    events = []

    class BrokenSource:
        def get(self, *, include):
            events.append(("source_read", include))
            return {"ids": ["one"], "documents": [], "metadatas": [], "embeddings": []}

    with pytest.raises(EphemeralVectorStoreError, match="payload"):
        build_ephemeral_vectorstore(
            source_collection=BrokenSource(),
            collection_name="kb_civil_code_v_test",
            embeddings_factory=lambda: events.append(("embedding_loaded",)),
            client_factory=lambda: pytest.fail("must not create runtime client"),
        )

    assert events == [("source_read", ["documents", "metadatas", "embeddings"])]


def test_runtime_store_loads_configured_artifact_without_opening_persistent_chroma(tmp_path):
    artifact = tmp_path / "runtime-payload.json.gz"
    payload = {
        "ids": ["civil-17"],
        "documents": ["第十七条"],
        "metadatas": [{"article_id": "中华人民共和国民法典第17条"}],
        "embeddings": [[0.1, 0.2]],
    }
    value = {
        "schema": "lexrag.stage8-runtime-payload",
        "version": 1,
        "collections": {"civil-code": {"collection_name": "kb_civil_code_v_test", "payload": payload}},
    }
    compressed = gzip.compress(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"), mtime=0
    )
    artifact.write_bytes(compressed)
    (tmp_path / "runtime-payload.manifest.json").write_text(
        json.dumps(
            {
                "schema": value["schema"],
                "version": value["version"],
                "payload_sha256": hashlib.sha256(compressed).hexdigest(),
                "collections": [
                    {
                        "collection_name": "kb_civil_code_v_test",
                        "payload_sha256": hashlib.sha256(
                            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                        ).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    collection = _RuntimeCollection()
    store = build_ephemeral_vectorstore_from_artifact(
        artifact_path=artifact,
        collection_name="kb_civil_code_v_test",
        embeddings_factory=lambda: SimpleNamespace(embed_query=lambda _query: [0.1, 0.2]),
        client_factory=lambda: _RuntimeClient(collection),
    )

    assert store._collection is collection
    assert collection.added["ids"] == ["civil-17"]


def test_verified_runtime_collection_requires_a_matching_integrity_checked_entry(tmp_path):
    artifact = tmp_path / "runtime-payload.json.gz"
    payload = {
        "ids": ["civil-17"],
        "documents": ["第十七条"],
        "metadatas": [{"article_id": "中华人民共和国民法典第17条"}],
        "embeddings": [[0.1, 0.2]],
    }
    value = {
        "schema": "lexrag.stage8-runtime-payload",
        "version": 1,
        "collections": {"civil-code": {"collection_name": "kb_civil_code_v_test", "payload": payload}},
    }
    compressed = gzip.compress(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"), mtime=0
    )
    artifact.write_bytes(compressed)
    (tmp_path / "runtime-payload.manifest.json").write_text(
        json.dumps(
            {
                "schema": value["schema"],
                "version": value["version"],
                "payload_sha256": hashlib.sha256(compressed).hexdigest(),
                "collections": [
                    {
                        "collection_name": "kb_civil_code_v_test",
                        "payload_sha256": hashlib.sha256(
                            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                        ).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert has_verified_runtime_collection(artifact, "kb_civil_code_v_test") is True
    assert has_verified_runtime_collection(artifact, "kb_civil_code_v_unknown") is False
