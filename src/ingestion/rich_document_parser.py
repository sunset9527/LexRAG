"""将 PDF 解析为带页面来源、表格和去噪检索文本的结果。"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExtractedTable:
    """一张原生 PDF 表格的可追溯内容。"""

    rows: list[list[str | None]]
    bbox: tuple[float, float, float, float]
    method: str = "pymupdf"


@dataclass
class ParsedPage:
    """单页的原始文本、检索文本及解析信号。"""

    page_number: int
    raw_text: str
    search_text: str
    source: str
    ocr_confidence: float | None = None
    tables: list[ExtractedTable] = field(default_factory=list)
    header: str | None = None
    footer: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """一份文档的逐页深度解析结果。"""

    pages: list[ParsedPage]


OcrPage = Callable[[object], tuple[str, float | None] | str]


def parse_document_details(
    path: str | Path,
    *,
    ocr_page: OcrPage | None = None,
    ocr_char_threshold: int = 20,
) -> ParsedDocument:
    """解析 PDF，并保留 OCR、表格和重复页眉页脚的处理结果。"""
    import fitz

    document_path = Path(path)
    if document_path.suffix.lower() != ".pdf":
        raise ValueError("富文档解析当前仅支持 PDF 文件")
    ocr = ocr_page or _default_ocr_page
    document = fitz.open(document_path)
    pages: list[ParsedPage] = []
    try:
        for page_number, page in enumerate(document, start=1):
            raw_text = (page.get_text("text") or "").strip()
            source = "text"
            confidence: float | None = None
            warnings: list[str] = []
            if len(raw_text) < ocr_char_threshold:
                try:
                    raw_text, confidence = _normalize_ocr_result(ocr(page))
                    source = "ocr" if raw_text else "empty"
                except Exception as exc:  # OCR 是可降级步骤，不能中止其余页面。
                    raw_text = ""
                    source = "empty"
                    warnings.append(f"OCR 失败: {exc}")
            pages.append(
                ParsedPage(
                    page_number=page_number,
                    raw_text=raw_text,
                    search_text=raw_text,
                    source=source,
                    ocr_confidence=confidence,
                    tables=_extract_tables(page, warnings),
                    warnings=warnings,
                )
            )
    finally:
        document.close()

    _remove_repeated_header_footer(pages)
    return ParsedDocument(pages=pages)


def _default_ocr_page(page: object) -> str:
    """复用既有 RapidOCR 回退，并保持模型延迟加载。"""
    from src.ingestion.pdf_parser import _ocr_page

    return _ocr_page(page)


def _normalize_ocr_result(result: tuple[str, float | None] | str) -> tuple[str, float | None]:
    if isinstance(result, tuple):
        text, confidence = result
        return str(text).strip(), confidence
    return str(result).strip(), None


def _extract_tables(page: object, warnings: list[str]) -> list[ExtractedTable]:
    try:
        finder = page.find_tables()
        return [
            ExtractedTable(
                rows=table.extract(),
                bbox=tuple(table.bbox),
            )
            for table in finder.tables
        ]
    except Exception as exc:  # 表格识别失败时仍保留页面正文。
        warnings.append(f"表格提取失败: {exc}")
        return []


def _remove_repeated_header_footer(pages: list[ParsedPage]) -> None:
    """只移除跨至少两页重复的首尾短行，避免误删单页正文。"""
    headers = Counter()
    footers = Counter()
    page_lines: dict[int, list[str]] = {}
    for page in pages:
        lines = [line.strip() for line in page.raw_text.splitlines() if line.strip()]
        page_lines[page.page_number] = lines
        if lines:
            headers[_normalize_repeated_line(lines[0])] += 1
            footers[_normalize_repeated_line(lines[-1])] += 1

    repeated_headers = {line for line, count in headers.items() if count >= 2}
    repeated_footers = {line for line, count in footers.items() if count >= 2}
    for page in pages:
        lines = page_lines[page.page_number]
        if not lines:
            continue
        header = lines[0] if _normalize_repeated_line(lines[0]) in repeated_headers else None
        footer = lines[-1] if _normalize_repeated_line(lines[-1]) in repeated_footers else None
        page.header = header
        page.footer = footer
        search_lines = lines[:]
        if header is not None:
            search_lines = search_lines[1:]
        if footer is not None and search_lines:
            search_lines = search_lines[:-1]
        page.search_text = "\n".join(search_lines)


def _normalize_repeated_line(line: str) -> str:
    return re.sub(r"\d+", "#", line).strip()
