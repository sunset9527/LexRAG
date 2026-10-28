"""Pure, auditable ranking and routing evaluation for approved Stage 8 rows.

The caller owns loading, real retriever/router construction, and report writing.
No legacy engineering label format, database, model, or clock is used here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Set
from math import log2
from typing import Any

from .stage8_dataset import Stage8DatasetError, validate_stage8_record

Evidence = Mapping[str, str]
Retriever = Callable[[str, str, int], Iterable[Evidence]]
Router = Callable[[str], Iterable[str]]
_RANKING_METRICS = ("recall_at_1", "recall_at_3", "recall_at_5", "mrr_at_5", "ndcg_at_5")


def _validated_records(records: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Fail before external calls if any record violates the formal contract."""
    rows = list(records)
    seen = set()
    for line_number, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise Stage8DatasetError(f"第 {line_number} 行必须是 JSON 对象")
        validate_stage8_record(row, line_number=line_number, require_approved=True)
        identifier = row["id"].strip()
        if identifier in seen:
            raise Stage8DatasetError(f"第 {line_number} 行字段 id 重复")
        seen.add(identifier)
    return rows


def _base_item(row: Mapping[str, Any]) -> dict[str, Any]:
    excluded = row["should_abstain"]
    return {
        "id": row["id"],
        "question": row["question"],
        "question_type": row["question_type"],
        "difficulty": row["difficulty"],
        "expected_knowledge_base_slugs": list(row["expected_knowledge_base_slugs"]),
        "should_abstain": excluded,
        "status": "excluded_abstention" if excluded else "scored",
        "included_in_metrics": not excluded,
        "exclusion_reason": "should_abstain" if excluded else None,
        "execution_errors": [],
    }


def _execution_error(item: dict[str, Any], exc: Exception, **context: str) -> None:
    item["execution_errors"].append(
        {**context, "error_type": type(exc).__name__, "message": str(exc)}
    )
    item.update(
        status="execution_error", included_in_metrics=False, exclusion_reason="execution_error"
    )


def _ranked_evidence(results: Iterable[Evidence]) -> list[dict[str, str]]:
    """Keep the first five unique composite articles, not duplicate chunks."""
    ranked = []
    seen = set()
    for result in results:
        if not isinstance(result, Mapping):
            raise ValueError("retrieval result must be a composite evidence mapping")
        slug, article = result.get("knowledge_base_slug"), result.get("article_id")
        if not all(isinstance(value, str) and value.strip() for value in (slug, article)):
            raise ValueError(
                "retrieval result requires nonblank knowledge_base_slug and article_id"
            )
        identity = (slug, article)
        if identity in seen:
            continue
        seen.add(identity)
        ranked.append({"knowledge_base_slug": slug, "article_id": article})
        if len(ranked) == 5:
            break
    return ranked


def _ranking_score(
    labels_by_slug: Mapping[str, list[dict[str, str]]],
    ranked_by_slug: Mapping[str, list[dict[str, str]]],
) -> tuple[dict[str, float], int | None]:
    """Use within-law ranks; combine DCG/IDCG and all labels across laws."""
    label_count = sum(len(labels) for labels in labels_by_slug.values())
    hits_at = {k: 0 for k in (1, 3, 5)}
    relevant_ranks = []
    dcg = ideal_dcg = 0.0
    for slug, labels in labels_by_slug.items():
        expected = {(label["knowledge_base_slug"], label["article_id"]) for label in labels}
        for rank, evidence in enumerate(ranked_by_slug.get(slug, []), start=1):
            if (evidence["knowledge_base_slug"], evidence["article_id"]) not in expected:
                continue
            relevant_ranks.append(rank)
            dcg += 1 / log2(rank + 1)
            for k in hits_at:
                if rank <= k:
                    hits_at[k] += 1
        ideal_dcg += sum(1 / log2(rank + 1) for rank in range(1, min(len(expected), 5) + 1))
    first_rank = min(relevant_ranks, default=None)
    return {
        **{
            f"recall_at_{k}": count / label_count if label_count else 0.0
            for k, count in hits_at.items()
        },
        "mrr_at_5": 1 / first_rank if first_rank else 0.0,
        "ndcg_at_5": dcg / ideal_dcg if ideal_dcg else 0.0,
    }, first_rank


def _counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_count": len(items),
        "scored_count": sum(item["included_in_metrics"] for item in items),
        "excluded_abstention_count": sum(item["status"] == "excluded_abstention" for item in items),
        "execution_error_count": sum(item["status"] == "execution_error" for item in items),
    }


def _ranking_summary(items: list[dict[str, Any]], slug: str | None = None) -> dict[str, Any]:
    scored = [item for item in items if item["included_in_metrics"]]
    scores = [
        item["metrics"] if slug is None else item["metrics_by_knowledge_base"][slug]
        for item in scored
    ]
    return {
        **_counts(items),
        **{
            name: sum(score[name] for score in scores) / len(scores) if scores else None
            for name in _RANKING_METRICS
        },
    }


def _grouped(
    items: list[dict[str, Any]], field: str, summarize: Callable[..., dict[str, Any]]
) -> dict[str, Any]:
    keys = sorted({item[field] for item in items})
    return {key: summarize([item for item in items if item[field] == key]) for key in keys}


def evaluate_oracle_retrieval(
    records: Iterable[Mapping[str, Any]], retriever: Retriever
) -> dict[str, Any]:
    """Evaluate approved records with ``retriever(question, slug, 5)``.

    The retriever returns ranked mappings with explicit ``knowledge_base_slug``
    and ``article_id``. Never infer a returned law from the requested law. Each
    expected law is called separately. Cross-law Recall@K uses every law's top-K
    list and all expected labels; NDCG is summed DCG / summed ideal DCG. MRR is
    reciprocal minimum relevant *within-law* rank, not a merged global rank.
    Per-law groups score only that law; type/difficulty groups retain row scores.
    Any execution error excludes the entire row, retaining successful subcalls.
    """
    items = []
    for row in _validated_records(records):
        item = _base_item(row)
        labels_by_slug = {
            evidence["knowledge_base_slug"]: [
                {"knowledge_base_slug": evidence["knowledge_base_slug"], "article_id": article}
                for article in evidence["article_ids"]
            ]
            for evidence in row["source_evidence"]
        }
        item.update(
            expected_labels=[label for labels in labels_by_slug.values() for label in labels],
            ranked_evidence_by_knowledge_base={},
            first_relevant_rank=None,
            metrics=None,
            metrics_by_knowledge_base={},
        )
        if not row["should_abstain"]:
            for slug in row["expected_knowledge_base_slugs"]:
                try:
                    item["ranked_evidence_by_knowledge_base"][slug] = _ranked_evidence(
                        retriever(row["question"], slug, 5)
                    )
                except Exception as exc:
                    _execution_error(item, exc, knowledge_base_slug=slug)
            if item["included_in_metrics"]:
                ranked = item["ranked_evidence_by_knowledge_base"]
                item["metrics"], item["first_relevant_rank"] = _ranking_score(
                    labels_by_slug, ranked
                )
                item["metrics_by_knowledge_base"] = {
                    slug: _ranking_score({slug: labels}, ranked)[0]
                    for slug, labels in labels_by_slug.items()
                }
        items.append(item)
    slugs = sorted({slug for item in items for slug in item["expected_knowledge_base_slugs"]})
    return {
        "evaluation": "oracle_retrieval",
        "metric_semantics": {
            "rank_scope": "within_each_knowledge_base",
            "top_k_per_knowledge_base": 5,
            "ranking_unit": "unique_composite_article",
            "cross_law_recall": "hits_in_each_law_top_k_divided_by_all_expected_composite_labels",
            "cross_law_ndcg": "sum_per_law_dcg_at_5_divided_by_sum_per_law_ideal_dcg_at_5",
            "cross_law_mrr": "reciprocal_minimum_relevant_within_law_rank_at_5",
            "aggregation": "macro_average_of_scored_rows",
            "by_knowledge_base": "only_the_group_law_labels_and_ranked_list",
            "execution_error_policy": "exclude_entire_row",
        },
        "overall": _ranking_summary(items),
        "by_knowledge_base": {
            slug: _ranking_summary(
                [item for item in items if slug in item["expected_knowledge_base_slugs"]], slug
            )
            for slug in slugs
        },
        "by_question_type": _grouped(items, "question_type", _ranking_summary),
        "by_difficulty": _grouped(items, "difficulty", _ranking_summary),
        "items": items,
    }


def _routing_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [item for item in items if item["included_in_metrics"]]
    singles = [item for item in scored if len(item["expected_knowledge_base_slugs"]) == 1]
    crosses = [item for item in scored if len(item["expected_knowledge_base_slugs"]) > 1]
    return {
        **_counts(items),
        "single_law_scored_count": len(singles),
        "cross_law_scored_count": len(crosses),
        "top_1_accuracy": sum(item["top_1_correct"] for item in singles) / len(singles)
        if singles
        else None,
        "candidate_recall": sum(item["candidate_recall"] for item in scored) / len(scored)
        if scored
        else None,
        "cross_law_candidate_recall": sum(item["candidate_recall"] for item in crosses)
        / len(crosses)
        if crosses
        else None,
    }


def evaluate_routing(records: Iterable[Mapping[str, Any]], router: Router) -> dict[str, Any]:
    """Evaluate ``router(question) -> ordered iterable of candidate slug strings``.

    Top-1 is the first ranked candidate and is scored only for single-law rows.
    Candidate recall is |expected intersection candidates| / |expected| per row,
    macro averaged over scored rows. Duplicates do not change ranks or recall.
    Empty candidates are a scored miss; abstentions and errors are excluded.
    """
    items = []
    for row in _validated_records(records):
        item = _base_item(row)
        item.update(candidate_knowledge_base_slugs=[], top_1_correct=None, candidate_recall=None)
        if not row["should_abstain"]:
            try:
                raw_candidates = router(row["question"])
                if isinstance(raw_candidates, (str, bytes, Mapping, Set)):
                    raise ValueError(
                        "router must return an ordered iterable of candidate slug strings"
                    )
                candidates = []
                for slug in raw_candidates:
                    if not isinstance(slug, str) or not slug.strip():
                        raise ValueError("routing candidate slug must be a nonblank string")
                    if slug not in candidates:
                        candidates.append(slug)
                expected = set(row["expected_knowledge_base_slugs"])
                item["candidate_knowledge_base_slugs"] = candidates
                item["candidate_recall"] = len(expected.intersection(candidates)) / len(expected)
                if len(expected) == 1:
                    item["top_1_correct"] = bool(candidates and candidates[0] in expected)
            except Exception as exc:
                _execution_error(item, exc)
        items.append(item)
    return {
        "evaluation": "automatic_routing",
        "metric_semantics": {
            "top_1": "first_ranked_candidate_single_law_rows_only",
            "candidate_recall": "expected_intersection_candidates_divided_by_expected_per_row",
            "cross_law": "more_than_one_expected_knowledge_base_slug",
            "aggregation": "macro_average_of_scored_rows",
            "execution_error_policy": "exclude_entire_row",
        },
        "overall": _routing_summary(items),
        "by_question_type": _grouped(items, "question_type", _routing_summary),
        "by_difficulty": _grouped(items, "difficulty", _routing_summary),
        "items": items,
    }
