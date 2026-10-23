"""Regression contracts for recognizing real statute article headings."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ingestion.law_parser import LawParser
from src.ingestion.statute_catalog import STATUTE_CATALOG

PROJECT_ROOT = Path(__file__).parent.parent


def test_article_reference_on_a_continuation_line_does_not_start_a_new_article():
    """Article 616 cites Article 511; the citation is not an Article 511 heading."""
    content = """第六百一十六条 当事人对标的物的质量要求没有约定或者约定不明确。
第五百一十一条第一项的规定。
第六百一十七条 出卖人交付的标的物不符合质量要求的。
"""

    articles = LawParser().parse_law_content(content, "中华人民共和国民法典")

    assert [article.article_number for article in articles] == ["616", "617"]
    assert "第五百一十一条第一项的规定。" in articles[0].content


def test_civil_code_snapshot_has_exactly_articles_one_through_1260():
    """The canonical civil snapshot must not gain a phantom split from a citation line."""
    articles = LawParser().parse_law_file(PROJECT_ROOT / "data/laws/中华人民共和国民法典.txt")

    assert len(articles) == 1260
    assert [article.article_number for article in articles] == [str(number) for number in range(1, 1261)]


def test_inserted_article_heading_with_suffix_remains_a_real_article():
    """A standalone ``第十七条之一`` heading is valid even without trailing body text."""
    articles = LawParser().parse_law_content(
        "第十七条 刑事责任年龄。\n第十七条之一\n已满七十五周岁的人。\n第十八条 精神病人。",
        "中华人民共和国刑法",
    )

    assert [article.article_number for article in articles] == ["17", "17-1", "18"]


@pytest.mark.parametrize(
    ("heading", "article_number"),
    [
        ("第一条【立法宗旨】为了保护民事主体的合法权益。", "1"),
        ("第一条（立法宗旨）为了保护民事主体的合法权益。", "1"),
        ("第十七条之一【刑事责任年龄】已满七十五周岁的人。", "17-1"),
    ],
)
def test_annotated_article_heading_starts_a_real_article(heading, article_number):
    """Editorial annotations after a heading do not make it a continuation citation."""
    articles = LawParser().parse_law_content(heading, "中华人民共和国测试法")

    assert [article.article_number for article in articles] == [article_number]
    assert articles[0].content == heading


def test_other_seven_catalog_snapshots_keep_their_recorded_article_counts():
    """Tightening header recognition must not change the already-valid peer snapshots."""
    for statute in STATUTE_CATALOG:
        if statute.definition.slug == "civil-code":
            continue

        articles = LawParser().parse_law_file(PROJECT_ROOT / statute.clean_text_path)

        assert len(articles) == statute.article_count, statute.definition.slug
