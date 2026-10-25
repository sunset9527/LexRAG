from datetime import date
from hashlib import sha256

import pytest

from src.ingestion.criminal_law_merge import (
    CriminalLawMergeError,
    CriminalLawPatch,
    build_consolidated_candidate,
    load_amendment_12_patch_manifest,
    merge_criminal_law_amendment_12,
)
from src.ingestion.statute_source_intake import (
    SOURCE_STATUS_HISTORICAL,
    SOURCE_STATUS_SUPPLEMENTAL_AMENDMENT,
    Stage4SourceCandidate,
)


def test_merge_replaces_only_explicit_target_articles_and_keeps_source_fingerprints():
    base = """中华人民共和国刑法
第一百六十六条 原条文。
第一百六十七条 不得修改。
第二百六十条 原条文。
"""
    amendment = "修正案十二原文"
    patch = CriminalLawPatch(
        article_number="166",
        amendment_item_number=1,
        replacement_text="第一百六十六条 修正后的完整条文。",
    )

    merged = merge_criminal_law_amendment_12(base, amendment, [patch])

    assert "第一百六十六条 修正后的完整条文。" in merged.content
    assert "第一百六十七条 不得修改。" in merged.content
    assert "第二百六十条 原条文。" in merged.content
    assert merged.base_content_sha256 == sha256(base.encode("utf-8")).hexdigest()
    assert merged.amendment_content_sha256 == sha256(amendment.encode("utf-8")).hexdigest()
    assert merged.content_sha256 == sha256(merged.content.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(
    "patches, error",
    [
        (
            [
                CriminalLawPatch("166", 1, "第一百六十六条 修正后的完整条文。"),
                CriminalLawPatch("166", 2, "第一百六十六条 重复替换。"),
            ],
            "重复",
        ),
        (
            [CriminalLawPatch("999", 1, "第九百九十九条 不存在的条文。")],
            "不存在",
        ),
    ],
)
def test_merge_rejects_ambiguous_or_missing_patch_targets(patches, error):
    base = "中华人民共和国刑法\n第一百六十六条 原条文。"

    with pytest.raises(CriminalLawMergeError, match=error):
        merge_criminal_law_amendment_12(base, "修正案十二原文", patches)


def test_merge_does_not_treat_an_inserted_article_as_a_duplicate_main_article():
    base = """中华人民共和国刑法
第一百六十九条 原条文。
第一百六十九条之一 保持不变的插入条文。
"""

    merged = merge_criminal_law_amendment_12(
        base,
        "修正案十二原文",
        [CriminalLawPatch("169", 3, "第一百六十九条 修正后的完整条文。")],
    )

    assert "第一百六十九条 修正后的完整条文。" in merged.content
    assert "第一百六十九条之一 保持不变的插入条文。" in merged.content


def test_build_consolidated_candidate_keeps_generated_text_pending_content_review(tmp_path):
    base = Stage4SourceCandidate(
        source_path=tmp_path / "criminal-base.docx",
        law_slug="criminal-law",
        law_name="中华人民共和国刑法",
        version_id="criminal-law@2020-12-26",
        promulgated_on=date(2020, 12, 26),
        effective_from=date(2021, 3, 1),
        source_status=SOURCE_STATUS_HISTORICAL,
        raw_sha256="a" * 64,
        content_sha256="b" * 64,
        content="中华人民共和国刑法\n第一百六十五条 原条文。",
    )
    amendment = Stage4SourceCandidate(
        source_path=tmp_path / "criminal-amendment-12.docx",
        law_slug="criminal-law",
        law_name="中华人民共和国刑法修正案（十二）",
        version_id="criminal-amendment-12@2023-12-29",
        promulgated_on=date(2023, 12, 29),
        effective_from=date(2024, 3, 1),
        source_status=SOURCE_STATUS_SUPPLEMENTAL_AMENDMENT,
        raw_sha256="c" * 64,
        content_sha256="d" * 64,
        content="修正案十二原文",
        document_type="AMENDMENT",
    )

    candidate = build_consolidated_candidate(
        base,
        amendment,
        [CriminalLawPatch("165", 1, "第一百六十五条 修正后的完整条文。")],
    )

    assert candidate.version_id == "criminal-law@2024-03-01"
    assert candidate.source_status == "CURRENT"
    assert candidate.authority_status == "PENDING_REVIEW"
    assert candidate.document_type == "STATUTE"
    assert candidate.source_path.as_posix() == "generated/criminal-law@2024-03-01.txt"


def test_amendment_12_patch_manifest_has_all_explicit_replacement_articles():
    patches = load_amendment_12_patch_manifest()

    assert [(patch.article_number, patch.amendment_item_number) for patch in patches] == [
        ("165", 1),
        ("166", 2),
        ("169", 3),
        ("387", 4),
        ("390", 5),
        ("391", 6),
        ("393", 7),
    ]
    assert patches[0].replacement_text.startswith("第一百六十五条")
