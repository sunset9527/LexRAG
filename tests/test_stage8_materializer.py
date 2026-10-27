"""Tests for deterministic Stage 8 formal-dataset materialization."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

from src.evaluation.stage8_materializer import (
    Stage8MaterializationError,
    build_stage8_manifest,
    materialize_stage8_records,
    records_jsonl,
    validate_formal_freeze_counts,
)


CIVIL_ARTICLE = "中华人民共和国民法典第17条"
COMPANY_ARTICLE = "中华人民共和国公司法第23条"


def _baseline(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "queue_id": "cross-001",
        "origin": "hard_candidate",
        "question": "成年人设立公司涉及哪些规则？",
        "proposed_question_type": "cross_law",
        "proposed_difficulty": "hard",
        "proposed_knowledge_base_slugs": ["civil-code", "company-law"],
        "proposed_relevant_article_ids": [CIVIL_ARTICLE, COMPANY_ARTICLE],
        "proposed_should_abstain": False,
        "local_source_locator": f"{CIVIL_ARTICLE}；{COMPANY_ARTICLE}",
        "review_state": "approved",
        "reviewer": "reviewer-a",
        "reviewed_at": "2026-10-27T20:30:00+08:00",
        "review_note": "逐项核对通过。",
        "verified_record": None,
    }
    row.update(overrides)
    return row


def _law(slug: str, article_ids: list[str], marker: str) -> dict[str, object]:
    return {
        "knowledge_base_slug": slug,
        "version_id": f"{slug}@2020-01-01",
        "effective_from": "2021-01-01",
        "effective_to": None,
        "source_url": f"https://flk.npc.gov.cn/{slug}",
        "content_hash": marker * 64,
        "collection_name": f"kb_{slug.replace('-', '_')}_v_{marker * 12}",
        "embedding_fingerprint": "f" * 64,
        "index_schema_version": 1,
        "chunk_count": len(article_ids),
        "article_ids": article_ids,
        "article_ids_sha256": hashlib.sha256(
            json.dumps(
                article_ids,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "article_count": len(article_ids),
    }


def _snapshot(*laws: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "lexrag.stage4-provenance-snapshot",
        "version": 1,
        "as_of": "2026-10-27",
        "laws": list(laws),
    }


def test_materializer_preserves_reviewed_values_and_partitions_cross_law_labels():
    baseline = _baseline()
    snapshot = _snapshot(
        _law("civil-code", [CIVIL_ARTICLE], "a"),
        _law("company-law", [COMPANY_ARTICLE], "b"),
    )

    records = materialize_stage8_records([baseline], snapshot)

    assert records[0] == {
        "id": baseline["queue_id"],
        "question": baseline["question"],
        "question_type": baseline["proposed_question_type"],
        "difficulty": baseline["proposed_difficulty"],
        "expected_knowledge_base_slugs": baseline["proposed_knowledge_base_slugs"],
        "relevant_article_ids": baseline["proposed_relevant_article_ids"],
        "should_abstain": False,
        "source_evidence": [
            {
                "knowledge_base_slug": "civil-code",
                "version_id": "civil-code@2020-01-01",
                "effective_from": "2021-01-01",
                "effective_to": None,
                "source_url": "https://flk.npc.gov.cn/civil-code",
                "content_hash": "a" * 64,
                "article_ids": [CIVIL_ARTICLE],
                "source_locator": CIVIL_ARTICLE,
            },
            {
                "knowledge_base_slug": "company-law",
                "version_id": "company-law@2020-01-01",
                "effective_from": "2021-01-01",
                "effective_to": None,
                "source_url": "https://flk.npc.gov.cn/company-law",
                "content_hash": "b" * 64,
                "article_ids": [COMPANY_ARTICLE],
                "source_locator": COMPANY_ARTICLE,
            },
        ],
        "reviewer": baseline["reviewer"],
        "reviewed_at": baseline["reviewed_at"],
        "review_note": baseline["review_note"],
        "review_status": "approved",
    }


def test_materializer_keeps_empty_abstain_evidence_with_deterministic_locator():
    row = _baseline(
        queue_id="abstain-001",
        proposed_knowledge_base_slugs=["civil-code"],
        proposed_relevant_article_ids=[],
        proposed_should_abstain=True,
        local_source_locator="民法典适用范围",
    )

    record = materialize_stage8_records(
        [row], _snapshot(_law("civil-code", [CIVIL_ARTICLE], "a"))
    )[0]

    assert record["source_evidence"][0]["article_ids"] == []
    assert record["source_evidence"][0]["source_locator"] == (
        "民法典适用范围 | knowledge_base_slug=civil-code"
    )


@pytest.mark.parametrize(
    "laws,error",
    [
        (
            [
                _law("civil-code", ["中华人民共和国民法典第18条"], "a"),
                _law("company-law", [COMPANY_ARTICLE], "b"),
            ],
            "zero",
        ),
        (
            [
                _law("civil-code", sorted([CIVIL_ARTICLE, COMPANY_ARTICLE]), "a"),
                _law("company-law", sorted([CIVIL_ARTICLE, COMPANY_ARTICLE]), "b"),
            ],
            "multiple",
        ),
    ],
)
def test_materializer_rejects_zero_or_multiple_article_catalog_matches(laws, error):
    with pytest.raises(Stage8MaterializationError, match=error):
        materialize_stage8_records([_baseline()], _snapshot(*laws))


def test_manifest_binds_inputs_output_and_counts_without_quality_claim():
    records = materialize_stage8_records(
        [_baseline()],
        _snapshot(
            _law("civil-code", [CIVIL_ARTICLE], "a"),
            _law("company-law", [COMPANY_ARTICLE], "b"),
        ),
    )
    dataset_payload = records_jsonl(records)
    baseline_payload = b"reviewed baseline\n"
    snapshot_payload = b'{"snapshot":true}\n'

    manifest = build_stage8_manifest(
        records,
        dataset_payload=dataset_payload,
        baseline_payload=baseline_payload,
        snapshot_payload=snapshot_payload,
        generated_at=datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
    )

    assert manifest["schema"] == "lexrag.stage8-frozen-dataset-manifest"
    assert manifest["version"] == 1
    assert manifest["generated_at"] == "2026-10-27T12:00:00+00:00"
    assert manifest["dataset"] == {
        "row_count": 1,
        "sha256": hashlib.sha256(dataset_payload).hexdigest(),
    }
    assert manifest["inputs"] == {
        "reviewed_baseline_sha256": hashlib.sha256(baseline_payload).hexdigest(),
        "stage4_snapshot_sha256": hashlib.sha256(snapshot_payload).hexdigest(),
    }
    assert manifest["evidence_count"] == 2
    assert manifest["label_count"] == 2
    assert manifest["per_slug"]["civil-code"]["evidence_count"] == 1
    assert "performance" not in json.dumps(manifest).lower()
    assert "human-reviewed baseline" in manifest["provenance_statement"]


def test_formal_freeze_counts_require_280_rows_320_evidence_and_460_labels():
    with pytest.raises(Stage8MaterializationError, match="280"):
        validate_formal_freeze_counts([{"source_evidence": [], "relevant_article_ids": []}])


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("embedding_fingerprint", "not-a-hash", "fingerprint"),
        ("index_schema_version", 0, "schema version"),
        ("chunk_count", 0, "chunk count"),
    ],
)
def test_materializer_rejects_invalid_captured_collection_identity(field, value, error):
    law = _law("civil-code", [CIVIL_ARTICLE], "a")
    law[field] = value
    row = _baseline(
        proposed_knowledge_base_slugs=["civil-code"],
        proposed_relevant_article_ids=[CIVIL_ARTICLE],
    )

    with pytest.raises(Stage8MaterializationError, match=error):
        materialize_stage8_records([row], _snapshot(law))
