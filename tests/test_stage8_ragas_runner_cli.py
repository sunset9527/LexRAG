from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from scripts.run_stage8_ragas import main


def _review(identifier: str) -> dict:
    return {
        "id": identifier,
        "reviewer": "reviewer-a",
        "reviewed_at": "2026-10-30T10:00:00+08:00",
        "review_note": "人工审核完成",
        "human_review": True,
        "question": "成年人是指年满多少周岁？",
        "workflow_output": {
            "answer": "年满十八周岁的自然人为成年人。",
            "citations": [{"original_text": "民法典第十七条：十八周岁以上的自然人为成年人。"}],
        },
    }


def _write_review_fixture(directory: Path) -> tuple[Path, Path]:
    review_path = directory / "review.jsonl"
    review_path.write_text(
        "".join(json.dumps(_review(identifier), ensure_ascii=False) + "\n" for identifier in ("sample-1", "sample-2")),
        encoding="utf-8",
    )
    manifest_path = directory / "review.manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "lexrag.stage8-answer-review-merged",
                "version": 1,
                "result": {"path": review_path.name, "sha256": sha256(review_path.read_bytes()).hexdigest()},
            }
        ),
        encoding="utf-8",
    )
    return review_path, manifest_path


def test_cli_writes_safe_hash_bound_ragas_artifacts_with_injected_evaluator(tmp_path: Path) -> None:
    review_path, manifest_path = _write_review_fixture(tmp_path)
    output_path = tmp_path / "ragas.jsonl"

    exit_code = main(
        [
            "--review",
            str(review_path),
            "--review-manifest",
            str(manifest_path),
            "--output",
            str(output_path),
            "--expected-count",
            "2",
            "--limit",
            "1",
        ],
        environment={"STAGE8_RAGAS_API_KEY": "test-key"},
        evaluator=lambda _record: {"faithfulness": 1.0, "context_precision_without_reference": 0.5},
        ragas_version="0.3.9",
    )

    assert exit_code == 0
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "id": "sample-1",
            "scores": {"context_precision_without_reference": 0.5, "faithfulness": 1.0},
            "status": "completed",
        }
    ]
    config = json.loads(output_path.with_suffix(".config.json").read_text(encoding="utf-8"))
    summary = json.loads(output_path.with_suffix(".summary.json").read_text(encoding="utf-8"))
    assert "api_key" not in json.dumps(config).lower()
    assert config["ragas_version"] == "0.3.9"
    assert summary["status"] == "PARTIAL"
    assert summary["inputs"]["review"]["sha256"] == sha256(review_path.read_bytes()).hexdigest()
    assert summary["unsupported_metric_reasons"]["answer_correctness"] == "reference_answer_missing"


def test_cli_requires_process_local_key_before_creating_output(tmp_path: Path) -> None:
    review_path, manifest_path = _write_review_fixture(tmp_path)
    output_path = tmp_path / "ragas.jsonl"

    assert (
        main(
            [
                "--review",
                str(review_path),
                "--review-manifest",
                str(manifest_path),
                "--output",
                str(output_path),
                "--expected-count",
                "2",
            ],
            environment={},
            evaluator=lambda _record: {"faithfulness": 1.0},
        )
        == 2
    )
    assert not output_path.exists()


def test_cli_retries_only_prior_errors_and_reuses_completed_scores(tmp_path: Path) -> None:
    review_path, manifest_path = _write_review_fixture(tmp_path)
    previous_path = tmp_path / "initial.jsonl"
    previous_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "sample-1",
                        "status": "completed",
                        "scores": {"faithfulness": 0.4, "context_precision_without_reference": 0.7},
                    }
                ),
                json.dumps({"id": "sample-2", "status": "execution_error", "error_type": "APIConnectionError"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "recovered.jsonl"

    exit_code = main(
        [
            "--review",
            str(review_path),
            "--review-manifest",
            str(manifest_path),
            "--output",
            str(output_path),
            "--expected-count",
            "2",
            "--resume-from",
            str(previous_path),
        ],
        environment={"STAGE8_RAGAS_API_KEY": "test-key"},
        evaluator=lambda record: {"faithfulness": 0.9, "context_precision_without_reference": 0.8}
        if record["id"] == "sample-2"
        else (_ for _ in ()).throw(AssertionError("completed sample must not be retried")),
        ragas_version="0.3.9",
    )

    assert exit_code == 0
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["scores"] == {"context_precision_without_reference": 0.7, "faithfulness": 0.4}
    assert rows[1]["scores"] == {"context_precision_without_reference": 0.8, "faithfulness": 0.9}
    summary = json.loads(output_path.with_suffix(".summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "COMPLETE"
    assert summary["counts"] == {"completed": 2, "execution_errors": 0, "selected": 2, "total_reviewed": 2}
    assert summary["recovery"] == {"reused_completed": 1, "retried": 1}
