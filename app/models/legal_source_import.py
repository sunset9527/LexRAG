"""Stage 4 本地法规原件的候选导入记录。"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LegalSourceImport(Base):
    """未完成权威核验的法规版本原件，不能直接用于问答。"""

    __tablename__ = "legal_source_imports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    law_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    law_name: Mapped[str] = mapped_column(String(128), nullable=False)
    version_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    raw_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False)
    promulgated_on: Mapped[date] = mapped_column(Date, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    source_status: Mapped[str] = mapped_column(String(40), nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False, default="STATUTE")
    authority_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="PENDING_REVIEW"
    )
    authority_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    verified_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("version_id", "raw_sha256", name="uq_legal_source_import_version_raw"),
    )
