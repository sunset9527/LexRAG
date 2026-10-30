from __future__ import annotations

from src.evaluation.stage8_ragas_runner import run_ragas_diagnostics


def test_runner_keeps_each_metric_result_and_provider_error_per_sample() -> None:
    records = [
        {"id": "sample-1", "user_input": "问题一", "response": "回答一", "retrieved_contexts": ["证据一"]},
        {"id": "sample-2", "user_input": "问题二", "response": "回答二", "retrieved_contexts": ["证据二"]},
    ]

    def evaluator(record: dict) -> dict[str, float]:
        if record["id"] == "sample-2":
            raise TimeoutError("provider timeout")
        return {"faithfulness": 1.0, "context_precision_without_reference": 0.5}

    assert run_ragas_diagnostics(records, evaluator) == [
        {
            "id": "sample-1",
            "status": "completed",
            "scores": {"faithfulness": 1.0, "context_precision_without_reference": 0.5},
        },
        {"id": "sample-2", "status": "execution_error", "error_type": "TimeoutError"},
    ]


def test_runner_rejects_duplicate_ids_and_non_numeric_scores() -> None:
    duplicate = [{"id": "same"}, {"id": "same"}]
    try:
        run_ragas_diagnostics(duplicate, lambda _record: {"faithfulness": 1.0})
    except ValueError as exc:
        assert "重复" in str(exc)
    else:
        raise AssertionError("duplicate ids must be rejected")

    try:
        run_ragas_diagnostics([{"id": "sample"}], lambda _record: {"faithfulness": "not-a-score"})
    except ValueError as exc:
        assert "数值" in str(exc)
    else:
        raise AssertionError("non-numeric score must be rejected")
