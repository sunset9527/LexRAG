"""Contract tests for the read-only Stage 8 reviewed-candidate baseline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.evaluation.stage8_reviewed_baseline import (
    Stage8ReviewedBaselineError,
    build_reviewed_baseline,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "evaluation" / "stage8"


def test_actual_reviewed_inputs_build_a_280_candidate_baseline() -> None:
    baseline, scope = build_reviewed_baseline(
        DATA / "review_queue_300.jsonl",
        DATA / "round2_candidates_171.jsonl",
        DATA / "round2_remediation_manifest.json",
        DATA / "review_queue_300.pending.bak.jsonl",
        DATA / "round2_candidates_171.pending.bak.jsonl",
    )

    assert len(baseline) == 280
    assert [row["queue_id"] for row in baseline[:109]] == [
        row["queue_id"]
        for row in map(json.loads, (DATA / "review_queue_300.jsonl").read_text(encoding="utf-8").splitlines())
        if row["review_state"] == "approved"
    ]
    assert scope["kind"] == "reviewed_candidate_baseline"
    assert scope["target_count"] == 280
    assert scope["retired_count"] == 20
    assert len(scope["retired_source_ids"]) == 20
    assert all(item["status"] == "retired_by_scope_decision" for item in scope["retired_source_ids"])
    assert {item["source_queue_id"] for item in scope["retired_source_ids"]} == {
        f"hard-version-{n:03d}" for n in range(1, 21)
    }
    assert scope["human_evidence_supported_corrections"]["count"] == 11
    assert "present-law" in scope["limitations"].lower()
    assert "source_url" not in "\n".join(json.dumps(row, ensure_ascii=False) for row in baseline)


def test_committed_artifacts_match_the_actual_reviewed_build() -> None:
    baseline_path = DATA / "stage8_reviewed_baseline_280.jsonl"
    scope_path = DATA / "stage8_scope_280.json"
    rows = [json.loads(line) for line in baseline_path.read_text(encoding="utf-8").splitlines()]
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    assert len(rows) == 280
    assert not any(row["queue_id"].startswith("hard-version-") for row in rows)
    assert scope["target_count"] == 280 and scope["retired_count"] == 20
    assert scope["sha256"]["baseline_jsonl"] == hashlib.sha256(baseline_path.read_bytes()).hexdigest()


def test_loader_rejects_duplicate_keys_and_unsupported_queue_fields(tmp_path: Path) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    manifest = tmp_path / "manifest.json"
    first.write_text('{"queue_id":"x","queue_id":"y"}\n', encoding="utf-8")
    second.write_text("", encoding="utf-8")
    manifest.write_text('{"lineage": []}', encoding="utf-8")
    with pytest.raises(Stage8ReviewedBaselineError, match="重复 JSON 键"):
        build_reviewed_baseline(first, second, manifest, first, second)

