from __future__ import annotations

import pytest

from src.evaluation.stage8_ragas_input import Stage8RagasInputError, materialize_ragas_records


def _review() -> dict:
    return {
        "id": "civil-001",
        "question": "成年人是指年满多少周岁？",
        "should_abstain": False,
        "workflow_output": {
            "answer": "年满十八周岁的自然人为成年人。",
            "citations": [
                {"original_text": "民法典第十七条：十八周岁以上的自然人为成年人。"},
                {"original_text": "民法典第十七条：十八周岁以上的自然人为成年人。"},
            ],
        },
    }


def test_materializer_builds_only_supported_ragas_fields_without_inventing_reference_answer() -> None:
    result = materialize_ragas_records([_review()])

    assert result["records"] == [
        {
            "id": "civil-001",
            "user_input": "成年人是指年满多少周岁？",
            "response": "年满十八周岁的自然人为成年人。",
            "retrieved_contexts": ["民法典第十七条：十八周岁以上的自然人为成年人。"],
        }
    ]
    assert result["unsupported_metrics"] == [
        "answer_correctness",
        "context_recall",
        "factual_correctness",
    ]
    assert result["supported_metrics"] == ["context_precision_without_reference", "faithfulness"]
    assert result["unsupported_metric_reasons"] == {
        "answer_correctness": "reference_answer_missing",
        "answer_relevancy": "embedding_configuration_missing",
        "context_recall": "reference_answer_missing",
        "factual_correctness": "reference_answer_missing",
    }


def test_materializer_rejects_missing_answer_or_retrieved_evidence() -> None:
    missing_answer = _review()
    missing_answer["workflow_output"]["answer"] = ""
    with pytest.raises(Stage8RagasInputError, match="回答"):
        materialize_ragas_records([missing_answer])

    missing_context = _review()
    missing_context["workflow_output"]["citations"] = []
    with pytest.raises(Stage8RagasInputError, match="检索证据"):
        materialize_ragas_records([missing_context])
