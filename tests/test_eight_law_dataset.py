"""正式八部法律评测集的组装与审核状态测试。"""

import pytest

from src.evaluation.eight_law_dataset import (
    EIGHT_LAW_SAMPLE_COUNTS,
    EvaluationDatasetError,
    build_approved_eight_law_dataset,
)


def _label(identifier: str, slug: str, *, status: str | None = None) -> dict:
    item = {
        "id": identifier,
        "query": "测试问题",
        "knowledge_base_slug": slug,
        "relevant_article_ids": ["测试法第1条"],
        "source": "测试来源",
        "reviewed_at": "2026-08-02" if status is None else "",
    }
    if status is not None:
        item["review_status"] = status
        item["source_locator"] = "测试法第1条"
    return item


def test_build_approved_dataset_promotes_only_verified_draft_to_exact_distribution():
    """人工确认后的草稿与历史基线必须合成恰好 100 条正式集。"""
    baseline = [_label(f"civil-{index:03d}", "civil-code") for index in range(1, 16)]
    draft = [
        _label(f"civil-new-{index:03d}", "civil-code", status="pending") for index in range(1, 16)
    ]
    for slug, total in EIGHT_LAW_SAMPLE_COUNTS.items():
        if slug == "civil-code":
            continue
        draft.extend(
            _label(f"{slug}-{index:03d}", slug, status="pending") for index in range(1, total + 1)
        )

    official = build_approved_eight_law_dataset(
        baseline,
        draft,
        reviewed_at="2026-10-06",
    )

    assert len(official) == 100
    assert {row["review_status"] for row in official} == {"approved"}
    assert all(row["reviewed_at"] for row in official)
    assert official[-1]["reviewed_at"] == "2026-10-06"


def test_build_approved_dataset_rejects_unexpected_distribution():
    """缺少任一法律样本时，不能生成看似正式的 100 条数据集。"""
    baseline = [_label(f"civil-{index:03d}", "civil-code") for index in range(1, 16)]

    with pytest.raises(EvaluationDatasetError, match="样本分布"):
        build_approved_eight_law_dataset(baseline, [], reviewed_at="2026-10-06")
