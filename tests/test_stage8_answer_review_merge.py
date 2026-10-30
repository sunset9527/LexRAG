from __future__ import annotations

import pytest

from src.evaluation.stage8_answer_review_merge import (
    Stage8AnswerReviewMergeError,
    merge_answer_review_runs,
)


def _sample(identifier: str) -> dict:
    return {
        "id": identifier,
        "question": f"{identifier} 的问题",
        "review_state": "pending",
        "reviewer": "",
        "reviewed_at": "",
        "review_note": "",
        "human_review": None,
    }


def _completed(identifier: str, answer: str) -> dict:
    return {
        "sample_id": identifier,
        "status": "completed",
        "answer": answer,
        "citations": [],
        "verification_status": "pass",
        "verification_issues": [],
        "workflow_trace": [],
        "attempts": 1,
        "latency_ms": 12.3,
    }


def test_merge_preserves_sample_order_and_uses_resume_for_prior_execution_errors() -> None:
    result = merge_answer_review_runs(
        [_sample("civil-001"), _sample("civil-002")],
        [
            _completed("civil-001", "首轮答案"),
            {"sample_id": "civil-002", "status": "execution_error", "error_type": "TimeoutError"},
        ],
        [_completed("civil-002", "补跑答案")],
        source_names=("initial.jsonl", "resume.jsonl"),
    )

    assert [row["id"] for row in result] == ["civil-001", "civil-002"]
    assert result[0]["workflow_output"]["answer"] == "首轮答案"
    assert result[0]["workflow_source"] == "initial.jsonl"
    assert result[1]["workflow_output"]["answer"] == "补跑答案"
    assert result[1]["workflow_source"] == "resume.jsonl"
    assert all(row["review_state"] == "pending" for row in result)
    assert all(row["human_review"] is None for row in result)


def test_merge_rejects_missing_or_duplicate_completed_samples() -> None:
    with pytest.raises(Stage8AnswerReviewMergeError, match="缺少"):
        merge_answer_review_runs(
            [_sample("civil-001"), _sample("civil-002")],
            [_completed("civil-001", "首轮答案")],
            [],
            source_names=("initial.jsonl", "resume.jsonl"),
        )

    with pytest.raises(Stage8AnswerReviewMergeError, match="重复"):
        merge_answer_review_runs(
            [_sample("civil-001")],
            [_completed("civil-001", "首轮答案")],
            [_completed("civil-001", "补跑答案")],
            source_names=("initial.jsonl", "resume.jsonl"),
        )
