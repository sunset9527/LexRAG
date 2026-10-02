"""v2.3 富文档解析器测试。"""

import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ingestion.rich_document_parser import parse_document_details


def build_native_contract_pdf(path: Path) -> None:
    """生成带重复页眉页脚和矢量表格的自编 PDF 样本。"""
    document = fitz.open()
    for page_number, body in enumerate(("Clause 1 employment term.", "Clause 2 monthly salary."), start=1):
        page = document.new_page()
        page.insert_text((50, 36), "Labor Contract")
        page.insert_text((50, 100), body)
        if page_number == 1:
            for x in (50, 220, 390):
                page.draw_line((x, 180), (x, 260))
            for y in (180, 220, 260):
                page.draw_line((50, y), (390, y))
            page.insert_text((60, 205), "Role")
            page.insert_text((230, 205), "Engineer")
            page.insert_text((60, 245), "Salary")
            page.insert_text((230, 245), "10000")
        page.insert_text((50, 800), f"Page {page_number}")
    document.save(path)
    document.close()


def test_native_pdf_keeps_table_and_removes_repeated_header_footer_from_search_text(tmp_path):
    """原生文本 PDF 不调用 OCR，表格可追溯，重复页眉页脚不参与检索。"""
    source = tmp_path / "劳动合同.pdf"
    build_native_contract_pdf(source)
    ocr_calls = []

    parsed = parse_document_details(
        source,
        ocr_page=lambda _page: ocr_calls.append(True) or ("不应调用", 0.1),
    )

    assert ocr_calls == []
    assert len(parsed.pages) == 2
    assert parsed.pages[0].source == "text"
    assert "Labor Contract" in parsed.pages[0].raw_text
    assert "Labor Contract" not in parsed.pages[0].search_text
    assert "Page 1" not in parsed.pages[0].search_text
    assert parsed.pages[0].header == "Labor Contract"
    assert parsed.pages[0].footer == "Page 1"
    assert parsed.pages[0].tables[0].method == "pymupdf"
    assert parsed.pages[0].tables[0].rows == [["Role", "Engineer"], ["Salary", "10000"]]


def test_scanned_page_uses_injected_ocr_and_preserves_confidence(tmp_path):
    """无文本层的页面应调用 OCR 适配器并保存来源和可信信号。"""
    source = tmp_path / "扫描合同.pdf"
    document = fitz.open()
    document.new_page()
    document.save(source)
    document.close()

    parsed = parse_document_details(
        source,
        ocr_page=lambda _page: ("甲方应当按月支付工资。", 0.93),
    )

    assert len(parsed.pages) == 1
    assert parsed.pages[0].source == "ocr"
    assert parsed.pages[0].raw_text == "甲方应当按月支付工资。"
    assert parsed.pages[0].search_text == "甲方应当按月支付工资。"
    assert parsed.pages[0].ocr_confidence == 0.93
