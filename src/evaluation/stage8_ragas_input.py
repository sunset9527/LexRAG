"""Materialize truthful Ragas inputs from completed Stage 8 answer reviews."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class Stage8RagasInputError(ValueError):
    """A completed answer review lacks evidence required for Ragas input."""


_REFERENCE_REQUIRED_METRICS = ["answer_correctness", "context_recall", "factual_correctness"]
_SUPPORTED_METRICS = ["context_precision_without_reference", "faithfulness"]
_UNSUPPORTED_METRIC_REASONS = {
    "answer_correctness": "reference_answer_missing",
    "answer_relevancy": "embedding_configuration_missing",
    "context_recall": "reference_answer_missing",
    "factual_correctness": "reference_answer_missing",
}


def materialize_ragas_records(reviews: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return Ragas-ready records without inventing reference answers.

    The Stage 8 review artifact contains real retrieved citation text but no
    independently authored gold answer. Metrics that require such a reference
    therefore remain explicitly unsupported rather than receiving fabricated
    values derived from statutes or model output.
    """
    records: list[dict[str, Any]] = []
    for review in reviews:
        identifier = str(review.get("id", ""))
        question = review.get("question")
        workflow = review.get("workflow_output")
        if not identifier or not isinstance(question, str) or not question.strip():
            raise Stage8RagasInputError("审核样本缺少问题")
        if not isinstance(workflow, Mapping):
            raise Stage8RagasInputError("审核样本缺少工作流输出")
        answer = workflow.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise Stage8RagasInputError("审核样本缺少回答")
        citations = workflow.get("citations")
        if not isinstance(citations, list):
            raise Stage8RagasInputError("审核样本缺少检索证据")
        contexts: list[str] = []
        for citation in citations:
            if not isinstance(citation, Mapping):
                continue
            text = citation.get("original_text")
            if isinstance(text, str) and text.strip() and text not in contexts:
                contexts.append(text)
        if not contexts:
            raise Stage8RagasInputError("审核样本缺少检索证据")
        records.append(
            {
                "id": identifier,
                "user_input": question,
                "response": answer,
                "retrieved_contexts": contexts,
            }
        )
    if not records:
        raise Stage8RagasInputError("审核样本为空")
    return {
        "records": records,
        "supported_metrics": _SUPPORTED_METRICS.copy(),
        "unsupported_metrics": _REFERENCE_REQUIRED_METRICS.copy(),
        "unsupported_metric_reasons": _UNSUPPORTED_METRIC_REASONS.copy(),
    }
