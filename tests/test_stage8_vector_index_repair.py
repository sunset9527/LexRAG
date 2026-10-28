from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from src.evaluation.stage8_vector_index_repair import (
    Stage8VectorRepairError,
    repair_isolated_copy,
    rebuild_snapshot_collections,
)


LAW = {
    "knowledge_base_slug": "civil-code",
    "collection_name": "kb_civil_code_v_aaaaaaaaaaaa",
    "embedding_fingerprint": "fingerprint",
    "index_schema_version": 1,
    "content_hash": "a" * 64,
    "version_id": "civil-code@2020-05-28",
    "effective_from": "2021-01-01",
    "effective_to": None,
    "source_url": "https://flk.npc.gov.cn/",
    "chunk_count": 2,
    "article_ids": ["中华人民共和国民法典第1条", "中华人民共和国民法典第2条"],
}


def _metadata(article_id: str) -> dict:
    return {
        "article_id": article_id,
        "version_id": LAW["version_id"],
        "effective_from": LAW["effective_from"],
        "effective_to": "",
        "source_url": LAW["source_url"],
        "content_hash": LAW["content_hash"],
    }


class Collection:
    def __init__(self, name: str, metadata: dict, *, query_fails: bool = False):
        self.name = name
        self.metadata = deepcopy(metadata)
        self.query_fails = query_fails
        self.payload = {"ids": [], "documents": [], "metadatas": [], "embeddings": []}

    def count(self):
        return len(self.payload["ids"])

    def get(self, *, include):
        assert include == ["documents", "metadatas", "embeddings"]
        return deepcopy(self.payload)

    def add(self, *, ids, documents, metadatas, embeddings):
        self.payload["ids"].extend(ids)
        self.payload["documents"].extend(documents)
        self.payload["metadatas"].extend(metadatas)
        self.payload["embeddings"].extend(embeddings)

    def query(self, *, query_embeddings, n_results):
        if self.query_fails:
            raise RuntimeError("HNSW reader unavailable")
        assert n_results == 1
        assert query_embeddings == [self.payload["embeddings"][0]]
        return {"ids": [[self.payload["ids"][0]]]}


class Client:
    def __init__(self, collections: dict[str, Collection], *, query_fails: bool = False):
        self.collections = collections
        self.query_fails = query_fails

    def get_collection(self, *, name):
        return self.collections[name]

    def delete_collection(self, *, name):
        del self.collections[name]

    def create_collection(self, *, name, metadata):
        collection = Collection(name, metadata, query_fails=self.query_fails)
        self.collections[name] = collection
        return collection


def _source_collection() -> Collection:
    collection = Collection(
        LAW["collection_name"],
        {
            "lexrag_embedding_fingerprint": LAW["embedding_fingerprint"],
            "lexrag_index_schema_version": LAW["index_schema_version"],
            "lexrag_statute_source_sha256": LAW["content_hash"],
        },
    )
    collection.add(
        ids=["first", "second"],
        documents=["first document", "second document"],
        metadatas=[_metadata(article) for article in LAW["article_ids"]],
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
    )
    return collection


def test_rebuild_recreates_collection_from_exact_stored_payload_and_queries_it():
    source = Client({LAW["collection_name"]: _source_collection()})
    target = Client({LAW["collection_name"]: _source_collection()})

    report = rebuild_snapshot_collections(source, target, {LAW["knowledge_base_slug"]: LAW})

    rebuilt = target.get_collection(name=LAW["collection_name"])
    assert rebuilt.payload == source.get_collection(name=LAW["collection_name"]).payload
    assert report == {
        "collections": [
            {
                "knowledge_base_slug": "civil-code",
                "collection_name": LAW["collection_name"],
                "chunk_count": 2,
                "payload_sha256": report["collections"][0]["payload_sha256"],
                "queryable": True,
            }
        ]
    }


def test_rebuild_accepts_chroma_numpy_embedding_payloads():
    class ChromaCollection(Collection):
        def get(self, *, include):
            result = super().get(include=include)
            result["embeddings"] = np.asarray(result["embeddings"], dtype=np.float32)
            return result

    source_collection = ChromaCollection(
        LAW["collection_name"],
        {
            "lexrag_embedding_fingerprint": LAW["embedding_fingerprint"],
            "lexrag_index_schema_version": LAW["index_schema_version"],
            "lexrag_statute_source_sha256": LAW["content_hash"],
        },
    )
    source_collection.add(
        ids=["first", "second"],
        documents=["first document", "second document"],
        metadatas=[_metadata(article) for article in LAW["article_ids"]],
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
    )
    source = Client({LAW["collection_name"]: source_collection})
    target = Client({LAW["collection_name"]: _source_collection()})

    rebuild_snapshot_collections(source, target, {LAW["knowledge_base_slug"]: LAW})

    actual = target.get_collection(name=LAW["collection_name"]).payload["embeddings"]
    assert actual[0] == pytest.approx([0.1, 0.2])
    assert actual[1] == pytest.approx([0.3, 0.4])


def test_rebuild_rejects_target_with_unqueryable_hnsw_segment():
    source = Client({LAW["collection_name"]: _source_collection()})
    target = Client({LAW["collection_name"]: _source_collection()}, query_fails=True)

    with pytest.raises(Stage8VectorRepairError, match="queryability check failed"):
        rebuild_snapshot_collections(source, target, {LAW["knowledge_base_slug"]: LAW})


def test_repair_isolated_copy_requires_a_new_target_and_never_reuses_source(tmp_path):
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    source = Client({LAW["collection_name"]: _source_collection()})
    target = Client({LAW["collection_name"]: _source_collection()})
    calls = []

    def copytree(actual_source, actual_target):
        calls.append((actual_source, actual_target))
        actual_target.mkdir()

    def client_factory(path):
        return source if path == str(source_path) else target

    report = repair_isolated_copy(
        source_path,
        target_path,
        {LAW["knowledge_base_slug"]: LAW},
        client_factory=client_factory,
        copytree=copytree,
    )

    assert calls == [(source_path, target_path)]
    assert report["collections"][0]["queryable"] is True
    with pytest.raises(Stage8VectorRepairError, match="target directory must not exist"):
        repair_isolated_copy(
            source_path,
            target_path,
            {LAW["knowledge_base_slug"]: LAW},
            client_factory=client_factory,
            copytree=copytree,
        )
