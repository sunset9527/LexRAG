"""八部法律正式检索评测集的组装与分布校验。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .retrieval_evaluation import EvaluationDatasetError

EIGHT_LAW_SAMPLE_COUNTS = {
    "civil-code": 30,
    "criminal-law": 15,
    "labor-law": 10,
    "labor-contract-law": 10,
    "company-law": 10,
    "patent-law": 5,
    "trademark-law": 10,
    "copyright-law": 10,
}


def build_approved_eight_law_dataset(
    baseline: list[dict[str, Any]],
    draft: list[dict[str, Any]],
    *,
    reviewed_at: str,
) -> list[dict[str, Any]]:
    """从历史人工基线与本次已确认草稿组装正式 100 条数据集。"""
    if not reviewed_at.strip():
        raise EvaluationDatasetError("人工核验日期不能为空")

    official: list[dict[str, Any]] = []
    for row in baseline:
        item = dict(row)
        item["source_locator"] = item.get("source_locator") or "; ".join(
            item["relevant_article_ids"]
        )
        item["review_status"] = "approved"
        official.append(item)

    for row in draft:
        if row.get("review_status") != "pending":
            raise EvaluationDatasetError(f"候选样本 {row.get('id', '')} 不是待核验状态")
        item = dict(row)
        item["review_status"] = "approved"
        item["reviewed_at"] = reviewed_at
        official.append(item)

    if len({row["id"] for row in official}) != len(official):
        raise EvaluationDatasetError("正式数据集存在重复样本 ID")

    actual_counts = Counter(row["knowledge_base_slug"] for row in official)
    if dict(actual_counts) != EIGHT_LAW_SAMPLE_COUNTS:
        raise EvaluationDatasetError(
            f"样本分布不符合八部法律 100 条规范: {dict(sorted(actual_counts.items()))}"
        )
    return official
