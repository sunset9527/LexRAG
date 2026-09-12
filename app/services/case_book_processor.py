"""年度案例从 OCR 检查点到结构化案例、独立索引的处理编排。"""

import json
from pathlib import Path
from typing import Any

from app.services.case_ingestion_service import CaseIngestionService
from src.ingestion.case_classifier import RuleBasedCaseCauseClassifier
from src.ingestion.case_parser import AnnualCaseParser


class AnnualCaseBookProcessor:
    """处理一份已登记案例源；OCR 页文本落盘后可从检查点恢复。"""

    def __init__(self, *, service: CaseIngestionService, scanner: Any, indexer: Any, ocr_root: Path):
        self._service = service
        self._scanner = scanner
        self._indexer = indexer
        self._ocr_root = Path(ocr_root)

    def process(self, source_id: int) -> dict[str, int]:
        source = self._service.get_source(source_id)
        pages_file = self._ocr_root / str(source_id) / "pages.jsonl"
        pages = self._read_pages(pages_file)
        start_page = (pages[-1]["page"] + 1) if pages else 1
        self._service.update_source_progress(
            source_id, status="OCR_RUNNING", processed_pages=len(pages),
        )

        def checkpoint(batch: list[dict[str, Any]]) -> None:
            self._append_pages(pages_file, batch)
            self._service.update_source_progress(
                source_id, status="OCR_RUNNING", processed_pages=batch[-1]["page"],
            )

        try:
            self._scanner.scan(
                Path(source["source_path"]),
                start_page=start_page,
                checkpoint_size=20,
                on_checkpoint=checkpoint,
            )
            pages = self._read_pages(pages_file)
            self._service.update_source_progress(
                source_id, status="STRUCTURING", processed_pages=len(pages),
            )
            cases = self._parse_cases(source, pages)
            self._service.clear_cases_for_source(source_id)
            persisted = [
                self._service.persist_case(source_id=source_id, sequence_no=index + 1, parsed=parsed)
                for index, parsed in enumerate(cases)
            ]
            indexed_count = self._indexer.upsert_cases(persisted)
            self._service.update_source_progress(
                source_id, status="COMPLETED", processed_pages=len(pages),
            )
            return {
                "source_id": source_id,
                "processed_pages": len(pages),
                "case_count": len(persisted),
                "indexed_count": indexed_count,
            }
        except Exception as exc:
            self._service.update_source_progress(
                source_id, status="FAILED", processed_pages=len(self._read_pages(pages_file)), error_message=str(exc),
            )
            raise

    def _parse_cases(self, source: dict[str, Any], pages: list[dict[str, Any]]):
        groups = self._split_by_focus(pages)
        parser = AnnualCaseParser(domain=source["domain"])
        classifier = RuleBasedCaseCauseClassifier(domain=source["domain"])
        parsed_cases = []
        for sequence_no, group in enumerate(groups, start=1):
            text = "\n".join(item["text"] for item in group)
            parsed = parser.parse_case(
                sequence_no=sequence_no,
                case_cause=classifier.classify(text),
                pages=group,
            )
            parsed.extraction_warnings.append("按“案件焦点”页自动切分，建议人工复核页码边界")
            parsed_cases.append(parsed)
        return parsed_cases

    @staticmethod
    def _split_by_focus(pages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        anchors = [index for index, page in enumerate(pages) if "【案件焦点】" in page.get("text", "")]
        if not anchors:
            return [pages] if pages else []
        return [pages[start:end] for start, end in zip(anchors, anchors[1:] + [len(pages)])]

    @staticmethod
    def _read_pages(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    @staticmethod
    def _append_pages(path: Path, pages: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for page in pages:
                handle.write(json.dumps(page, ensure_ascii=False) + "\n")
