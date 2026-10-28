"""Committed integrity gate for the formal Stage 8 freeze artifacts."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from src.evaluation.stage4_provenance_snapshot import canonical_json_sha256
from src.evaluation.stage8_dataset import REQUIRED_STAGE8_FIELDS, load_stage8_dataset
from src.evaluation.stage8_materializer import load_reviewed_baseline, load_stage4_snapshot

ROOT = Path(__file__).resolve().parents[1]
STAGE8 = ROOT / "data" / "evaluation" / "stage8"
BASELINE = STAGE8 / "stage8_reviewed_baseline_280.jsonl"
SNAPSHOT = STAGE8 / "stage4_provenance_2026-10-27.json"
DATASET = STAGE8 / "stage8_frozen_280.jsonl"
MANIFEST = STAGE8 / "stage8_frozen_280.manifest.json"

EXPECTED_DATASET_SHA256 = "de1ea5f227ef005dbf964555d837b54db549610a5c92b979c579882a5fef7a33"
EXPECTED_SNAPSHOT_SHA256 = "bce7126dbb249517ed4f32630203103fe4e7c04bdbdec97a1460304ede9d3df5"
EXPECTED_BASELINE_SHA256 = "13a0af5ff0a977f40276222b6f45df4fdf2e0b6e2a1a56b31258cb41430f4399"
EXPECTED_EMBEDDING_FINGERPRINT = (
    "a818074ac6bd73d5e29d061cf23ac1d08ab32f23eac49b627fd4e71818a9627c"
)
EXPECTED_LAWS = {
    "civil-code": (
        "civil-code@2020-05-28",
        "853d1a8756b8b4c33ab15ec380de71dc9cb6438680bb8a98bbdcf08258a8c35e",
        1260,
        1634,
    ),
    "company-law": (
        "company-law@2023-12-29",
        "2a469e6461d40c37ff786218cacee98fae70b1cd426d33cd63608fb8db798aba",
        266,
        436,
    ),
    "copyright-law": (
        "copyright-law@2020-11-11",
        "2cd05cb08e2881af36f78b85d6587c524897bde0b25a283bbb22562c1332a203",
        67,
        161,
    ),
    "criminal-law": (
        "criminal-law@2024-03-01",
        "b2b02ff24310ca477befd14333e315ebdf00eea68ff5f07d274ad91c2831b8ab",
        505,
        768,
    ),
    "labor-contract-law": (
        "labor-contract-law@2012-12-28",
        "d32229a55ab961635ae01e7becf6f11cd22d98a61dfb35c2796ee2d8edaf37b9",
        98,
        178,
    ),
    "labor-law": (
        "labor-law@2018-12-29",
        "5c94703bd8481fbe00f58eba49ac0c7d8d36e1c7133bc73eb6ba3231cc8c52c4",
        107,
        157,
    ),
    "patent-law": (
        "patent-law@2020-10-17",
        "73ad59ae3213de95594319ee1d9fe8a79ceef4248273b9881a0d96a8960dca28",
        82,
        106,
    ),
    "trademark-law": (
        "trademark-law@2019-04-23",
        "cba3cd94ade450129323857a36c83538dcf9fc974c785d23c9e6168f0ace339b",
        73,
        103,
    ),
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_committed_formal_dataset_has_the_reviewed_280_row_contract():
    records = load_stage8_dataset(DATASET, require_approved=True)

    assert len(records) == 280
    assert sum(len(row["source_evidence"]) for row in records) == 320
    assert sum(len(row["relevant_article_ids"]) for row in records) == 460
    assert sum(len(row["source_evidence"]) == 2 for row in records) == 40
    assert sum(row["should_abstain"] for row in records) == 20
    assert all(set(row) == REQUIRED_STAGE8_FIELDS for row in records)
    forbidden = {"source_url", "source_version", "source_locator"}
    assert all(not (set(row) & forbidden) for row in records)
    assert all(not any(field.startswith("proposed_") for field in row) for row in records)
    assert _sha256(DATASET.read_bytes()) == EXPECTED_DATASET_SHA256


def test_committed_stage4_snapshot_freezes_the_live_eight_law_sources():
    snapshot, snapshot_payload = load_stage4_snapshot(SNAPSHOT)
    laws = {law["knowledge_base_slug"]: law for law in snapshot["laws"]}

    assert snapshot["as_of"] == "2026-10-27"
    assert set(laws) == set(EXPECTED_LAWS)
    assert _sha256(snapshot_payload) == EXPECTED_SNAPSHOT_SHA256
    for slug, (version_id, content_hash, article_count, chunk_count) in EXPECTED_LAWS.items():
        law = laws[slug]
        assert law["version_id"] == version_id
        assert law["content_hash"] == content_hash
        assert law["article_count"] == article_count == len(law["article_ids"])
        assert law["chunk_count"] == chunk_count
        assert law["article_ids"] == sorted(set(law["article_ids"]))
        assert law["article_ids_sha256"] == canonical_json_sha256(law["article_ids"])
        assert law["embedding_fingerprint"] == EXPECTED_EMBEDDING_FINGERPRINT
        assert law["index_schema_version"] == 1


def test_committed_manifest_binds_actual_artifact_and_input_bytes():
    records = load_stage8_dataset(DATASET, require_approved=True)
    snapshot, snapshot_payload = load_stage4_snapshot(SNAPSHOT)
    _, baseline_payload = load_reviewed_baseline(BASELINE)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dataset_payload = DATASET.read_bytes()

    assert manifest["dataset"] == {
        "row_count": 280,
        "sha256": EXPECTED_DATASET_SHA256,
    }
    assert manifest["inputs"] == {
        "reviewed_baseline_sha256": EXPECTED_BASELINE_SHA256,
        "stage4_snapshot_sha256": EXPECTED_SNAPSHOT_SHA256,
    }
    assert _sha256(dataset_payload) == manifest["dataset"]["sha256"]
    assert _sha256(baseline_payload) == manifest["inputs"]["reviewed_baseline_sha256"]
    assert _sha256(snapshot_payload) == manifest["inputs"]["stage4_snapshot_sha256"]
    assert manifest["evidence_count"] == 320
    assert manifest["label_count"] == 460
    generated_at = datetime.fromisoformat(manifest["generated_at"])
    assert generated_at.tzinfo is not None and generated_at.utcoffset() is not None

    evidence_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    for record in records:
        for evidence in record["source_evidence"]:
            slug = evidence["knowledge_base_slug"]
            evidence_counts[slug] += 1
            label_counts[slug] += len(evidence["article_ids"])
    laws = {law["knowledge_base_slug"]: law for law in snapshot["laws"]}
    assert set(manifest["per_slug"]) == set(laws)
    for slug, summary in manifest["per_slug"].items():
        assert summary == {
            "version_id": laws[slug]["version_id"],
            "content_hash": laws[slug]["content_hash"],
            "evidence_count": evidence_counts[slug],
            "label_count": label_counts[slug],
        }
