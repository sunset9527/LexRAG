"""Deterministic, label-preserving Stage 8 full-answer review sampling."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any


class Stage8AnswerReviewSamplingError(ValueError):
    """The frozen records cannot form the declared review sample."""


_ANSWERABLE_QUOTAS = {
    "baseline_direct_lookup": 31,
    "oral_without_law_name": 15,
    "adjacent_or_confusable": 12,
    "cross_law": 12,
    "multi_hop": 10,
}


def _stable_rank(seed: str, record_id: str) -> str:
    return hashlib.sha256(f"{seed}:{record_id}".encode("utf-8")).hexdigest()


def _review_record(record: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(record)
    result.update(
        {
            "review_state": "pending",
            "reviewer": "",
            "reviewed_at": "",
            "review_note": "",
            "human_review": None,
        }
    )
    return result


def _balanced_type_sample(rows: list[dict[str, Any]], quota: int, seed: str) -> list[dict[str, Any]]:
    """Select a type quota while balancing available difficulty and law coverage."""
    available_difficulty = Counter(str(row["difficulty"]) for row in rows)
    available_slug = Counter(
        slug for row in rows for slug in row["expected_knowledge_base_slugs"]
    )
    selected_difficulty: Counter[str] = Counter()
    selected_slug: Counter[str] = Counter()
    remaining = list(rows)
    selected = []
    for _ in range(quota):
        if not remaining:
            raise Stage8AnswerReviewSamplingError("question type has insufficient rows")

        def priority(row: dict[str, Any]):
            difficulty = str(row["difficulty"])
            slugs = row["expected_knowledge_base_slugs"]
            difficulty_share = selected_difficulty[difficulty] / available_difficulty[difficulty]
            slug_share = min(selected_slug[slug] / available_slug[slug] for slug in slugs)
            return (difficulty_share, slug_share, _stable_rank(seed, str(row["id"])))

        chosen = min(remaining, key=priority)
        remaining.remove(chosen)
        selected.append(chosen)
        selected_difficulty[str(chosen["difficulty"])] += 1
        selected_slug.update(chosen["expected_knowledge_base_slugs"])
    return selected


def select_answer_review_sample(records: list[dict[str, Any]], *, seed: str) -> list[dict[str, Any]]:
    """Return 100 pending review rows without changing frozen legal labels."""
    if not isinstance(seed, str) or not seed.strip():
        raise Stage8AnswerReviewSamplingError("seed must be nonblank")
    ids = [row.get("id") for row in records]
    if len(records) != 280 or any(not isinstance(value, str) or not value for value in ids):
        raise Stage8AnswerReviewSamplingError("requires the complete 280-row frozen dataset")
    if len(set(ids)) != len(ids):
        raise Stage8AnswerReviewSamplingError("frozen dataset contains duplicate IDs")

    abstentions = [row for row in records if row.get("should_abstain") is True]
    answerable = [row for row in records if row.get("should_abstain") is False]
    if len(abstentions) != 20 or len(answerable) != 260:
        raise Stage8AnswerReviewSamplingError("frozen abstention/answerable counts differ")
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in answerable:
        by_type[str(row.get("question_type"))].append(row)
    if set(by_type) != set(_ANSWERABLE_QUOTAS):
        raise Stage8AnswerReviewSamplingError("answerable question types differ from formal contract")

    selected = list(abstentions)
    for question_type, quota in _ANSWERABLE_QUOTAS.items():
        selected.extend(_balanced_type_sample(by_type[question_type], quota, seed))
    if len(selected) != 100:
        raise Stage8AnswerReviewSamplingError("sample size is not 100")
    return [_review_record(row) for row in sorted(selected, key=lambda row: str(row["id"]))]
