"""登记或处理用户提供的年度案例 PDF。"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import session as db_session
from app.db.session import init_db
from app.services.case_book_processor import AnnualCaseBookProcessor
from app.services.case_ingestion_service import CaseIngestionService
from config import settings
from src.ingestion.annual_case_indexer import AnnualCaseIndexer
from src.ingestion.case_ocr import build_annual_case_scanner, count_pdf_pages


def infer_domain(filename: str) -> str:
    if "劳动" in filename:
        return "labor"
    if "公司" in filename:
        return "company"
    if "知识产权" in filename:
        return "intellectual_property"
    if "刑事" in filename:
        return "criminal"
    if "合同" in filename:
        return "contract"
    if "物权" in filename:
        return "property"
    if "执行" in filename:
        return "enforcement"
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser(description="年度案例 PDF 入库：默认仅登记来源，不执行 OCR")
    parser.add_argument("input_dir", type=Path, help="存放用户提供 PDF 的目录")
    parser.add_argument("--process", action="store_true", help="显式执行 OCR、结构化解析和案例索引")
    parser.add_argument("--filename", help="仅处理指定文件名")
    args = parser.parse_args()

    files = sorted(args.input_dir.glob("*.pdf"))
    if args.filename:
        files = [path for path in files if path.name == args.filename]
    if not files:
        raise SystemExit("未找到待登记的 PDF 文件")

    init_db()
    service = CaseIngestionService(db_session.SessionLocal, page_counter=count_pdf_pages)
    sources = []
    for path in files:
        source = service.register_source(
            path=path,
            title=path.stem,
            domain=infer_domain(path.name),
            publisher_note="用户提供的本地年度案例 PDF；保留文件哈希和本地路径用于追溯。",
        )
        sources.append(source)
        print(f"已登记: id={source['id']} | {source['domain']} | {path.name} | {source['page_count']} 页")

    if not args.process:
        print("仅完成来源登记。需要执行 OCR 时，重新运行并加 --process；建议先用 --filename 指定一本验证。")
        return

    processor = AnnualCaseBookProcessor(
        service=service,
        scanner=build_annual_case_scanner(),
        indexer=AnnualCaseIndexer(),
        ocr_root=Path(settings.cases_data_path) / "ocr",
    )
    for source in sources:
        result = processor.process(source["id"])
        print(f"已完成: {result}")


if __name__ == "__main__":
    main()
