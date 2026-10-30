from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from scripts.run_stage8_judge import build_judge_messages, main


def test_judge_messages_explicitly_request_json_object_output() -> None:
    messages = build_judge_messages({"id": "sample-1", "question": "问题"})

    assert messages[0]["role"] == "system"
    assert "json" in messages[0]["content"].lower()
    assert '"decision"' in messages[0]["content"]
    assert '"dimensions"' in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "json" in messages[1]["content"].lower()


def test_judge_cli_writes_credential_free_rows_with_injected_judge(tmp_path: Path) -> None:
    review_path = tmp_path / "review.jsonl"
    review_path.write_text(
        json.dumps(
            {
                "id": "sample-1",
                "question": "问题",
                "reviewer": "reviewer-a",
                "reviewed_at": "2026-10-29T22:31:04+08:00",
                "review_note": "完成",
                "human_review": True,
                "workflow_output": {"answer": "回答", "citations": []},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "review.manifest.json"
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
    output_path = tmp_path / "judge.jsonl"
    secret = "stage8-judge-secret"

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
                "1",
            ],
            environment={"STAGE8_JUDGE_API_KEY": secret},
            judge=lambda item: {"decision": True, "dimensions": {"clarity": 4}},
        )
        == 0
    )

    serialized = output_path.read_text(encoding="utf-8")
    assert '"status": "completed"' in serialized
    assert secret not in serialized
