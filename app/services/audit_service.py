"""审计写入服务：只存动作元数据和内容摘要。"""

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.audit_log import AuditLog

_ALLOWED_QUERY_METADATA = {"cache_hit", "law_area", "knowledge_base", "citation_count"}
_SENSITIVE_METADATA_KEYS = {
    "api_key",
    "authorization",
    "jwt",
    "password",
    "question",
    "answer",
    "content",
    "token",
}


class AuditService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def append_query(
        self,
        *,
        event_id: str,
        organization_id: int,
        actor_user_id: int | None,
        request_id: str | None,
        question: str,
        answer: str,
        verification_status: str,
        metadata: dict | None,
    ) -> bool:
        safe_metadata = {
            "question_sha256": self._sha256(question),
            "answer_sha256": self._sha256(answer),
            "question_length": len(question),
            "answer_length": len(answer),
            "verification_status": verification_status,
        }
        for key, value in (metadata or {}).items():
            if key in _ALLOWED_QUERY_METADATA and isinstance(
                value, (str, int, float, bool, type(None))
            ):
                safe_metadata[key] = value

        with self.session_factory() as db:
            if db.scalar(select(AuditLog.id).where(AuditLog.event_id == event_id)) is not None:
                return False
            db.add(
                AuditLog(
                    event_id=event_id,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    action="query",
                    target_type="legal_query",
                    target_id=None,
                    status="success" if verification_status == "pass" else "unverified",
                    request_id=request_id,
                    metadata_=safe_metadata,
                )
            )
            db.commit()
            return True

    def append_event(
        self,
        *,
        event_id: str,
        organization_id: int,
        actor_user_id: int | None,
        action: str,
        target_type: str,
        target_id: str | None,
        status: str,
        metadata: dict | None = None,
        request_id: str | None = None,
    ) -> bool:
        """记录管理/工具动作；只接受标量白名单并屏蔽敏感名称。"""
        safe_metadata = {
            str(key): value
            for key, value in (metadata or {}).items()
            if str(key).lower() not in _SENSITIVE_METADATA_KEYS
            and isinstance(value, (str, int, float, bool, type(None)))
        }
        with self.session_factory() as db:
            if db.scalar(select(AuditLog.id).where(AuditLog.event_id == event_id)) is not None:
                return False
            db.add(
                AuditLog(
                    event_id=event_id,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    action=action[:64],
                    target_type=target_type[:64],
                    target_id=target_id[:128] if target_id else None,
                    status=status[:16],
                    request_id=request_id[:64] if request_id else None,
                    metadata_=safe_metadata,
                )
            )
            db.commit()
            return True

    @staticmethod
    def _sha256(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
