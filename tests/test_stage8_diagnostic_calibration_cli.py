from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from scripts.run_stage8_diagnostic_calibration import main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _review(identifier: str, decision: bool) -> dict:
    return {
        "id": identifier,
        "reviewer": "reviewer-a",
        "reviewed_at": "2026-10-29T22:31:04+08:00",
        "review_note": "人工审核完成",
        "human_review": decision,
        "workflow_output": {"answer": "受测回答", "citations": []},
    }


def _write_manifest(path: Path, review_path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "lexrag.stage8-answer-review-merged",
                "version": 1,
                "result": {"path": review_path.name, "sha256": sha256(review_path.read_bytes()).hexdigest()},
            }
        ),
        encoding="utf-8",
    )


def test_cli_writes_hash_bound_calibration_report(tmp_path: Path) -> None:
    review_path = tmp_path / "review.jsonl"
    manifest_path = tmp_path / "review.manifest.json"
    judge_path = tmp_path / "judge.jsonl"
    config_path = tmp_path / "judge-config.json"
    output_path = tmp_path / "report.json"
    _write_jsonl(review_path, [_review("sample-1", True), _review("sample-2", False)])
    _write_manifest(manifest_path, review_path)
    _write_jsonl(
        judge_path,
        [
            {"id": "sample-1", "status": "completed", "decision": True},
            {"id": "sample-2", "status": "execution_error", "error_type": "TimeoutError"},
        ],
    )
    config_path.write_text(json.dumps({"kind": "judge", "model": "example-model"}), encoding="utf-8")

    exit_code = main(
        [
            "--review",
            str(review_path),
            "--review-manifest",
            str(manifest_path),
            "--evaluator-results",
            str(judge_path),
            "--evaluator-config",
            str(config_path),
            "--output",
            str(output_path),
            "--expected-count",
            "2",
        ]
    )

    assert exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "INCOMPLETE"
    assert report["inputs"]["review"]["sha256"] == sha256(review_path.read_bytes()).hexdigest()
    assert report["inputs"]["evaluator_results"]["sha256"] == sha256(judge_path.read_bytes()).hexdigest()
    assert report["counts"]["execution_errors"] == 1


def test_cli_refuses_secret_bearing_config_without_creating_report(tmp_path: Path) -> None:
    review_path = tmp_path / "review.jsonl"
    manifest_path = tmp_path / "review.manifest.json"
    judge_path = tmp_path / "judge.jsonl"
    config_path = tmp_path / "unsafe-config.json"
    output_path = tmp_path / "report.json"
    _write_jsonl(review_path, [_review("sample-1", True)])
    _write_manifest(manifest_path, review_path)
    _write_jsonl(judge_path, [{"id": "sample-1", "status": "completed", "decision": True}])
    config_path.write_text(json.dumps({"kind": "judge", "api_key": "unsafe"}), encoding="utf-8")

    assert (
        main(
            [
                "--review",
                str(review_path),
                "--review-manifest",
                str(manifest_path),
                "--evaluator-results",
                str(judge_path),
                "--evaluator-config",
                str(config_path),
                "--output",
                str(output_path),
                "--expected-count",
                "1",
            ]
        )
        == 2
    )
    assert not output_path.exists()
