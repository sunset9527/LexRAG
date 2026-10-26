"""Health and readiness response contracts."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    components: dict[str, str]


class ReadinessResponse(BaseModel):
    status: str
    components: dict[str, str]
