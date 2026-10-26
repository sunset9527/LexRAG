"""Knowledge-base request and response contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    slug: str = Field(..., pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    law_area: str = Field(..., min_length=1, max_length=64)


class KnowledgeBaseRebuildRequest(BaseModel):
    content: str = Field(..., min_length=1)


class UploadRequest(BaseModel):
    knowledge_base_slug: str = Field(..., pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    content: str = Field(..., description="法律文档内容")
    law_name: str = Field(..., description="法律名称")
    version: str = Field("v1.0", description="版本号")


class KnowledgeBaseListResponse(BaseModel):
    items: list[dict[str, Any]]
