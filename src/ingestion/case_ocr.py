"""年度案例 PDF 的可断点 OCR 扫描器。"""

from collections.abc import Callable
from pathlib import Path
from typing import Any


def count_pdf_pages(path: Path) -> int:
    """返回 PDF 页数，供登记案例源时记录可复现的输入规模。"""
    import fitz

    document = fitz.open(path)
    try:
        return len(document)
    finally:
        document.close()


class CaseOcrScanner:
    """逐页 OCR，并定期将连续页面交给调用方持久化。"""

    def __init__(
        self,
        *,
        page_count: Callable[[Path], int],
        ocr_page: Callable[[Path, int], str],
    ):
        self._page_count = page_count
        self._ocr_page = ocr_page

    def scan(
        self,
        path: Path,
        *,
        start_page: int = 1,
        checkpoint_size: int = 20,
        on_checkpoint: Callable[[list[dict[str, Any]]], None],
    ) -> list[dict[str, Any]]:
        if checkpoint_size < 1:
            raise ValueError("checkpoint_size 必须大于 0")
        path = Path(path)
        total_pages = self._page_count(path)
        pages: list[dict[str, Any]] = []
        batch: list[dict[str, Any]] = []
        for page_number in range(start_page, total_pages + 1):
            item = {
                "page": page_number,
                "text": self._ocr_page(path, page_number),
                "ocr_source": "ocr",
            }
            pages.append(item)
            batch.append(item)
            if len(batch) == checkpoint_size:
                on_checkpoint(batch)
                batch = []
        if batch:
            on_checkpoint(batch)
        return pages


def build_annual_case_scanner(dpi: int = 150) -> CaseOcrScanner:
    """构造使用 PyMuPDF + RapidOCR 的真实扫描器。"""
    from src.ingestion.pdf_parser import _ocr_page

    import fitz

    def ocr_page(path: Path, page_number: int) -> str:
        document = fitz.open(path)
        try:
            return _ocr_page(document[page_number - 1], dpi=dpi)
        finally:
            document.close()

    return CaseOcrScanner(page_count=count_pdf_pages, ocr_page=ocr_page)
