"""Query request and response contracts."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., description="用户问题")
    session_id: str | None = Field(None, description="会话ID")
    config: dict[str, Any] | None = Field(default_factory=dict, description="配置参数")
    knowledge_base_ids: list[str] = Field(default_factory=list, description="限定检索的知识库 ID")
    case_date: date | None = Field(None, description="案件发生日期，格式 YYYY-MM-DD")


class QueryResponse(BaseModel):
    query_id: str
    query: str
    answer: str
    intent: str
    citations: list[dict[str, Any]]
    verification_status: str
    verification_issues: list[str]
    sub_questions: list[dict[str, str]]
    metadata: dict[str, Any]


class QueryRunAccepted(BaseModel):
    query_id: str
