"""Tests for the immutable Stage 4 provenance snapshot."""

from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest

from src.evaluation.stage4_provenance_snapshot import (
    Stage4ProvenanceSnapshotError,
    build_stage4_provenance_snapshot,
)

CIVIL_ARTICLES = ["中华人民共和国民法典第17条", "中华人民共和国民法典第20条"]


class _Chains:
    def get_indexable_chain_for_law(self, slug: str, *, as_of: date):
        assert as_of == date(2026, 10, 27)
        return {
            "id": 7,
            "law_slug": slug,
            "target_version_id": f"{slug}@2020-05-28",
            "effective_from": "2021-01-01",
            "effective_to": None,
            "is_indexable": True,
        }

    def get_index_provenance(self, chain_id: int, *, as_of: date):
        assert chain_id == 7
        return {
            "version_id": "civil-code@2020-05-28",
            "effective_from": "2021-01-01",
            "effective_to": "",
            "source_url": "https://flk.npc.gov.cn/detail2.html",
            "content_hash": "a" * 64,
        }


class _KnowledgeBases:
    def list_knowledge_bases(self):
        return [
            {
                "slug": "civil-code",
                "status": "READY",
                "collection_name": "kb_civil_code_v_aaaaaaaaaaaa",
                "source_hash": "a" * 64,
                "embedding_fingerprint": "f" * 64,
                "index_schema_version": 1,
                "document_count": 2,
                "chunk_count": 2,
            }
        ]


def _collection(**overrides: object) -> dict[str, object]:
    articles = CIVIL_ARTICLES
    payload: dict[str, object] = {
        "name": "kb_civil_code_v_aaaaaaaaaaaa",
        "metadata": {
            "lexrag_statute_source_sha256": "a" * 64,
            "lexrag_embedding_fingerprint": "f" * 64,
            "lexrag_index_schema_version": 1,
        },
        "metadatas": [
            {
                "article_id": article,
                "version_id": "civil-code@2020-05-28",
                "effective_from": "2021-01-01",
                "effective_to": "",
                "source_url": "https://flk.npc.gov.cn/detail2.html",
                "content_hash": "a" * 64,
            }
            for article in articles
        ],
    }
    payload.update(overrides)
    return payload


def _build(collection=None, knowledge_bases=None):
    collection_payload = collection or _collection()
    return build_stage4_provenance_snapshot(
        ["civil-code"],
        as_of=date(2026, 10, 27),
        chain_service=_Chains(),
        knowledge_base_service=knowledge_bases or _KnowledgeBases(),
        collection_reader=lambda name: collection_payload,
    )


def test_snapshot_captures_verified_db_and_active_collection_facts():
    snapshot = _build()
    articles = CIVIL_ARTICLES

    assert snapshot == {
        "schema": "lexrag.stage4-provenance-snapshot",
        "version": 1,
        "as_of": "2026-10-27",
        "laws": [
            {
                "knowledge_base_slug": "civil-code",
                "version_id": "civil-code@2020-05-28",
                "effective_from": "2021-01-01",
                "effective_to": None,
                "source_url": "https://flk.npc.gov.cn/detail2.html",
                "content_hash": "a" * 64,
                "collection_name": "kb_civil_code_v_aaaaaaaaaaaa",
                "embedding_fingerprint": "f" * 64,
                "index_schema_version": 1,
                "chunk_count": 2,
                "article_ids": articles,
                "article_ids_sha256": hashlib.sha256(
                    json.dumps(
                        articles,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "article_count": 2,
            }
        ],
    }


@pytest.mark.parametrize(
    "collection,error",
    [
        (_collection(name="other"), "collection"),
        (
            _collection(
                metadata={
                    "lexrag_statute_source_sha256": "b" * 64,
                    "lexrag_embedding_fingerprint": "f" * 64,
                    "lexrag_index_schema_version": 1,
                }
            ),
            "provenance",
        ),
        (
            _collection(
                metadatas=[
                    {"article_id": " "},
                    _collection()["metadatas"][1],
                ]
            ),
            "blank",
        ),
        (
            _collection(
                metadatas=[
                    {
                        **_collection()["metadatas"][0],
                        "content_hash": "b" * 64,
                    },
                    _collection()["metadatas"][1],
                ]
            ),
            "provenance",
        ),
    ],
)
def test_snapshot_rejects_collection_identity_provenance_or_labels(collection, error):
    with pytest.raises(Stage4ProvenanceSnapshotError, match=error):
        _build(collection=collection)


def test_snapshot_rejects_non_ready_active_registry_pointer():
    class NotReady(_KnowledgeBases):
        def list_knowledge_bases(self):
            rows = super().list_knowledge_bases()
            rows[0]["status"] = "FAILED"
            return rows

    with pytest.raises(Stage4ProvenanceSnapshotError, match="READY"):
        _build(knowledge_bases=NotReady())


def test_snapshot_accepts_legacy_ready_pointer_with_null_source_hash():
    class LegacyReady(_KnowledgeBases):
        def list_knowledge_bases(self):
            rows = super().list_knowledge_bases()
            rows[0]["source_hash"] = None
            return rows

    snapshot = _build(knowledge_bases=LegacyReady())

    assert snapshot["laws"][0]["content_hash"] == "a" * 64
    assert snapshot["laws"][0]["collection_name"] == "kb_civil_code_v_aaaaaaaaaaaa"


def test_snapshot_accepts_legacy_collection_without_collection_level_source_hash():
    legacy_metadata = {
        "lexrag_embedding_fingerprint": "f" * 64,
        "lexrag_index_schema_version": 1,
    }

    snapshot = _build(collection=_collection(metadata=legacy_metadata))

    assert snapshot["laws"][0]["content_hash"] == "a" * 64


def test_snapshot_accepts_null_registry_identity_and_captures_collection_identity():
    class LegacyIdentity(_KnowledgeBases):
        def list_knowledge_bases(self):
            rows = super().list_knowledge_bases()
            rows[0]["embedding_fingerprint"] = None
            rows[0]["index_schema_version"] = None
            return rows

    law = _build(knowledge_bases=LegacyIdentity())["laws"][0]

    assert law["embedding_fingerprint"] == "f" * 64
    assert law["index_schema_version"] == 1


def test_snapshot_deduplicates_article_ids_across_verified_chunks():
    first, second = _collection()["metadatas"]

    class Chunked(_KnowledgeBases):
        def list_knowledge_bases(self):
            rows = super().list_knowledge_bases()
            rows[0]["chunk_count"] = 3
            return rows

    law = _build(
        knowledge_bases=Chunked(),
        collection=_collection(metadatas=[first, first, second]),
    )["laws"][0]

    assert law["chunk_count"] == 3
    assert law["article_count"] == 2
    assert law["article_ids"] == sorted([CIVIL_ARTICLES[0], CIVIL_ARTICLES[1]])


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("chunk_count", 3, "chunk count"),
        ("document_count", 3, "document count"),
    ],
)
def test_snapshot_rejects_registry_count_disagreement(field, value, error):
    class WrongCount(_KnowledgeBases):
        def list_knowledge_bases(self):
            rows = super().list_knowledge_bases()
            rows[0][field] = value
            return rows

    with pytest.raises(Stage4ProvenanceSnapshotError, match=error):
        _build(knowledge_bases=WrongCount())


def test_snapshot_rejects_active_collection_name_not_derived_from_verified_chain_hash():
    wrong_name = "kb_civil_code_v_wronghash"

    class WrongCollection(_KnowledgeBases):
        def list_knowledge_bases(self):
            rows = super().list_knowledge_bases()
            rows[0]["source_hash"] = None
            rows[0]["collection_name"] = wrong_name
            return rows

    with pytest.raises(Stage4ProvenanceSnapshotError, match="collection name"):
        _build(
            knowledge_bases=WrongCollection(),
            collection=_collection(name=wrong_name),
        )


def test_snapshot_rejects_duplicate_requested_slug():
    with pytest.raises(Stage4ProvenanceSnapshotError, match="duplicate"):
        build_stage4_provenance_snapshot(
            ["civil-code", "civil-code"],
            as_of=date(2026, 10, 27),
            chain_service=_Chains(),
            knowledge_base_service=_KnowledgeBases(),
            collection_reader=lambda name: _collection(),
        )
