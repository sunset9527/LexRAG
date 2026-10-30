from __future__ import annotations

from src.evaluation.stage8_judge_runner import build_judge_input, run_judge_diagnostics


def _review(identifier: str, approved: bool) -> dict:
    return {
        "id": identifier,
        "question": "不满八周岁的未成年人属于什么民事行为能力人？",
        "human_review": approved,
        "workflow_output": {
            "answer": "不满八周岁的未成年人为无民事行为能力人。",
            "citations": [{"citation_text": "【中华人民共和国民法典第20条】"}],
            "verification_status": "pass",
        },
    }


def test_judge_input_hides_human_verdict_and_limits_the_evaluation_scope() -> None:
    payload = build_judge_input(_review("sample-1", True))

    assert "human_review" not in payload
    assert payload["id"] == "sample-1"
    assert payload["task_scope"] == "evidence_fidelity,coverage,abstention,clarity"
    assert "不得独立裁定法律适用结论" in payload["instructions"]


def test_judge_runner_preserves_provider_failures_as_execution_errors() -> None:
    results = run_judge_diagnostics(
        [_review("sample-1", True), _review("sample-2", False)],
        lambda item: {"decision": item["id"] == "sample-1", "dimensions": {"clarity": 4}},
    )
    assert results == [
        {
            "id": "sample-1",
            "status": "completed",
            "decision": True,
            "dimensions": {"clarity": 4},
        },
        {
            "id": "sample-2",
            "status": "completed",
            "decision": False,
            "dimensions": {"clarity": 4},
        },
    ]

    failed = run_judge_diagnostics([_review("sample-3", True)], lambda _item: (_ for _ in ()).throw(TimeoutError()))
    assert failed == [{"id": "sample-3", "status": "execution_error", "error_type": "TimeoutError"}]
