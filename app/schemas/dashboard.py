"""Dashboard response contracts."""

from __future__ import annotations

from pydantic import BaseModel


class DashboardStatsResponse(BaseModel):
    case_count: int
    source_count: int
