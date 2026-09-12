"""年度案例 OCR 检查点、规则分案和独立索引的串联测试。"""

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.db.base import Base
import app.models.case_source  # noqa: F401
from app.services.case_ingestion_service import CaseIngestionService
from app.services.case_book_processor import AnnualCaseBookProcessor


class Scanner:
    def scan(self, _path, *, start_page, checkpoint_size, on_checkpoint):
        assert start_page == 1
        assert checkpoint_size == 20
        pages = [
            {"page": 1, "text": "某甲诉某公司案\n【案件焦点】劳动关系是否成立。\n【法院裁判要旨】审查从属性。\n判决如下：驳回。", "ocr_source": "ocr"},
            {"page": 2, "text": "某乙诉某公司案\n【案件焦点】是否拖欠工资。\n【法院裁判要旨】应支付劳动报酬。\n判决如下：支持。", "ocr_source": "ocr"},
        ]
        on_checkpoint(pages)
        return pages


class Indexer:
    def __init__(self):
        self.cases = []

    def upsert_cases(self, cases):
        self.cases.extend(cases)
        return len(cases)


def test_processor_persists_checkpoint_cases_and_separate_index(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    source_file = tmp_path / "labor.pdf"
    source_file.write_bytes(b"case-book")
    service = CaseIngestionService(sessionmaker(bind=engine, expire_on_commit=False), page_counter=lambda _path: 2)
    source = service.register_source(path=source_file, title="劳动案例", domain="labor", publisher_note="用户提供")
    indexer = Indexer()
    processor = AnnualCaseBookProcessor(
        service=service,
        scanner=Scanner(),
        indexer=indexer,
        ocr_root=tmp_path / "ocr",
    )

    result = processor.process(source["id"])

    assert result == {"source_id": source["id"], "processed_pages": 2, "case_count": 2, "indexed_count": 2}
    assert service.get_source(source["id"])["status"] == "COMPLETED"
    assert [case["case_cause"] for case in indexer.cases] == ["确认劳动关系纠纷", "劳动报酬纠纷"]
    assert (tmp_path / "ocr" / str(source["id"]) / "pages.jsonl").is_file()
