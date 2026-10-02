"""可解释的用户法律领域偏好摘要。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.user import User  # noqa: F401


class UserProfile(Base):
    """只记录通过证据校验的问答聚合计数。"""

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    law_area_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    intent_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
