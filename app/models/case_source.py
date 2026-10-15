"""年度案例来源、处理任务与结构化案例模型。"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CaseSource(Base):
    __tablename__ = "case_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    publisher_note: Mapped[str] = mapped_column(Text, nullable=False)
    origin_label: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    processed_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CaseIngestionJob(Base):
    __tablename__ = "case_ingestion_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("case_sources.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    current_page: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LegalCase(Base):
    __tablename__ = "legal_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("case_sources.id"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    case_cause: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    court_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    case_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    judgment_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    key_facts: Mapped[str] = mapped_column(Text, nullable=False)
    issues: Mapped[str | None] = mapped_column(Text, nullable=True)
    court_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    judgment_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_commentary: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_basis: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end_page: Mapped[int] = mapped_column(Integer, nullable=False)
    extraction_warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
