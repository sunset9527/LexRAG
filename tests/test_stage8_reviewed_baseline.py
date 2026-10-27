"""Contract tests for the read-only Stage 8 reviewed-candidate baseline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_stage8_reviewed_baseline as baseline_cli
from src.evaluation.stage8_reviewed_baseline import (
    Stage8ReviewedBaselineError,
    build_reviewed_baseline,
    canonical_content_sha256,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "evaluation" / "stage8"
SNAPSHOTS = DATA / "snapshots"


def test_actual_reviewed_inputs_build_a_280_candidate_baseline() -> None:
    baseline, scope = build_reviewed_baseline(
        SNAPSHOTS / "review_queue_300.reviewed.jsonl",
        SNAPSHOTS / "round2_candidates_171.reviewed.jsonl",
        DATA / "round2_remediation_manifest.json",
        SNAPSHOTS / "review_queue_300.pending.jsonl",
        SNAPSHOTS / "round2_candidates_171.pending.jsonl",
    )

    assert len(baseline) == 280
    assert [row["queue_id"] for row in baseline[:109]] == [
        row["queue_id"]
        for row in map(json.loads, (SNAPSHOTS / "review_queue_300.reviewed.jsonl").read_text(encoding="utf-8").splitlines())
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
    assert scope["sha256"]["baseline_jsonl"] == canonical_content_sha256(baseline_path)
    assert scope["sources"]["first_reviewed"].startswith("data/evaluation/stage8/snapshots/")
    assert set(scope["sha256"]) == {
        "baseline_jsonl", "first_reviewed", "first_pending", "second_reviewed", "second_pending", "remediation_manifest"
    }
    assert scope["sha256_method"] == "SHA-256 of UTF-8 text content after CRLF/CR-to-LF normalization"


def test_loader_rejects_duplicate_keys_and_unsupported_queue_fields(tmp_path: Path) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    manifest = tmp_path / "manifest.json"
    first.write_text('{"queue_id":"x","queue_id":"y"}\n', encoding="utf-8")
    second.write_text("", encoding="utf-8")
    manifest.write_text('{"lineage": []}', encoding="utf-8")
    with pytest.raises(Stage8ReviewedBaselineError, match="重复 JSON 键"):
        build_reviewed_baseline(first, second, manifest, first, second)


def test_canonical_content_sha256_treats_lf_and_crlf_as_same_utf8_content(tmp_path: Path) -> None:
    lf = tmp_path / "lf.jsonl"; crlf = tmp_path / "crlf.jsonl"
    lf.write_bytes("{\"queue_id\":\"例\"}\nnext\n".encode("utf-8"))
    crlf.write_bytes("{\"queue_id\":\"例\"}\r\nnext\r\n".encode("utf-8"))
    assert canonical_content_sha256(lf) == canonical_content_sha256(crlf)


def test_builder_rejects_queue_id_collision_across_review_rounds(tmp_path: Path) -> None:
    second = tmp_path / "second.jsonl"
    rows = (SNAPSHOTS / "round2_candidates_171.reviewed.jsonl").read_text(encoding="utf-8").splitlines()
    changed = json.loads(rows[0]); changed["queue_id"] = "civil-001"
    second.write_text("\n".join([json.dumps(changed, ensure_ascii=False), *rows[1:]]) + "\n", encoding="utf-8")
    with pytest.raises(Stage8ReviewedBaselineError, match="跨轮.*queue_id"):
        build_reviewed_baseline(
            SNAPSHOTS / "review_queue_300.reviewed.jsonl", second, DATA / "round2_remediation_manifest.json",
            SNAPSHOTS / "review_queue_300.pending.jsonl", SNAPSHOTS / "round2_candidates_171.pending.jsonl",
        )


def test_cli_rejects_equal_output_paths(tmp_path: Path) -> None:
    output = tmp_path / "same.json"
    assert baseline_cli.main(["--baseline-output", str(output), "--scope-output", str(output)]) == 1
    assert not output.exists()


def test_cli_restores_both_outputs_when_second_replacement_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = tmp_path / "baseline.jsonl"; scope = tmp_path / "scope.json"
    baseline.write_text("old baseline\n", encoding="utf-8"); scope.write_text("old scope\n", encoding="utf-8")
    original_replace = baseline_cli.os.replace
    def fail_scope_replace(source: str, destination: str) -> None:
        if Path(destination) == scope: raise OSError("simulated scope replacement failure")
        original_replace(source, destination)
    monkeypatch.setattr(baseline_cli.os, "replace", fail_scope_replace)
    assert baseline_cli.main(["--baseline-output", str(baseline), "--scope-output", str(scope)]) == 1
    assert baseline.read_text(encoding="utf-8") == "old baseline\n"
    assert scope.read_text(encoding="utf-8") == "old scope\n"

