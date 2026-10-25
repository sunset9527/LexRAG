"""人工标注检索集的加载、校验与指标计算。"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "id",
    "query",
    "knowledge_base_slug",
    "relevant_article_ids",
    "source",
    "reviewed_at",
}


class EvaluationDatasetError(ValueError):
    """评测集不符合可审计数据契约。"""


def _canonical_article_id(article_id: str) -> str:
    """统一「第17条之1」与「第17-1条」这类等价条号写法。"""
    return re.sub(r"第(\d+)条之(\d+)", r"第\1-\2条", article_id)


def load_labels(path: Path, *, require_reviewed: bool = False) -> list[dict[str, Any]]:
    """加载并校验 JSONL 人工标注，拒绝不完整、重复或未核验的正式样本。"""
    labels: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationDatasetError(f"第 {line_number} 行不是合法 JSON") from exc
        missing = REQUIRED_FIELDS - item.keys()
        if missing:
            raise EvaluationDatasetError(
                f"第 {line_number} 行缺少字段: {', '.join(sorted(missing))}"
            )
        if not isinstance(item["id"], str) or not item["id"].strip() or item["id"] in seen_ids:
            raise EvaluationDatasetError(f"第 {line_number} 行 id 为空或重复")
        if not isinstance(item["relevant_article_ids"], list) or not item["relevant_article_ids"]:
            raise EvaluationDatasetError(f"第 {line_number} 行缺少人工核验的相关法条")
        if not all(
            isinstance(article_id, str) and article_id.strip()
            for article_id in item["relevant_article_ids"]
        ):
            raise EvaluationDatasetError(f"第 {line_number} 行包含无效法条 ID")
        if require_reviewed and item.get("review_status") != "approved":
            raise EvaluationDatasetError(f"第 {line_number} 行未经人工核验，不能用于正式评测")
        seen_ids.add(item["id"])
        labels.append(item)
    if not labels:
        raise EvaluationDatasetError("评测集没有有效样本")
    return labels


def evaluate_labels(
    labels: list[dict[str, Any]],
    retrieve: Callable[[dict[str, Any]], list[str]],
    *,
    top_k: int,
) -> dict[str, Any]:
    """以每条样本的真实相关法条计算 Recall@K、MRR@K 和 NDCG@K。"""
    if top_k < 1:
        raise ValueError("top_k 必须大于 0")

    recall_scores: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcg_scores: list[float] = []
    items: list[dict[str, Any]] = []

    for label in labels:
        ranked_article_ids: list[str] = []
        seen_article_ids: set[str] = set()
        for article_id in retrieve(label):
            article_id = _canonical_article_id(article_id)
            if article_id in seen_article_ids:
                continue
            seen_article_ids.add(article_id)
            ranked_article_ids.append(article_id)
            if len(ranked_article_ids) >= top_k:
                break
        relevant = {_canonical_article_id(article_id) for article_id in label["relevant_article_ids"]}
        hits = [article_id for article_id in ranked_article_ids if article_id in relevant]
        recall_scores.append(len(set(hits)) / len(relevant))

        first_rank = next(
            (
                index + 1
                for index, article_id in enumerate(ranked_article_ids)
                if article_id in relevant
            ),
            None,
        )
        reciprocal_ranks.append(1 / first_rank if first_rank else 0.0)

        dcg = sum(
            1 / math.log2(index + 2)
            for index, article_id in enumerate(ranked_article_ids)
            if article_id in relevant
        )
        ideal_count = min(len(relevant), top_k)
        ideal_dcg = sum(1 / math.log2(index + 2) for index in range(ideal_count))
        ndcg_scores.append(dcg / ideal_dcg if ideal_dcg else 0.0)
        items.append(
            {
                "id": label["id"],
                "knowledge_base_slug": label["knowledge_base_slug"],
                "relevant_article_ids": label["relevant_article_ids"],
                "ranked_article_ids": ranked_article_ids,
                "first_relevant_rank": first_rank,
            }
        )

    count = len(labels)
    return {
        "sample_count": count,
        "top_k": top_k,
        "metrics": {
            "recall_at_k": round(sum(recall_scores) / count, 6),
            "mrr_at_k": round(sum(reciprocal_ranks) / count, 6),
            "ndcg_at_k": round(sum(ndcg_scores) / count, 6),
        },
        "items": items,
    }


def evaluate_labels_by_knowledge_base(
    labels: list[dict[str, Any]],
    retrieve: Callable[[dict[str, Any]], list[str]],
    *,
    top_k: int,
) -> dict[str, Any]:
    """计算总体指标，并保留每个知识库的独立指标和命中明细。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for label in labels:
        grouped.setdefault(label["knowledge_base_slug"], []).append(label)

    return {
        "overall": evaluate_labels(labels, retrieve, top_k=top_k),
        "by_knowledge_base": {
            slug: evaluate_labels(grouped_labels, retrieve, top_k=top_k)
            for slug, grouped_labels in sorted(grouped.items())
        },
    }
