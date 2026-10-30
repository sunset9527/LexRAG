"""Failure-preserving execution helpers for the optional Stage 8 Ragas run."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from math import isfinite
from typing import Any


RagasEvaluator = Callable[[Mapping[str, Any]], Mapping[str, float]]


def run_ragas_diagnostics(
    records: Sequence[Mapping[str, Any]],
    evaluator: RagasEvaluator,
) -> list[dict[str, Any]]:
    """Evaluate records one by one without silently dropping provider failures."""
    identifiers: set[str] = set()
    results: list[dict[str, Any]] = []
    for record in records:
        identifier = str(record.get("id", ""))
        if not identifier or identifier in identifiers:
            raise ValueError("Ragas 样本 ID 无效或重复")
        identifiers.add(identifier)
        try:
            raw_scores = evaluator(record)
        except Exception as exc:  # Provider failures must remain observable evidence.
            results.append({"id": identifier, "status": "execution_error", "error_type": type(exc).__name__})
        else:
            scores = _validate_scores(raw_scores)
            results.append({"id": identifier, "status": "completed", "scores": scores})
    return results


def _validate_scores(raw_scores: Mapping[str, float]) -> dict[str, float]:
    if not raw_scores:
        raise ValueError("Ragas 未返回指标分数")
    scores: dict[str, float] = {}
    for name, value in raw_scores.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
            raise ValueError("Ragas 指标分数必须为有限数值")
        scores[str(name)] = float(value)
    return scores
