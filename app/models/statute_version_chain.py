"""可追溯的法规基准全文与修正案版本链。"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StatuteVersionChain(Base):
    __tablename__ = "statute_version_chains"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    law_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_version_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    consolidated_source_import_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("legal_source_imports.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class StatuteVersionChainMember(Base):
    __tablename__ = "statute_version_chain_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chain_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("statute_version_chains.id", ondelete="CASCADE"), nullable=False
    )
    source_import_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("legal_source_imports.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("chain_id", "source_import_id", name="uq_statute_chain_member_source"),
        UniqueConstraint("chain_id", "sequence", name="uq_statute_chain_member_sequence"),
    )
