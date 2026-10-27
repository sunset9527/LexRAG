"""Stage 8 frozen-evaluation dataset contract tests."""

from __future__ import annotations

import json

import pytest

from src.evaluation.stage8_dataset import Stage8DatasetError, load_stage8_dataset


def _evidence(**overrides: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "knowledge_base_slug": "civil-code",
        "version_id": "civil-code@2020-05-28",
        "effective_from": "2021-01-01",
        "effective_to": None,
        "source_url": "https://flk.npc.gov.cn/detail2.html",
        "content_hash": "a" * 64,
        "article_ids": ["中华人民共和国民法典第17条"],
        "source_locator": "中华人民共和国民法典第17条",
    }
    evidence.update(overrides)
    return evidence


def _reviewed_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": "stage8-civil-001",
        "question": "成年人年龄如何规定？",
        "question_type": "direct_lookup",
        "difficulty": "easy",
        "expected_knowledge_base_slugs": ["civil-code"],
        "relevant_article_ids": ["中华人民共和国民法典第17条"],
        "should_abstain": False,
        "source_evidence": [_evidence()],
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
            source_evidence=[_evidence(article_ids=[], source_locator="民法典适用范围")],
        ),
    )

    records = load_stage8_dataset(dataset, require_approved=True)

    assert records[0]["should_abstain"] is True
    assert records[0]["relevant_article_ids"] == []


@pytest.mark.parametrize("field", ["source_locator", "version_id"])
def test_load_stage8_dataset_rejects_approved_item_with_pending_review_marker(tmp_path, field):
    dataset = _write_jsonl(
        tmp_path,
        _reviewed_item(source_evidence=[_evidence(**{field: "待人工核验"})]),
    )

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
        ["civil-code", "civil-code"],
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
    evidence_articles = [] if should_abstain else relevant_article_ids
    dataset = _write_jsonl(
        tmp_path,
        _reviewed_item(
            should_abstain=should_abstain,
            relevant_article_ids=relevant_article_ids,
            source_evidence=[_evidence(article_ids=evidence_articles)],
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
    dataset = _write_jsonl(
        tmp_path,
        _reviewed_item(source_evidence=[_evidence(source_url=source_url)]),
    )

    with pytest.raises(Stage8DatasetError, match="source_url"):
        load_stage8_dataset(dataset, require_approved=True)


@pytest.mark.parametrize(
    "source_url",
    [
        " https://flk.npc.gov.cn/detail2.html",
        "https://flk.npc.gov.cn/detail 2.html",
        "https://flk.npc.gov.cn/detail2.html\n",
        "https://flk.npc.gov.cn\\evil.example/detail2.html",
    ],
)
def test_load_stage8_dataset_rejects_control_whitespace_and_backslash_source_urls(
    tmp_path, source_url
):
    dataset = _write_jsonl(
        tmp_path,
        _reviewed_item(source_evidence=[_evidence(source_url=source_url)]),
    )

    with pytest.raises(Stage8DatasetError, match="source_url"):
        load_stage8_dataset(dataset, require_approved=True)


def test_load_stage8_dataset_rejects_pending_item_in_formal_mode(tmp_path):
    dataset = _write_jsonl(tmp_path, _reviewed_item(review_status="pending"))

    with pytest.raises(Stage8DatasetError, match="approved"):
        load_stage8_dataset(dataset, require_approved=True)


@pytest.mark.parametrize("review_status", ["anything", " approved", "approved ", "APPROVED"])
def test_load_stage8_dataset_rejects_unknown_or_noncanonical_review_status(
    tmp_path, review_status
):
    dataset = _write_jsonl(tmp_path, _reviewed_item(review_status=review_status))

    with pytest.raises(Stage8DatasetError, match="review_status"):
        load_stage8_dataset(dataset)


def test_load_stage8_dataset_accepts_pending_status_in_draft_mode(tmp_path):
    dataset = _write_jsonl(tmp_path, _reviewed_item(review_status="pending"))

    assert load_stage8_dataset(dataset)[0]["review_status"] == "pending"


@pytest.mark.parametrize(
    "field, value, error",
    [
        ("reviewer", "", "reviewer"),
        ("reviewed_at", "2026-10-26T10:30:00", "reviewed_at"),
        ("reviewed_at", "2026-10-26X10:30:00+08:00", "reviewed_at"),
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


def test_load_stage8_dataset_rejects_duplicate_json_object_keys(tmp_path):
    item = _reviewed_item()
    serialized = json.dumps(item, ensure_ascii=False)
    dataset = tmp_path / "stage8.jsonl"
    dataset.write_text(
        f'{serialized[:-1]}, "id": "stage8-civil-duplicate"}}',
        encoding="utf-8",
    )

    with pytest.raises(Stage8DatasetError, match="重复.*键"):
        load_stage8_dataset(dataset, require_approved=True)


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


def test_load_stage8_dataset_accepts_cross_law_exact_partition(tmp_path):
    company_article = "中华人民共和国公司法第23条"
    item = _reviewed_item(
        expected_knowledge_base_slugs=["civil-code", "company-law"],
        relevant_article_ids=["中华人民共和国民法典第17条", company_article],
        source_evidence=[
            _evidence(),
            _evidence(
                knowledge_base_slug="company-law",
                version_id="company-law@2023-12-29",
                effective_from="2024-07-01",
                content_hash="b" * 64,
                article_ids=[company_article],
                source_locator=company_article,
            ),
        ],
    )

    assert load_stage8_dataset(_write_jsonl(tmp_path, item), require_approved=True) == [item]


def test_load_stage8_dataset_rejects_legacy_singular_source_metadata(tmp_path):
    item = _reviewed_item(source_url="https://flk.npc.gov.cn/", source_version="legacy")

    with pytest.raises(Stage8DatasetError, match="未知字段"):
        load_stage8_dataset(_write_jsonl(tmp_path, item), require_approved=True)


def test_load_stage8_dataset_rejects_pending_marker_in_review_note(tmp_path):
    dataset = _write_jsonl(tmp_path, _reviewed_item(review_note="待人工核验"))

    with pytest.raises(Stage8DatasetError, match="待人工核验"):
        load_stage8_dataset(dataset, require_approved=True)


def test_load_stage8_dataset_rejects_pending_marker_nested_in_evidence_article_ids(tmp_path):
    marker = "待人工核验"
    dataset = _write_jsonl(
        tmp_path,
        _reviewed_item(
            relevant_article_ids=[marker],
            source_evidence=[_evidence(article_ids=[marker])],
        ),
    )

    with pytest.raises(Stage8DatasetError, match="待人工核验"):
        load_stage8_dataset(dataset, require_approved=True)


@pytest.mark.parametrize(
    "override,error",
    [
        ({"content_hash": "A" * 64}, "content_hash"),
        ({"content_hash": "a" * 63}, "content_hash"),
        ({"effective_from": "2021-1-01"}, "effective_from"),
        ({"effective_to": "not-a-date"}, "effective_to"),
        ({"effective_from": "2024-01-02", "effective_to": "2024-01-01"}, "effective_to"),
    ],
)
def test_load_stage8_dataset_validates_evidence_hash_and_dates(tmp_path, override, error):
    dataset = _write_jsonl(
        tmp_path,
        _reviewed_item(source_evidence=[_evidence(**override)]),
    )

    with pytest.raises(Stage8DatasetError, match=error):
        load_stage8_dataset(dataset, require_approved=True)


@pytest.mark.parametrize(
    "source_evidence,error",
    [
        ([], "source_evidence"),
        ([_evidence(knowledge_base_slug="company-law")], "slug"),
        ([_evidence(), _evidence()], "slug"),
        ([_evidence(article_ids=[])], "partition"),
        ([_evidence(article_ids=["中华人民共和国民法典第17条"] * 2)], "重复"),
        ([_evidence(extra="ambiguous")], "未知字段"),
    ],
)
def test_load_stage8_dataset_rejects_invalid_evidence_set_or_partition(
    tmp_path, source_evidence, error
):
    dataset = _write_jsonl(tmp_path, _reviewed_item(source_evidence=source_evidence))

    with pytest.raises(Stage8DatasetError, match=error):
        load_stage8_dataset(dataset, require_approved=True)


def test_load_stage8_dataset_rejects_duplicate_top_level_article_ids(tmp_path):
    article = "中华人民共和国民法典第17条"
    dataset = _write_jsonl(
        tmp_path,
        _reviewed_item(
            relevant_article_ids=[article, article],
            source_evidence=[_evidence(article_ids=[article, article])],
        ),
    )

    with pytest.raises(Stage8DatasetError, match="重复"):
        load_stage8_dataset(dataset, require_approved=True)
