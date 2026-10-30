"""Provider-independent Stage 8 Judge diagnostic execution helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any

JudgeCallable = Callable[[dict[str, Any]], Mapping[str, Any]]

_INSTRUCTIONS = (
    "仅评估证据忠实度、问题覆盖度、拒答适当性和表达清晰度；"
    "不得独立裁定法律适用结论。输出布尔 decision 与可选 dimensions。"
)


def build_judge_input(review: Mapping[str, Any]) -> dict[str, Any]:
    """Build a blind diagnostic payload that never reveals the human verdict."""
    workflow = review.get("workflow_output")
    if not isinstance(workflow, Mapping):
        raise ValueError("review is missing workflow output")
    identifier = str(review.get("id", ""))
    question = review.get("question")
    answer = workflow.get("answer")
    if not identifier or not isinstance(question, str) or not isinstance(answer, str):
        raise ValueError("review is missing judge input fields")
    return {
        "id": identifier,
        "task_scope": "evidence_fidelity,coverage,abstention,clarity",
        "instructions": _INSTRUCTIONS,
        "question": question,
        "answer": answer,
        "citations": deepcopy(workflow.get("citations", [])),
        "verification_status": workflow.get("verification_status"),
    }


def run_judge_diagnostics(
    reviews: Sequence[Mapping[str, Any]],
    judge: JudgeCallable,
) -> list[dict[str, Any]]:
    """Run a blind Judge callable and retain each provider failure explicitly."""
    results: list[dict[str, Any]] = []
    for review in reviews:
        identifier = str(review.get("id", ""))
        try:
            response = judge(build_judge_input(review))
            decision = response.get("decision")
            dimensions = response.get("dimensions", {})
            if not isinstance(decision, bool) or not isinstance(dimensions, Mapping):
                raise ValueError("invalid judge response")
            results.append(
                {
                    "id": identifier,
                    "status": "completed",
                    "decision": decision,
                    "dimensions": dict(dimensions),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": identifier,
                    "status": "execution_error",
                    "error_type": type(exc).__name__,
                }
            )
    return results
