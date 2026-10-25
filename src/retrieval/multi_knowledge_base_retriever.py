"""在请求范围内对多个法规知识库独立检索。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScopedRetrievalResult:
    knowledge_base_slug: str
    result: Any


class MultiKnowledgeBaseLawRetriever:
    def __init__(self, retrievers: Mapping[str, Any]) -> None:
        self._retrievers = dict(retrievers)

    def retrieve(self, question: str, *, top_k: int = 5) -> list[ScopedRetrievalResult]:
        results: list[ScopedRetrievalResult] = []
        for slug, retriever in self._retrievers.items():
            for result in retriever.retrieve(question, top_k=top_k) or []:
                results.append(ScopedRetrievalResult(knowledge_base_slug=slug, result=result))
        return results
