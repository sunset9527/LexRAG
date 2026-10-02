"""v2.1 真实工作流验收的可审计指标计算。

本模块只计算响应中可观察到的事实；“回答断言是否被法条充分支持”必须由人工复核表提供，
不能以模型自评或引用存在性冒充法律效果。
"""

from __future__ import annotations

import re
from statistics import mean
from typing import Any

_ARTICLE_NUMBER = re.compile(r"第?(\d+(?:-\d+)?)条?$")


def _normalized_article_id(value: object) -> str:
    """将 API 纯条号与人工标注的完整法条 ID 统一为稳定条号。"""
    text = str(value).strip()
    match = _ARTICLE_NUMBER.search(text)
    return match.group(1) if match else text


def evaluate_workflow_responses(
    labels: list[dict[str, Any]], responses: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """汇总真实 API 响应；缺样本直接失败，不把执行故障算作低分。"""
    missing = [str(label["id"]) for label in labels if str(label["id"]) not in responses]
    if missing:
        raise ValueError("缺少工作流响应：" + "、".join(missing))

    passed: list[float] = []
    coverage: list[float] = []
    repair_triggered: list[float] = []
    repair_success: list[float] = []
    latencies: list[float] = []
    review_values: list[float] = []
    missing_reviews: list[str] = []
    cache_hits = 0
    items: list[dict[str, Any]] = []

    for label in labels:
        item_id = str(label["id"])
        response = responses[item_id]
        citations = response.get("citations", [])
        citation_ids = {
            _normalized_article_id(citation.get("article_id", ""))
            for citation in citations
            if isinstance(citation, dict) and citation.get("is_verified") is True
        }
        expected = {
            _normalized_article_id(article_id) for article_id in label["relevant_article_ids"]
        }
        verification_pass = response.get("verification_status") == "pass"
        attempts = int(response.get("metadata", {}).get("verification_attempts", 0) or 0)
        cache_hit = response.get("metadata", {}).get("cache_hit")
        cache_hits += int(bool(cache_hit))
        covered = len(expected & citation_ids) / len(expected)
        passed.append(float(verification_pass))
        coverage.append(covered)
        repair_triggered.append(float(attempts > 0))
        if attempts > 0:
            repair_success.append(float(verification_pass))
        if isinstance(response.get("latency_ms"), int | float):
            latencies.append(float(response["latency_ms"]))

        review = response.get("human_assertion_review")
        if isinstance(review, bool):
            review_values.append(float(review))
        else:
            missing_reviews.append(item_id)
        items.append(
            {
                "id": item_id,
                "verification_status": response.get("verification_status"),
                "verified_citation_ids": sorted(citation_ids),
                "expected_citation_ids": sorted(expected),
                "expected_citation_coverage": round(covered, 6),
                "verification_attempts": attempts,
                "latency_ms": response.get("latency_ms"),
                "cache_hit": cache_hit,
                "human_assertion_review": review if isinstance(review, bool) else None,
            }
        )

    return {
        "sample_count": len(labels),
        "metrics": {
            "verification_pass_rate": round(mean(passed), 6),
            "expected_citation_coverage": round(mean(coverage), 6),
            "repair_trigger_rate": round(mean(repair_triggered), 6),
            "repair_success_rate": round(mean(repair_success), 6) if repair_success else None,
            "mean_end_to_end_latency_ms": round(mean(latencies), 3) if latencies else None,
            "cache_hit_count": cache_hits,
        },
        "human_review": {
            "assertion_support_rate": round(mean(review_values), 6) if review_values else None,
            "reviewed_count": len(review_values),
            "missing_review_ids": missing_reviews,
        },
        "items": items,
    }
