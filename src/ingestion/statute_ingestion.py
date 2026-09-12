"""核心法规清洗文本的校验与知识库导入编排。"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any, Mapping, Protocol, Sequence
from xml.etree import ElementTree
from zipfile import ZipFile

from src.ingestion.law_parser import LawParser


class StatuteValidationError(ValueError):
    """清洗后的法规文本不能安全入库。"""


@dataclass(frozen=True)
class StatuteDefinition:
    """一部法规及其独立知识库的稳定标识。"""

    slug: str
    name: str
    law_area: str
    source_id: str
    terminal_article_number: int | None = None
    first_article_marker: str | None = None


@dataclass(frozen=True)
class StatuteValidationReport:
    """不访问数据库即可生成的法规文本验收摘要。"""

    law_name: str
    article_count: int
    first_article_number: int
    last_article_number: int
    clean_text_sha256: str


@dataclass(frozen=True)
class IngestionResult:
    """单部法规的批量导入结果。"""

    slug: str
    reason: str | None = None
    report: StatuteValidationReport | None = None
    knowledge_base: dict[str, Any] | None = None


@dataclass
class IngestionSummary:
    """批量导入汇总，保留每一部法律的独立结果。"""

    succeeded: list[IngestionResult] = field(default_factory=list)
    failed: list[IngestionResult] = field(default_factory=list)


class KnowledgeBaseWriter(Protocol):
    """导入管线依赖的最小服务契约。"""

    def create_knowledge_base(self, *, name: str, slug: str, law_area: str) -> dict[str, Any]: ...

    def rebuild_knowledge_base(self, slug: str, *, content: str) -> dict[str, Any]: ...


class _EpubHtmlTextExtractor(HTMLParser):
    """将 EPUB XHTML 的可见文字转换为按块换行的纯文本。"""

    _BLOCK_TAGS = {"article", "br", "div", "h1", "h2", "h3", "h4", "li", "p", "section"}
    _IGNORED_TAGS = {"script", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._IGNORED_TAGS:
            self._ignored_depth += 1
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._parts.append(data)

    def text(self) -> str:
        return "\n".join(
            " ".join(line.split())
            for line in "".join(self._parts).splitlines()
            if line.strip()
        )


def extract_epub_text(epub_path: Path) -> str:
    """按 EPUB 阅读顺序提取 XHTML 正文；简化 EPUB 则回退到文件名顺序。"""
    with ZipFile(epub_path) as archive:
        chapter_names = _epub_chapter_names(archive)
        extracted_parts: list[str] = []
        for chapter_name in chapter_names:
            extractor = _EpubHtmlTextExtractor()
            extractor.feed(_decode_epub_html(archive.read(chapter_name)))
            text = extractor.text()
            if text:
                extracted_parts.append(text)
        return "\n".join(extracted_parts)


def _decode_epub_html(raw_html: bytes) -> str:
    """优先遵守页面字符集声明，未声明时安全回退到常见中文编码。"""
    declaration = raw_html[:2048].decode("ascii", errors="ignore")
    match = re.search(
        r"(?:charset|encoding)\\s*=\\s*['\"]?([A-Za-z0-9_-]+)",
        declaration,
        flags=re.IGNORECASE,
    )
    encodings = [match.group(1)] if match else []
    encodings.extend(["utf-8-sig", "gb18030"])
    for encoding in dict.fromkeys(encodings):
        try:
            return raw_html.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw_html.decode("utf-8", errors="replace")


def _epub_chapter_names(archive: ZipFile) -> list[str]:
    """读取 OPF spine；遇到非标准 EPUB 时以 HTML 文件名回退。"""
    html_names = sorted(
        name
        for name in archive.namelist()
        if name.lower().endswith((".html", ".htm", ".xhtml"))
    )
    try:
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = next(
            element.attrib["full-path"]
            for element in container.iter()
            if element.tag.endswith("rootfile")
        )
        package = ElementTree.fromstring(archive.read(rootfile))
        manifest = next(element for element in package if element.tag.endswith("manifest"))
        spine = next(element for element in package if element.tag.endswith("spine"))
        href_by_id = {
            item.attrib["id"]: item.attrib["href"]
            for item in manifest
            if item.tag.endswith("item") and item.attrib.get("href", "").lower().endswith(
                (".html", ".htm", ".xhtml")
            )
        }
        opf_directory = str(Path(rootfile).parent).replace("\\", "/")
        chapter_names = []
        for itemref in spine:
            href = href_by_id.get(itemref.attrib.get("idref", ""))
            if href:
                chapter_names.append(f"{opf_directory}/{href}".lstrip("/"))
        return chapter_names or html_names
    except (KeyError, StopIteration, ElementTree.ParseError):
        return html_names


_ARTICLE_START = re.compile(r"^第[一二三四五六七八九十百千零\d]+条")
_STRUCTURE_TITLE = re.compile(r"^第[一二三四五六七八九十百千零\d]+[编章节]")
_ARTICLE_DECORATION = re.compile(r"【[^】]*】|\[\d+\]")
_ANNOTATION_START = re.compile(r"^(?:注释|［|链接|理解与适用|相关规定)")
_LAW_TITLE_LINE = re.compile(r"^中华人民共和国.+(?:法|条例|规定|决定|修正案)(?:（|\(|$)")
_STANDALONE_FOOTNOTE = re.compile(r"^\[\d+\]$")


def clean_statute_from_source(source_text: str, definition: StatuteDefinition) -> str:
    """从带目录和注释的法规汇编中切出一部法律的最小正文。"""
    if definition.terminal_article_number is None:
        raise StatuteValidationError(f"缺少末条号规则: {definition.slug}")

    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    for title_index, line in enumerate(lines):
        if not line.startswith(definition.name):
            continue
        next_title_index = next(
            (
                index
                for index in range(title_index + 1, len(lines))
                if lines[index].startswith(definition.name)
            ),
            len(lines),
        )
        first_article_index = _find_first_article_index(
            lines,
            title_index,
            definition.first_article_marker,
            stop_index=next_title_index,
        )
        if first_article_index is None:
            continue
        cleaned = [definition.name]
        cleaned.extend(
            line
            for line in lines[title_index + 1 : first_article_index]
            if _STRUCTURE_TITLE.match(line)
        )
        is_collecting_body = False
        terminal_started = False
        for line in lines[first_article_index:]:
            if _ARTICLE_START.match(line):
                if terminal_started:
                    return "\n".join(cleaned)
                normalized = " ".join(_ARTICLE_DECORATION.sub(" ", line).split())
                cleaned.append(normalized)
                article = LawParser().parse_law_content(normalized, definition.name)[0]
                is_collecting_body = True
                if _article_number_sort_key(article.article_number)[0] == definition.terminal_article_number:
                    terminal_started = True
            elif _STRUCTURE_TITLE.match(line):
                if terminal_started:
                    return "\n".join(cleaned)
                cleaned.append(line)
                is_collecting_body = False
            elif terminal_started and _LAW_TITLE_LINE.match(line):
                return "\n".join(cleaned)
            elif _ANNOTATION_START.match(line):
                is_collecting_body = False
            elif _STANDALONE_FOOTNOTE.match(line):
                continue
            elif is_collecting_body:
                cleaned.append(line)

        if terminal_started:
            return "\n".join(cleaned)

    raise StatuteValidationError(f"未找到完整正文边界: {definition.name}")


def _find_first_article_index(
    lines: list[str], title_index: int, marker: str | None, *, stop_index: int
) -> int | None:
    """识别标题后的真实第一条，跳过目录中的“第一条”条目。"""
    for index in range(title_index + 1, min(title_index + 80, stop_index)):
        line = lines[index]
        if not line.startswith("第一条"):
            continue
        nearby_text = " ".join(lines[index : index + 2])
        if marker is None or marker in nearby_text:
            return index
    return None


def _article_number_sort_key(article_number: str) -> tuple[int, int]:
    """将普通条和“第十七条之一”映射为可比较的稳定顺序。"""
    parts = article_number.split("-", maxsplit=1)
    try:
        base = int(parts[0])
        inserted = int(parts[1]) if len(parts) == 2 else 0
    except ValueError as exc:
        raise StatuteValidationError(f"非法条号: {article_number}") from exc
    return base, inserted


def build_source_manifest_entry(
    *,
    source_id: str,
    source_path: Path,
    laws: list[str],
    extracted_at: str,
    extractor: str,
) -> dict[str, Any]:
    """为用户提供的原始文件生成可复核的来源登记。"""
    if not source_path.is_file():
        raise FileNotFoundError(f"原始来源文件不存在: {source_path}")
    return {
        "source_id": source_id,
        "original_file_name": source_path.name,
        "original_file_path": str(source_path.resolve()),
        "original_file_sha256": sha256(source_path.read_bytes()).hexdigest(),
        "laws": laws,
        "extracted_at": extracted_at,
        "extractor": extractor,
        "source_assertion": "user_confirmed_official",
    }


def prepare_statute_sources(
    source_files: Mapping[str, Path],
    definitions: Sequence[StatuteDefinition],
    *,
    raw_directory: Path,
    clean_text_directory: Path,
    extracted_at: str,
) -> dict[str, Any]:
    """从原始 EPUB 生成保留文本、单法清洗文本及可追溯来源清单。"""
    raw_directory.mkdir(parents=True, exist_ok=True)
    clean_text_directory.mkdir(parents=True, exist_ok=True)
    definitions_by_source: dict[str, list[StatuteDefinition]] = {}
    for definition in definitions:
        definitions_by_source.setdefault(definition.source_id, []).append(definition)

    source_entries: list[dict[str, Any]] = []
    law_entries: dict[str, dict[str, Any]] = {}
    for source_id, source_path in source_files.items():
        source_definitions = definitions_by_source.get(source_id, [])
        if not source_definitions:
            continue
        extracted_text = extract_epub_text(source_path)
        extracted_path = raw_directory / source_id / "extracted.txt"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text(extracted_text, encoding="utf-8")
        source_entries.append(
            build_source_manifest_entry(
                source_id=source_id,
                source_path=source_path,
                laws=[definition.slug for definition in source_definitions],
                extracted_at=extracted_at,
                extractor="epub-html-v1",
            )
        )
        for definition in source_definitions:
            clean_text = clean_statute_from_source(extracted_text, definition)
            report = validate_clean_law_text(clean_text, definition)
            clean_path = clean_text_directory / f"{definition.slug}.txt"
            clean_path.write_text(clean_text, encoding="utf-8")
            law_entries[definition.slug] = {
                "source_id": definition.source_id,
                "law_name": report.law_name,
                "clean_text_file": str(clean_path.relative_to(clean_text_directory.parent)),
                "clean_text_sha256": report.clean_text_sha256,
                "article_count": report.article_count,
                "first_article_number": report.first_article_number,
                "last_article_number": report.last_article_number,
            }

    manifest = {"sources": source_entries, "laws": law_entries}
    (raw_directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def validate_clean_law_text(
    content: str, definition: StatuteDefinition
) -> StatuteValidationReport:
    """校验单部法规标题、条号连续顺序和可解析性。"""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        raise StatuteValidationError("清洗文本为空")
    if lines[0] != definition.name:
        raise StatuteValidationError(
            f"法律标题不匹配: 期望 {definition.name}，实际 {lines[0]}"
        )

    articles = LawParser().parse_law_content(content, definition.name)
    if not articles:
        raise StatuteValidationError("未解析到法条")

    article_numbers = [article.article_number for article in articles]
    article_keys = [_article_number_sort_key(number) for number in article_numbers]

    seen: set[str] = set()
    previous: tuple[int, int] | None = None
    for number, key in zip(article_numbers, article_keys):
        if number in seen:
            raise StatuteValidationError(f"条号重复: {number}")
        if previous is not None and key <= previous:
            raise StatuteValidationError(f"条号未严格递增: {previous} -> {number}")
        seen.add(number)
        previous = key

    return StatuteValidationReport(
        law_name=definition.name,
        article_count=len(articles),
        first_article_number=article_keys[0][0],
        last_article_number=article_keys[-1][0],
        clean_text_sha256=sha256(content.encode("utf-8")).hexdigest(),
    )


class StatuteIngestionRunner:
    """以知识库服务为唯一写入入口，批量导入互不影响。"""

    def __init__(self, knowledge_base_service: KnowledgeBaseWriter):
        self._knowledge_base_service = knowledge_base_service

    def ingest_all(
        self,
        definitions: Sequence[StatuteDefinition],
        *,
        clean_text_directory: Path,
    ) -> IngestionSummary:
        """逐库校验、入库，记录失败但继续处理后续法律。"""
        summary = IngestionSummary()
        for definition in definitions:
            try:
                result = self.ingest_one(
                    definition, clean_text_directory=clean_text_directory
                )
            except (OSError, StatuteValidationError, ValueError) as exc:
                summary.failed.append(IngestionResult(definition.slug, reason=str(exc)))
            else:
                summary.succeeded.append(result)
        return summary

    def ingest_one(
        self,
        definition: StatuteDefinition,
        *,
        clean_text_directory: Path,
    ) -> IngestionResult:
        """校验一部法规后创建或复用其注册记录并重建专属索引。"""
        text_path = clean_text_directory / f"{definition.slug}.txt"
        content = text_path.read_text(encoding="utf-8")
        report = validate_clean_law_text(content, definition)
        try:
            self._knowledge_base_service.create_knowledge_base(
                name=definition.name,
                slug=definition.slug,
                law_area=definition.law_area,
            )
        except ValueError as exc:
            if "已存在" not in str(exc):
                raise
        knowledge_base = self._knowledge_base_service.rebuild_knowledge_base(
            definition.slug, content=content
        )
        return IngestionResult(
            slug=definition.slug,
            report=report,
            knowledge_base=knowledge_base,
        )
