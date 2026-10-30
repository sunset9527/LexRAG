"""组织级 Agent 运行参数；不保存可执行代码或任意工具定义。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentConfig(Base):
    __tablename__ = "agent_configs"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_agent_configs_organization"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_search_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    model_alias: Mapped[str] = mapped_column(
        String(64), nullable=False, default="browser-configured"
    )
    version_note: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
