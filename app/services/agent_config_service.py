"""组织级 Agent 安全配置服务。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.agent_config import AgentConfig


class AgentConfigService:
    _DEFAULTS = {
        "case_search_enabled": True,
        "graph_search_enabled": True,
        "top_k": 5,
        "timeout_seconds": 30,
        "model_alias": "browser-configured",
        "version_note": "",
    }
    _ALLOWED_KEYS = frozenset(_DEFAULTS)

    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return dict(cls._DEFAULTS)

    def get(self, *, organization_id: int) -> dict[str, Any]:
        with self.session_factory() as db:
            item = db.scalar(select(AgentConfig).where(AgentConfig.organization_id == organization_id))
            return self._serialize(item) if item else self.defaults()

    def upsert(self, *, organization_id: int, values: dict[str, Any]) -> dict[str, Any]:
        unknown = set(values) - self._ALLOWED_KEYS
        if unknown:
            raise ValueError(f"不允许配置字段: {', '.join(sorted(unknown))}")
        merged = {**self.defaults(), **values}
        self._validate(merged)
        with self.session_factory() as db:
            item = db.scalar(select(AgentConfig).where(AgentConfig.organization_id == organization_id))
            if item is None:
                item = AgentConfig(organization_id=organization_id, **merged)
                db.add(item)
            else:
                for key, value in merged.items():
                    setattr(item, key, value)
            db.commit()
            db.refresh(item)
            return self._serialize(item)

    @classmethod
    def _validate(cls, values: dict[str, Any]) -> None:
        if not isinstance(values["top_k"], int) or not 1 <= values["top_k"] <= 20:
            raise ValueError("top_k 必须是 1 到 20 的整数")
        if not isinstance(values["timeout_seconds"], int) or not 5 <= values["timeout_seconds"] <= 120:
            raise ValueError("timeout_seconds 必须是 5 到 120 的整数")
        for key in ("case_search_enabled", "graph_search_enabled"):
            if not isinstance(values[key], bool):
                raise ValueError(f"{key} 必须为布尔值")
        if not isinstance(values["model_alias"], str) or not 1 <= len(values["model_alias"]) <= 64:
            raise ValueError("model_alias 长度必须在 1 到 64 之间")
        if not isinstance(values["version_note"], str) or len(values["version_note"]) > 256:
            raise ValueError("version_note 长度不能超过 256")

    @classmethod
    def _serialize(cls, item: AgentConfig) -> dict[str, Any]:
        return {key: getattr(item, key) for key in cls._ALLOWED_KEYS}
