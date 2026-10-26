"""Stage 8 frozen-evaluation dataset contract tests."""

from __future__ import annotations

import json

import pytest

from src.evaluation.stage8_dataset import Stage8DatasetError, load_stage8_dataset


def _reviewed_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": "stage8-civil-001",
        "question": "成年人年龄如何规定？",
        "question_type": "direct_lookup",
        "difficulty": "easy",
        "expected_knowledge_base_slugs": ["civil-code"],
        "relevant_article_ids": ["中华人民共和国民法典第17条"],
        "should_abstain": False,
        "source_url": "https://flk.npc.gov.cn/detail2.html",
        "source_version": "2026-10-01",
        "source_locator": "中华人民共和国民法典第17条",
        "reviewer": "reviewer-a",
        "reviewed_at": "2026-10-26T10:30:00+08:00",
        "review_note": "逐条核对问题、来源和相关法条。",
        "review_status": "approved",
    }
    item.update(overrides)
    return item


def _write_jsonl(tmp_path, *items: object) -> object:
    dataset = tmp_path / "stage8.jsonl"
    dataset.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in items),
        encoding="utf-8",
    )
    return dataset


def test_load_stage8_dataset_accepts_reviewed_answerable_item(tmp_path):
    dataset = _write_jsonl(tmp_path, _reviewed_item())

    records = load_stage8_dataset(dataset, require_approved=True)

    assert records == [_reviewed_item()]


def test_load_stage8_dataset_accepts_reviewed_abstention_item(tmp_path):
    dataset = _write_jsonl(
        tmp_path,
        _reviewed_item(
            id="stage8-abstain-001",
            question="请根据未收录的地方政策回答。",
            relevant_article_ids=[],
            should_abstain=True,
        ),
    )

    records = load_stage8_dataset(dataset, require_approved=True)

    assert records[0]["should_abstain"] is True
    assert records[0]["relevant_article_ids"] == []


@pytest.mark.parametrize("field", ["source_locator", "review_note"])
def test_load_stage8_dataset_rejects_approved_item_with_pending_review_marker(tmp_path, field):
    dataset = _write_jsonl(tmp_path, _reviewed_item(**{field: "待人工核验"}))

    with pytest.raises(Stage8DatasetError, match="待人工核验"):
        load_stage8_dataset(dataset, require_approved=True)


@pytest.mark.parametrize(
    "items, error",
    [
        ([{key: value for key, value in _reviewed_item().items() if key != "id"}], "缺少字段"),
        ([_reviewed_item(), _reviewed_item()], "id"),
    ],
)
def test_load_stage8_dataset_rejects_missing_or_duplicate_id(tmp_path, items, error):
    dataset = _write_jsonl(tmp_path, *items)

    with pytest.raises(Stage8DatasetError, match=error):
        load_stage8_dataset(dataset, require_approved=True)


def test_load_stage8_dataset_rejects_blank_id(tmp_path):
    dataset = _write_jsonl(tmp_path, _reviewed_item(id=" "))

    with pytest.raises(Stage8DatasetError, match="id"):
        load_stage8_dataset(dataset, require_approved=True)


@pytest.mark.parametrize(
    "expected_knowledge_base_slugs",
    [
        None,
        [],
        [""],
    ],
)
def test_load_stage8_dataset_validates_expected_knowledge_base_slugs(
    tmp_path, expected_knowledge_base_slugs
):
    dataset = _write_jsonl(
        tmp_path,
        _reviewed_item(expected_knowledge_base_slugs=expected_knowledge_base_slugs),
    )

    with pytest.raises(Stage8DatasetError, match="expected_knowledge_base_slugs"):
        load_stage8_dataset(dataset, require_approved=True)


@pytest.mark.parametrize("should_abstain", [0, 1, "false", None])
def test_load_stage8_dataset_rejects_non_boolean_should_abstain(tmp_path, should_abstain):
    dataset = _write_jsonl(tmp_path, _reviewed_item(should_abstain=should_abstain))

    with pytest.raises(Stage8DatasetError, match="should_abstain"):
        load_stage8_dataset(dataset, require_approved=True)


@pytest.mark.parametrize(
    "should_abstain, relevant_article_ids",
    [
        (False, []),
        (True, ["中华人民共和国民法典第17条"]),
    ],
)
def test_load_stage8_dataset_rejects_ambiguous_abstention_article_combinations(
    tmp_path, should_abstain, relevant_article_ids
):
    dataset = _write_jsonl(
        tmp_path,
        _reviewed_item(
            should_abstain=should_abstain,
            relevant_article_ids=relevant_article_ids,
        ),
    )

    with pytest.raises(Stage8DatasetError, match="相关法条"):
        load_stage8_dataset(dataset, require_approved=True)


@pytest.mark.parametrize(
    "source_url",
    [
        "http://flk.npc.gov.cn/detail2.html",
        "https://user:secret@flk.npc.gov.cn/detail2.html",
        "https://flk.npc.gov.cn/detail2.html?draft=1",
        "https://flk.npc.gov.cn/detail2.html#article-17",
        "/detail2.html",
    ],
)
def test_load_stage8_dataset_rejects_invalid_source_url(tmp_path, source_url):
    dataset = _write_jsonl(tmp_path, _reviewed_item(source_url=source_url))

    with pytest.raises(Stage8DatasetError, match="source_url"):
        load_stage8_dataset(dataset, require_approved=True)


def test_load_stage8_dataset_rejects_pending_item_in_formal_mode(tmp_path):
    dataset = _write_jsonl(tmp_path, _reviewed_item(review_status="pending"))

    with pytest.raises(Stage8DatasetError, match="approved"):
        load_stage8_dataset(dataset, require_approved=True)


@pytest.mark.parametrize(
    "field, value, error",
    [
        ("reviewer", "", "reviewer"),
        ("reviewed_at", "2026-10-26T10:30:00", "reviewed_at"),
        ("reviewed_at", "not-a-timestamp", "reviewed_at"),
    ],
)
def test_load_stage8_dataset_validates_approved_reviewer_and_timestamp(
    tmp_path, field, value, error
):
    dataset = _write_jsonl(tmp_path, _reviewed_item(**{field: value}))

    with pytest.raises(Stage8DatasetError, match=error):
        load_stage8_dataset(dataset, require_approved=True)


def test_load_stage8_dataset_rejects_malformed_json(tmp_path):
    dataset = tmp_path / "stage8.jsonl"
    dataset.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(Stage8DatasetError, match="合法 JSON"):
        load_stage8_dataset(dataset)


def test_load_stage8_dataset_reports_unreadable_input(tmp_path):
    missing_dataset = tmp_path / "missing-stage8.jsonl"

    with pytest.raises(Stage8DatasetError, match="无法读取"):
        load_stage8_dataset(missing_dataset)


def test_load_stage8_dataset_ignores_blank_lines(tmp_path):
    item = _reviewed_item()
    dataset = tmp_path / "stage8.jsonl"
    dataset.write_text(
        f"\n  \n{json.dumps(item, ensure_ascii=False)}\n\t\n",
        encoding="utf-8",
    )

    assert load_stage8_dataset(dataset, require_approved=True) == [item]
