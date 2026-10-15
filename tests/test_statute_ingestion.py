"""v1.9 核心法规接入管线的契约测试。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.ingest_statutes import STATUTE_DEFINITIONS  # noqa: E402
from src.ingestion.statute_ingestion import (  # noqa: E402
    StatuteDefinition,
    StatuteIngestionRunner,
    StatuteValidationError,
    build_source_manifest_entry,
    clean_statute_from_source,
    extract_epub_text,
    prepare_statute_sources,
    validate_clean_law_text,
)

COMPANY_LAW = """中华人民共和国公司法
第一章 总则
第一条 为了规范公司的组织和行为，保护公司、股东、职工和债权人的合法权益，完善中国特色现代企业制度，弘扬企业家精神，维护社会经济秩序，促进社会主义市场经济的发展，根据宪法，制定本法。
第二条 本法所称公司，是指依照本法在中华人民共和国境内设立的有限责任公司和股份有限公司。
"""


def test_validate_clean_law_text_reports_a_traceable_article_range():
    """清洗后的单部法律必须产生稳定、可演示的验收摘要。"""
    definition = StatuteDefinition(
        slug="company-law",
        name="中华人民共和国公司法",
        law_area="company",
        source_id="company-code",
    )

    report = validate_clean_law_text(COMPANY_LAW, definition)

    assert report.law_name == "中华人民共和国公司法"
    assert report.article_count == 2
    assert report.first_article_number == 1
    assert report.last_article_number == 2
    assert report.clean_text_sha256 == hashlib.sha256(COMPANY_LAW.encode("utf-8")).hexdigest()


def test_validate_clean_law_text_keeps_inserted_articles_in_strict_order():
    """“第十七条之一”是独立法条，不能被折叠为重复的第十七条。"""
    content = """中华人民共和国刑法
第十七条 刑事责任年龄。
第十七条之一 已满七十五周岁的人的刑事责任。
第十八条 特殊人员的刑事责任。
"""
    definition = StatuteDefinition(
        "criminal-law",
        "中华人民共和国刑法",
        "criminal",
        "criminal-code",
    )

    report = validate_clean_law_text(content, definition)

    assert report.article_count == 3
    assert report.first_article_number == 17
    assert report.last_article_number == 18


@pytest.mark.parametrize(
    "content, reason",
    [
        (
            COMPANY_LAW.replace("第二条", "第一条"),
            "条号重复",
        ),
        (
            COMPANY_LAW.replace("第一条", "第三条").replace("第二条", "第二条"),
            "条号未严格递增",
        ),
    ],
)
def test_validate_clean_law_text_rejects_invalid_article_order(content, reason):
    """目录、注释或排版造成的伪条号不能被静默入库。"""
    definition = StatuteDefinition(
        slug="company-law",
        name="中华人民共和国公司法",
        law_area="company",
        source_id="company-code",
    )

    with pytest.raises(StatuteValidationError, match=reason):
        validate_clean_law_text(content, definition)


def test_build_source_manifest_entry_records_original_file_hash(tmp_path):
    """来源清单必须可回溯到用户提供的原始文件，而不是只记录展示名。"""
    source = tmp_path / "公司法.epub"
    source.write_bytes(b"official-statute-source")

    entry = build_source_manifest_entry(
        source_id="company-code",
        source_path=source,
        laws=["company-law"],
        extracted_at="2026-09-10T12:00:00+08:00",
        extractor="zip-html-v1",
    )

    assert entry["source_id"] == "company-code"
    assert entry["original_file_name"] == "公司法.epub"
    assert entry["original_file_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert entry["laws"] == ["company-law"]


def test_extract_epub_text_keeps_reading_order_and_removes_html_markup(tmp_path):
    """EPUB 的章节 HTML 必须转换为可清洗的 UTF-8 文本。"""
    epub_path = tmp_path / "law.epub"
    with ZipFile(epub_path, "w") as archive:
        archive.writestr(
            "OPS/chapter-1.xhtml",
            "<html><body><h1>中华人民共和国公司法</h1><p>第一条 公司正文。</p></body></html>",
        )
        archive.writestr(
            "OPS/chapter-2.xhtml",
            "<html><body><p>第二条 第二段正文。</p><script>ignored()</script></body></html>",
        )

    extracted = extract_epub_text(epub_path)

    assert extracted == "中华人民共和国公司法\n第一条 公司正文。\n第二条 第二段正文。"


def test_extract_epub_text_honors_declared_gb18030_encoding(tmp_path):
    """本地书籍常用 GBK/GB18030，不能以 UTF-8 替换字符后再清洗。"""
    epub_path = tmp_path / "gb18030-law.epub"
    html = (
        '<html><head><meta charset="gb18030"></head><body><p>中华人民共和国刑法</p></body></html>'
    )
    with ZipFile(epub_path, "w") as archive:
        archive.writestr("OPS/chapter-1.xhtml", html.encode("gb18030"))

    assert extract_epub_text(epub_path) == "中华人民共和国刑法"


def test_clean_statute_from_source_discards_catalog_and_annotations():
    """注释法典只应输出目标法律正文，不能把目录或注释入库。"""
    source_text = """目录
中华人民共和国公司法
第一章 总则
第一条 目录条目
中华人民共和国公司法（2013年修正版）
第一章 总则
第一条【立法宗旨】公司法正文一。
注释［立法宗旨］
这段是出版物注释，不是法条。
第二条【调整对象】公司法正文二。
中华人民共和国劳动法
第一条 不应被保留。
"""
    definition = StatuteDefinition(
        "company-law",
        "中华人民共和国公司法",
        "company",
        "company-code",
        terminal_article_number=2,
        first_article_marker="公司法正文一",
    )

    clean_text = clean_statute_from_source(source_text, definition)

    assert (
        clean_text
        == """中华人民共和国公司法
第一章 总则
第一条 公司法正文一。
第二条 公司法正文二。"""
    )


def test_clean_statute_from_source_keeps_multiline_article_body_before_annotation():
    """正文与条号分行的 EPUB 也必须保留完整条文，注释仍须排除。"""
    source_text = """中华人民共和国刑法（节录）
第一章 总则
第一条【立法宗旨】
为了惩罚犯罪，保护人民，制定本法。
[2]
注释 本行及后续说明不能进入法规库。
注释续行。
第二条【任务】
中华人民共和国刑法的任务，是用刑罚同一切犯罪行为作斗争。
"""
    definition = StatuteDefinition(
        "criminal-law",
        "中华人民共和国刑法",
        "criminal",
        "criminal-code",
        terminal_article_number=2,
        first_article_marker="为了惩罚犯罪",
    )

    clean_text = clean_statute_from_source(source_text, definition)

    assert (
        clean_text
        == """中华人民共和国刑法
第一章 总则
第一条
为了惩罚犯罪，保护人民，制定本法。
第二条
中华人民共和国刑法的任务，是用刑罚同一切犯罪行为作斗争。"""
    )


def test_prepare_statute_sources_writes_raw_clean_text_and_manifest(tmp_path):
    """资料准备必须留下可复现的 raw、clean 与哈希来源清单。"""
    source = tmp_path / "公司法.epub"
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "chapter.xhtml",
            "<p>中华人民共和国公司法（2013年修正版）</p><p>第一章 总则</p>"
            "<p>第一条【立法宗旨】公司法正文一。</p>",
        )
    definition = StatuteDefinition(
        "company-law",
        "中华人民共和国公司法",
        "company",
        "company-code",
        terminal_article_number=1,
        first_article_marker="公司法正文一",
    )
    raw_directory = tmp_path / "raw"
    clean_directory = tmp_path / "clean"

    manifest = prepare_statute_sources(
        {"company-code": source},
        [definition],
        raw_directory=raw_directory,
        clean_text_directory=clean_directory,
        extracted_at="2026-09-10T12:00:00+08:00",
    )

    assert (raw_directory / "company-code" / "extracted.txt").read_text(
        encoding="utf-8"
    ) == "中华人民共和国公司法（2013年修正版）\n第一章 总则\n第一条【立法宗旨】公司法正文一。"
    assert (clean_directory / "company-law.txt").read_text(encoding="utf-8") == (
        "中华人民共和国公司法\n第一章 总则\n第一条 公司法正文一。"
    )
    assert manifest["sources"][0]["original_file_name"] == "公司法.epub"
    assert manifest["laws"]["company-law"]["article_count"] == 1
    assert json.loads((raw_directory / "manifest.json").read_text(encoding="utf-8")) == manifest


def test_cli_catalog_declares_each_planned_statute_as_an_independent_library():
    """命令行目录是模块 1 的单一配置源，不能遗漏规划中的任一法律。"""
    definitions = {definition.slug: definition for definition in STATUTE_DEFINITIONS}

    assert set(definitions) == {
        "criminal-law",
        "labor-law",
        "labor-contract-law",
        "company-law",
        "patent-law",
        "trademark-law",
        "copyright-law",
    }
    assert all(definition.terminal_article_number for definition in definitions.values())
    assert all(definition.first_article_marker for definition in definitions.values())


class FakeKnowledgeBaseService:
    def __init__(self):
        self.created: list[dict[str, str]] = []
        self.rebuilt: list[tuple[str, str]] = []

    def create_knowledge_base(self, *, name, slug, law_area):
        self.created.append({"name": name, "slug": slug, "law_area": law_area})

    def rebuild_knowledge_base(self, slug, *, content):
        self.rebuilt.append((slug, content))
        return {
            "name": slug,
            "status": "READY",
            "document_count": 2,
            "chunk_count": 2,
        }


def test_batch_ingestion_keeps_ready_laws_when_one_law_fails_validation(tmp_path):
    """批量导入失败必须局限在坏数据的法律库，不能碰已验证的其他库。"""
    good_file = tmp_path / "company-law.txt"
    bad_file = tmp_path / "criminal-law.txt"
    good_file.write_text(COMPANY_LAW, encoding="utf-8")
    bad_file.write_text(
        "中华人民共和国刑法\n第一条 刑法正文。\n第一条 重复正文。", encoding="utf-8"
    )
    service = FakeKnowledgeBaseService()
    runner = StatuteIngestionRunner(service)
    definitions = [
        StatuteDefinition("company-law", "中华人民共和国公司法", "company", "company-code"),
        StatuteDefinition("criminal-law", "中华人民共和国刑法", "criminal", "criminal-code"),
    ]

    summary = runner.ingest_all(
        definitions,
        clean_text_directory=tmp_path,
    )

    assert [item.slug for item in summary.succeeded] == ["company-law"]
    assert [(item.slug, item.reason) for item in summary.failed] == [
        ("criminal-law", "条号重复: 1")
    ]
    assert service.rebuilt == [("company-law", COMPANY_LAW)]
