"""Knowledge-graph request contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class GraphQueryRequest(BaseModel):
    article_id: str | None = Field(default=None, min_length=1)
    source: str | None = Field(default=None, min_length=1)
    target: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_a_complete_query(self) -> GraphQueryRequest:
        if self.article_id or (self.source and self.target):
            return self
        raise ValueError("请提供article_id或source+target")
