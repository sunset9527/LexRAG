"""Pure Stage 8 ranking/routing evaluation with no model or database access."""

import json
import math
from pathlib import Path

import pytest

from src.evaluation.stage8_dataset import Stage8DatasetError, load_stage8_dataset


def record(identifier="single", labels=None, *, abstain=False, difficulty="easy"):
    labels = labels or {"civil-code": ["article-1", "article-2"]}
    if abstain:
        labels = {slug: [] for slug in labels}
    return {
        "id": identifier,
        "question": identifier,
        "question_type": "cross_law" if len(labels) > 1 else "direct_lookup",
        "difficulty": difficulty,
        "expected_knowledge_base_slugs": list(labels),
        "relevant_article_ids": [article for articles in labels.values() for article in articles],
        "should_abstain": abstain,
        "source_evidence": [
            {
                "knowledge_base_slug": slug,
                "version_id": slug + "@2026",
                "effective_from": "2026-01-01",
                "effective_to": None,
                "source_url": "https://flk.npc.gov.cn/detail.html",
                "content_hash": "a" * 64,
                "article_ids": articles,
                "source_locator": "official text",
            }
            for slug, articles in labels.items()
        ],
        "reviewer": "reviewer-a",
        "reviewed_at": "2026-10-26T10:30:00+08:00",
        "review_note": "Verified against official text.",
        "review_status": "approved",
    }


def hits(slug, *articles):
    return [{"knowledge_base_slug": slug, "article_id": article} for article in articles]


def test_oracle_scores_exact_labels_and_article_ranks_without_duplicate_inflation():
    from src.evaluation.stage8_retrieval_evaluation import evaluate_oracle_retrieval

    calls = []

    def retrieve(question, slug, k):
        calls.append((question, slug, k))
        return [
            *hits("wrong-law", "article-1"),
            *hits(slug, "article-1", "article-1", "miss", "article-2"),
        ]

    result = evaluate_oracle_retrieval([record()], retrieve)
    metrics = result["overall"]
    assert result["metric_semantics"]["rank_scope"] == "within_each_knowledge_base"
    assert (
        result["metric_semantics"]["cross_law_mrr"]
        == "reciprocal_minimum_relevant_within_law_rank_at_5"
    )
    assert calls == [("single", "civil-code", 5)]
    assert metrics["scored_count"] == 1
    assert metrics["recall_at_1"] == 0
    assert metrics["recall_at_3"] == 0.5
    assert metrics["recall_at_5"] == 1
    assert metrics["mrr_at_5"] == 0.5
    assert metrics["ndcg_at_5"] == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3))
    )
    item = result["items"][0]
    assert item["first_relevant_rank"] == 2
    assert item["included_in_metrics"] is True
    assert item["expected_labels"] == hits("civil-code", "article-1", "article-2")
    assert len(item["ranked_evidence_by_knowledge_base"]["civil-code"]) == 4
    assert result["by_knowledge_base"]["civil-code"] == metrics
    assert result["by_question_type"]["direct_lookup"] == metrics
    assert result["by_difficulty"]["easy"] == metrics


def test_cross_law_scores_complete_labels_and_per_law_lists():
    from src.evaluation.stage8_retrieval_evaluation import evaluate_oracle_retrieval

    calls = []

    def retrieve(question, slug, k):
        calls.append(slug)
        return hits(slug, "article-a") if slug == "law-a" else hits("law-a", "article-b")

    row = record("cross", {"law-a": ["article-a"], "law-b": ["article-b"]}, difficulty="hard")
    result = evaluate_oracle_retrieval([row], retrieve)
    assert calls == ["law-a", "law-b"]
    assert result["overall"]["recall_at_1"] == 0.5
    assert result["overall"]["ndcg_at_5"] == 0.5
    assert result["by_knowledge_base"]["law-a"]["recall_at_5"] == 1
    assert result["by_knowledge_base"]["law-b"]["recall_at_5"] == 0
    assert result["by_question_type"]["cross_law"]["scored_count"] == 1


def test_oracle_abstentions_and_partial_failure_are_explicit_and_not_scored():
    from src.evaluation.stage8_retrieval_evaluation import evaluate_oracle_retrieval

    calls = []

    def retrieve(question, slug, k):
        calls.append((question, slug))
        if slug == "law-b":
            raise RuntimeError("collection unavailable")
        return hits(slug, "article-a")

    rows = [
        record("skip", abstain=True),
        record("fail", {"law-a": ["article-a"], "law-b": ["article-b"]}),
    ]
    result = evaluate_oracle_retrieval(rows, retrieve)
    assert calls == [("fail", "law-a"), ("fail", "law-b")]
    assert result["overall"]["scored_count"] == 0
    assert result["overall"]["recall_at_5"] is None
    assert result["overall"]["excluded_abstention_count"] == 1
    assert result["overall"]["execution_error_count"] == 1
    skip, failure = result["items"]
    assert skip["status"] == "excluded_abstention"
    assert skip["included_in_metrics"] is False
    assert skip["exclusion_reason"] == "should_abstain"
    assert failure["status"] == "execution_error"
    assert failure["exclusion_reason"] == "execution_error"
    assert failure["execution_errors"] == [
        {
            "knowledge_base_slug": "law-b",
            "error_type": "RuntimeError",
            "message": "collection unavailable",
        }
    ]
    assert failure["ranked_evidence_by_knowledge_base"]["law-a"] == hits("law-a", "article-a")
    assert result["by_knowledge_base"]["law-a"]["scored_count"] == 0
    json.dumps(result, allow_nan=False)


def test_oracle_rejects_unapproved_or_malformed_input_before_any_retrieval():
    from src.evaluation.stage8_retrieval_evaluation import evaluate_oracle_retrieval

    invalid = record("invalid")
    invalid["review_status"] = "pending"
    calls = []
    with pytest.raises(Stage8DatasetError, match="approved"):
        evaluate_oracle_retrieval([record(), invalid], lambda *args: calls.append(args))
    assert calls == []


def test_oracle_empty_and_malformed_results_are_distinct_from_abstention():
    from src.evaluation.stage8_retrieval_evaluation import evaluate_oracle_retrieval

    result = evaluate_oracle_retrieval([record()], lambda *args: [])
    assert result["overall"]["scored_count"] == 1
    assert result["overall"]["recall_at_5"] == 0
    assert result["overall"]["mrr_at_5"] == 0
    assert result["items"][0]["first_relevant_rank"] is None
    result = evaluate_oracle_retrieval([record()], lambda *args: [{"article_id": "article-1"}])
    assert result["overall"]["execution_error_count"] == 1
    assert result["overall"]["scored_count"] == 0


def test_routing_single_top1_and_cross_law_candidate_recall_have_separate_denominators():
    from src.evaluation.stage8_retrieval_evaluation import evaluate_routing

    rows = [record("single"), record("cross", {"law-a": ["article-a"], "law-b": ["article-b"]})]
    result = evaluate_routing(
        rows, lambda query: ["wrong", "civil-code"] if query == "single" else ["law-a", "law-a"]
    )
    metrics = result["overall"]
    assert metrics["single_law_scored_count"] == 1
    assert metrics["top_1_accuracy"] == 0
    assert metrics["scored_count"] == 2
    assert metrics["candidate_recall"] == 0.75
    assert metrics["cross_law_scored_count"] == 1
    assert metrics["cross_law_candidate_recall"] == 0.5
    assert result["items"][1]["top_1_correct"] is None
    assert result["items"][1]["candidate_knowledge_base_slugs"] == ["law-a"]


def test_routing_abstention_errors_empty_candidates_and_all_items_are_auditable():
    from src.evaluation.stage8_retrieval_evaluation import evaluate_routing

    calls = []

    def route(query):
        calls.append(query)
        if query == "error":
            raise ValueError("route failed")
        return []

    rows = [record("skip", abstain=True), record("error"), record("empty")]
    result = evaluate_routing(rows, route)
    assert calls == ["error", "empty"]
    assert len(result["items"]) == 3
    assert result["overall"]["scored_count"] == 1
    assert result["overall"]["execution_error_count"] == 1
    assert result["overall"]["excluded_abstention_count"] == 1
    assert result["overall"]["candidate_recall"] == 0
    assert result["overall"]["cross_law_candidate_recall"] is None
    assert result["items"][1]["execution_errors"][0]["message"] == "route failed"
    assert result["items"][2]["included_in_metrics"] is True
    assert result == evaluate_routing(rows, route)
    json.dumps(result, allow_nan=False)


def test_formal_frozen_dataset_can_be_evaluated_without_external_services():
    from src.evaluation.stage8_retrieval_evaluation import (
        evaluate_oracle_retrieval,
        evaluate_routing,
    )

    rows = load_stage8_dataset(
        Path(__file__).resolve().parents[1] / "data/evaluation/stage8/stage8_frozen_280.jsonl",
        require_approved=True,
    )
    retrieved = evaluate_oracle_retrieval(rows, lambda *args: [])
    routed = evaluate_routing(rows, lambda query: [])
    for result in (retrieved, routed):
        assert len(result["items"]) == 280
        assert result["overall"]["scored_count"] == 260
        assert result["overall"]["excluded_abstention_count"] == 20
        assert result["overall"]["execution_error_count"] == 0
        json.dumps(result, allow_nan=False)


def test_oracle_only_scores_five_unique_articles_and_perfect_cross_law_has_unit_ndcg():
    from src.evaluation.stage8_retrieval_evaluation import evaluate_oracle_retrieval

    truncated = evaluate_oracle_retrieval(
        [record()],
        lambda question, slug, k: hits(
            slug, "miss-1", "miss-2", "miss-3", "miss-4", "miss-5", "article-1"
        ),
    )
    assert truncated["overall"]["recall_at_5"] == 0
    assert len(truncated["items"][0]["ranked_evidence_by_knowledge_base"]["civil-code"]) == 5
    labels = {"law-a": ["article-a", "article-b"], "law-b": ["article-c"]}
    result = evaluate_oracle_retrieval(
        [record("cross", labels)], lambda question, slug, k: hits(slug, *labels[slug])
    )
    assert result["overall"]["recall_at_1"] == pytest.approx(2 / 3)
    assert result["overall"]["recall_at_3"] == 1
    assert result["overall"]["mrr_at_5"] == 1
    assert result["overall"]["ndcg_at_5"] == 1


@pytest.mark.parametrize("evaluate_name", ["evaluate_oracle_retrieval", "evaluate_routing"])
def test_all_evaluators_reject_duplicate_ids_before_any_execution(evaluate_name):
    from src.evaluation import stage8_retrieval_evaluation

    calls = []
    with pytest.raises(Stage8DatasetError, match="重复"):
        getattr(stage8_retrieval_evaluation, evaluate_name)(
            [record(), record()], lambda *args: calls.append(args)
        )
    assert calls == []


@pytest.mark.parametrize(
    "candidates", ["civil-code", {"civil-code"}, {"slug": "civil-code"}, [None]]
)
def test_routing_malformed_or_unordered_candidates_are_explicit_execution_errors(candidates):
    from src.evaluation.stage8_retrieval_evaluation import evaluate_routing

    result = evaluate_routing([record()], lambda question: candidates)
    assert result["overall"]["scored_count"] == 0
    assert result["overall"]["execution_error_count"] == 1
    assert result["items"][0]["exclusion_reason"] == "execution_error"
