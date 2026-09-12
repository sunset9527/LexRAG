"""案例 OCR checkpoint 扫描测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ingestion.case_ocr import CaseOcrScanner


def test_scanner_resumes_from_page_and_emits_fixed_checkpoints():
    """重跑时只扫描未完成页，并在固定页数后持久化检查点。"""
    checkpoints = []
    scanner = CaseOcrScanner(
        page_count=lambda _path: 5,
        ocr_page=lambda _path, page: f"第{page}页案例文本",
    )

    pages = scanner.scan(
        Path("labor.pdf"),
        start_page=3,
        checkpoint_size=2,
        on_checkpoint=lambda batch: checkpoints.append(batch),
    )

    assert [item["page"] for item in pages] == [3, 4, 5]
    assert [[item["page"] for item in batch] for batch in checkpoints] == [[3, 4], [5]]
