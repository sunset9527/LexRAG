from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from src.evaluation.stage8_diagnostic_calibration import (
    Stage8DiagnosticCalibrationError,
    build_calibration_report,
    load_completed_answer_reviews,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _review_row(identifier: str, approved: bool) -> dict:
    return {
        "id": identifier,
        "reviewer": "reviewer-a",
        "reviewed_at": "2026-10-29T22:31:04+08:00",
        "review_note": "人工审核完成",
        "human_review": approved,
        "workflow_output": {"answer": "受测回答", "citations": []},
    }


def _manifest_for(path: Path) -> dict:
    return {
        "schema": "lexrag.stage8-answer-review-merged",
        "version": 1,
        "result": {"path": path.name, "sha256": sha256(path.read_bytes()).hexdigest()},
    }


def test_loader_rejects_incomplete_review_and_manifest_mismatch(tmp_path: Path) -> None:
    review_path = tmp_path / "review.jsonl"
    _write_jsonl(review_path, [_review_row("sample-1", True), _review_row("sample-2", False)])
    manifest_path = tmp_path / "review.manifest.json"
    manifest_path.write_text(json.dumps(_manifest_for(review_path)), encoding="utf-8")

    rows = load_completed_answer_reviews(review_path, manifest_path, expected_count=2)
    assert [row["id"] for row in rows] == ["sample-1", "sample-2"]

    incomplete = _review_row("sample-3", True)
    incomplete["reviewer"] = ""
    _write_jsonl(review_path, [_review_row("sample-1", True), incomplete])
    manifest_path.write_text(json.dumps(_manifest_for(review_path)), encoding="utf-8")
    with pytest.raises(Stage8DiagnosticCalibrationError, match="审核字段不完整"):
        load_completed_answer_reviews(review_path, manifest_path, expected_count=2)

    manifest_path.write_text(
        json.dumps({**_manifest_for(review_path), "result": {"path": review_path.name, "sha256": "bad"}}),
        encoding="utf-8",
    )
    with pytest.raises(Stage8DiagnosticCalibrationError, match="哈希"):
        load_completed_answer_reviews(review_path, manifest_path, expected_count=2)


def test_loader_accepts_hash_bound_reviewed_manifest(tmp_path: Path) -> None:
    review_path = tmp_path / "review.jsonl"
    _write_jsonl(review_path, [_review_row("sample-1", True), _review_row("sample-2", False)])
    manifest_path = tmp_path / "review.review_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "lexrag.stage8-answer-review-reviewed",
                "version": 1,
                "reviewed_file": {"path": review_path.name, "sha256": sha256(review_path.read_bytes()).hexdigest()},
            }
        ),
        encoding="utf-8",
    )

    rows = load_completed_answer_reviews(review_path, manifest_path, expected_count=2)

    assert [row["id"] for row in rows] == ["sample-1", "sample-2"]


def test_calibration_preserves_execution_errors_in_total_and_confusion_counts() -> None:
    reviews = [_review_row("sample-1", True), _review_row("sample-2", False), _review_row("sample-3", True)]
    judge_rows = [
        {"id": "sample-1", "status": "completed", "decision": True},
        {"id": "sample-2", "status": "completed", "decision": True},
        {"id": "sample-3", "status": "execution_error", "error_type": "TimeoutError"},
    ]

    report = build_calibration_report(
        reviews,
        judge_rows,
        evaluator={"kind": "judge", "model": "example-model", "temperature": 0},
    )

    assert report["status"] == "INCOMPLETE"
    assert report["counts"] == {"total": 3, "evaluable": 2, "execution_errors": 1}
    assert report["agreement_rate"] == 0.5
    assert report["confusion_matrix"] == {"true_positive": 1, "true_negative": 0, "false_positive": 1, "false_negative": 0}
    assert report["error_ids"] == ["sample-3"]


def test_calibration_rejects_secret_bearing_configuration_and_duplicate_judge_rows() -> None:
    reviews = [_review_row("sample-1", True)]

    with pytest.raises(Stage8DiagnosticCalibrationError, match="敏感配置"):
        build_calibration_report(
            reviews,
            [{"id": "sample-1", "status": "completed", "decision": True}],
            evaluator={"kind": "judge", "api_key": "not-allowed"},
        )

    with pytest.raises(Stage8DiagnosticCalibrationError, match="重复"):
        build_calibration_report(
            reviews,
            [
                {"id": "sample-1", "status": "completed", "decision": True},
                {"id": "sample-1", "status": "completed", "decision": False},
            ],
            evaluator={"kind": "judge", "model": "example-model"},
        )
