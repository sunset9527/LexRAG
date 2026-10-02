"""可解释的跨文档关联边。"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentRelation(Base):
    """一条必须附带法条、相似度或原文依据的关联。"""

    __tablename__ = "document_relations"
    __table_args__ = (
        CheckConstraint(
            "law_article IS NOT NULL OR similarity IS NOT NULL OR evidence_text IS NOT NULL",
            name="ck_document_relations_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("document_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_locator: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    law_article: Mapped[str | None] = mapped_column(String(128), nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
