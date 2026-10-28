from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from src.evaluation.stage8_answer_review_sampling import select_answer_review_sample


ROOT = Path(__file__).resolve().parents[1]


def _records():
    return [
        json.loads(line)
        for line in (ROOT / "data/evaluation/stage8/stage8_frozen_280.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


def test_answer_review_sample_is_100_rows_and_keeps_every_abstention_row():
    records = _records()

    sample = select_answer_review_sample(records, seed="stage8-answer-review-v1")

    assert len(sample) == 100
    assert {row["id"] for row in sample if row["should_abstain"]} == {
        row["id"] for row in records if row["should_abstain"]
    }
    answerable_types = Counter(
        row["question_type"] for row in sample if not row["should_abstain"]
    )
    assert answerable_types == {
        "baseline_direct_lookup": 31,
        "oral_without_law_name": 15,
        "adjacent_or_confusable": 12,
        "cross_law": 12,
        "multi_hop": 10,
    }


def test_answer_review_sample_is_deterministic_and_returns_blank_human_fields():
    records = _records()

    first = select_answer_review_sample(records, seed="stage8-answer-review-v1")
    second = select_answer_review_sample(records, seed="stage8-answer-review-v1")

    assert first == second
    assert all(
        row["review_state"] == "pending"
        and row["reviewer"] == ""
        and row["reviewed_at"] == ""
        and row["review_note"] == ""
        and row["human_review"] is None
        for row in first
    )
