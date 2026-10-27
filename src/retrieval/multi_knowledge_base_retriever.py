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
        retrievers = list(self._retrievers.values())
        shared_rewriter = getattr(retrievers[0], "query_rewriter", None) if retrievers else None
        shares_rewriter = shared_rewriter is not None and all(
            getattr(retriever, "query_rewriter", None) is shared_rewriter
            and callable(getattr(retriever, "prepare_query", None))
            and callable(getattr(retriever, "retrieve_prepared", None))
            for retriever in retrievers
        )
        prepared_query = retrievers[0].prepare_query(question) if shares_rewriter else None
        for slug, retriever in self._retrievers.items():
            if shares_rewriter:
                retrieved = retriever.retrieve_prepared(question, prepared_query, top_k=top_k)
            else:
                retrieved = retriever.retrieve(question, top_k=top_k)
            for result in retrieved or []:
                results.append(ScopedRetrievalResult(knowledge_base_slug=slug, result=result))
        return results
