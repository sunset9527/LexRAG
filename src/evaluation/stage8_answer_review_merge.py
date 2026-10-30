"""Combine successful Stage 8 answer-review runs without changing frozen labels."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import Any


class Stage8AnswerReviewMergeError(ValueError):
    """Answer-review inputs cannot form one complete, auditable review set."""


_WORKFLOW_FIELDS = (
    "answer",
    "citations",
    "verification_status",
    "verification_issues",
    "workflow_trace",
    "attempts",
    "latency_ms",
)


def merge_answer_review_runs(
    sample_records: Sequence[dict[str, Any]],
    initial_run_records: Sequence[dict[str, Any]],
    resume_run_records: Sequence[dict[str, Any]],
    *,
    source_names: tuple[str, str],
) -> list[dict[str, Any]]:
    """Return one pending-human-review row per frozen sample in original order."""
    sample_ids = [str(record.get("id", "")) for record in sample_records]
    if not sample_ids or any(not item for item in sample_ids) or len(sample_ids) != len(set(sample_ids)):
        raise Stage8AnswerReviewMergeError("冻结审核样本 ID 无效或重复")

    completed_by_id: dict[str, tuple[str, dict[str, Any]]] = {}
    for source_name, records in zip(source_names, (initial_run_records, resume_run_records), strict=True):
        for record in records:
            if record.get("status") != "completed":
                continue
            sample_id = str(record.get("sample_id", ""))
            if sample_id not in sample_ids:
                raise Stage8AnswerReviewMergeError(f"运行结果包含未知样本: {sample_id}")
            if sample_id in completed_by_id:
                raise Stage8AnswerReviewMergeError(f"运行结果包含重复完成样本: {sample_id}")
            completed_by_id[sample_id] = (source_name, record)

    missing = [sample_id for sample_id in sample_ids if sample_id not in completed_by_id]
    if missing:
        raise Stage8AnswerReviewMergeError("缺少完成样本: " + "、".join(missing))

    merged = []
    for sample in sample_records:
        sample_id = str(sample["id"])
        source_name, result = completed_by_id[sample_id]
        workflow_output = {field: deepcopy(result.get(field)) for field in _WORKFLOW_FIELDS}
        merged.append(
            {
                **deepcopy(sample),
                "workflow_source": source_name,
                "workflow_output": workflow_output,
                "review_state": "pending",
                "reviewer": "",
                "reviewed_at": "",
                "review_note": "",
                "human_review": None,
            }
        )
    return merged
