"""案例来源登记与后续 OCR 入库的业务入口。"""

from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.case_source import CaseSource, LegalCase
from src.ingestion.case_parser import ParsedAnnualCase


class CaseIngestionService:
    """管理用户提供年度案例文件的来源记录。"""

    origin_label = "用户提供的年度案例汇编"

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        page_counter: Callable[[Path], int],
    ):
        self._session_factory = session_factory
        self._page_counter = page_counter

    def register_source(
        self,
        *,
        path: Path,
        title: str,
        domain: str,
        publisher_note: str,
    ) -> dict[str, Any]:
        path = Path(path)
        if not path.is_file():
            raise ValueError(f"案例来源文件不存在: {path}")
        file_hash = sha256(path.read_bytes()).hexdigest()
        with self._session_factory() as session:
            existing = session.scalar(select(CaseSource).where(CaseSource.file_sha256 == file_hash))
            if existing is not None:
                return self._serialize(existing)
            source = CaseSource(
                title=title,
                domain=domain,
                source_path=str(path.resolve()),
                original_filename=path.name,
                file_sha256=file_hash,
                page_count=self._page_counter(path),
                publisher_note=publisher_note,
                origin_label=self.origin_label,
                status="PENDING",
                processed_pages=0,
                ocr_engine="RapidOCR",
            )
            session.add(source)
            session.commit()
            session.refresh(source)
            return self._serialize(source)

    def persist_case(
        self,
        *,
        source_id: int,
        sequence_no: int,
        parsed: ParsedAnnualCase,
    ) -> dict[str, Any]:
        """将规则解析结果持久化；缺失字段按解析器结果原样保留。"""
        with self._session_factory() as session:
            if session.get(CaseSource, source_id) is None:
                raise ValueError(f"案例来源不存在: {source_id}")
            case = LegalCase(
                id=str(uuid5(NAMESPACE_URL, f"lexrag:case-source:{source_id}:sequence:{sequence_no}")),
                source_id=source_id,
                sequence_no=sequence_no,
                title=parsed.title,
                domain=parsed.domain,
                case_cause=parsed.case_cause,
                key_facts=parsed.key_facts,
                issues=parsed.issues,
                court_reasoning=parsed.court_reasoning,
                judgment_result=parsed.judgment_result,
                judge_commentary=parsed.judge_commentary,
                legal_basis=parsed.legal_basis,
                source_start_page=parsed.source_start_page,
                source_end_page=parsed.source_end_page,
                extraction_warnings=parsed.extraction_warnings,
            )
            session.add(case)
            session.commit()
            session.refresh(case)
            return self._serialize_case(case)

    def list_cases(
        self,
        *,
        domain: str | None = None,
        case_cause: str | None = None,
        source_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """按页面筛选条件读取结构化案例。"""
        statement = select(LegalCase).order_by(LegalCase.source_id, LegalCase.sequence_no)
        if domain:
            statement = statement.where(LegalCase.domain == domain)
        if case_cause:
            statement = statement.where(LegalCase.case_cause == case_cause)
        if source_id is not None:
            statement = statement.where(LegalCase.source_id == source_id)
        with self._session_factory() as session:
            return [self._serialize_case(case) for case in session.scalars(statement).all()]

    def get_source(self, source_id: int) -> dict[str, Any]:
        with self._session_factory() as session:
            source = session.get(CaseSource, source_id)
            if source is None:
                raise ValueError(f"案例来源不存在: {source_id}")
            return self._serialize(source)

    def update_source_progress(
        self,
        source_id: int,
        *,
        status: str,
        processed_pages: int,
        error_message: str | None = None,
    ) -> None:
        """持久化检查点状态，以便进程中断后从已写入页继续。"""
        with self._session_factory() as session:
            source = session.get(CaseSource, source_id)
            if source is None:
                raise ValueError(f"案例来源不存在: {source_id}")
            source.status = status
            source.processed_pages = processed_pages
            source.error_message = error_message
            session.commit()

    def clear_cases_for_source(self, source_id: int) -> None:
        """重建结构化结果前删除该来源旧记录；向量 ID 保持稳定以覆盖旧向量。"""
        with self._session_factory() as session:
            if session.get(CaseSource, source_id) is None:
                raise ValueError(f"案例来源不存在: {source_id}")
            session.execute(delete(LegalCase).where(LegalCase.source_id == source_id))
            session.commit()

    def list_sources(self, *, domain: str | None = None) -> list[dict[str, Any]]:
        """返回案例源及其 OCR 进度，不泄露或伪造外部官方链接。"""
        statement = select(CaseSource).order_by(CaseSource.id)
        if domain:
            statement = statement.where(CaseSource.domain == domain)
        with self._session_factory() as session:
            return [self._serialize(source) for source in session.scalars(statement).all()]

    def get_statistics(self) -> dict[str, int]:
        """返回首页可展示的真实结构化案例与来源数量。"""
        with self._session_factory() as session:
            return {
                "case_count": int(session.scalar(select(func.count()).select_from(LegalCase)) or 0),
                "source_count": int(session.scalar(select(func.count()).select_from(CaseSource)) or 0),
            }

    def get_case(self, case_id: str) -> dict[str, Any]:
        """读取一条结构化案例；原始页码随结果返回以便人工复核。"""
        with self._session_factory() as session:
            case = session.get(LegalCase, case_id)
            if case is None:
                raise ValueError(f"案例不存在: {case_id}")
            return self._serialize_case(case)

    @staticmethod
    def _serialize(source: CaseSource) -> dict[str, Any]:
        return {
            "id": source.id,
            "title": source.title,
            "domain": source.domain,
            "source_path": source.source_path,
            "original_filename": source.original_filename,
            "file_sha256": source.file_sha256,
            "page_count": source.page_count,
            "publisher_note": source.publisher_note,
            "origin_label": source.origin_label,
            "status": source.status,
            "processed_pages": source.processed_pages,
            "error_message": source.error_message,
        }

    @staticmethod
    def _serialize_case(case: LegalCase) -> dict[str, Any]:
        return {
            "id": case.id,
            "source_id": case.source_id,
            "sequence_no": case.sequence_no,
            "title": case.title,
            "domain": case.domain,
            "case_cause": case.case_cause,
            "key_facts": case.key_facts,
            "issues": case.issues,
            "court_reasoning": case.court_reasoning,
            "judgment_result": case.judgment_result,
            "judge_commentary": case.judge_commentary,
            "legal_basis": case.legal_basis,
            "source_start_page": case.source_start_page,
            "source_end_page": case.source_end_page,
            "extraction_warnings": case.extraction_warnings,
        }
