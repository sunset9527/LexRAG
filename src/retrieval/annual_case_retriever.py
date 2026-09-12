"""年度案例库的语义检索与相似案例排序。"""

from collections.abc import Callable
from typing import Any


class AnnualCaseRetriever:
    """基于独立案例向量库检索，并对案由一致的候选做透明加分。"""

    cause_boost = 0.2

    def __init__(self, vectorstore: Any, *, case_loader: Callable[[str], dict[str, Any]]):
        self._vectorstore = vectorstore
        self._case_loader = case_loader

    def similar_cases(self, case_id: str, *, top_k: int = 5) -> list[dict[str, Any]]:
        source = self._case_loader(case_id)
        query = "\n".join(
            value for value in (source.get("case_cause"), source.get("issues"), source.get("court_reasoning")) if value
        )
        candidates = self._vectorstore.similarity_search_with_score(query, k=top_k * 4, filter=None)
        results = []
        for document, distance in candidates:
            metadata = document.metadata
            candidate_id = metadata.get("case_id")
            if not candidate_id or candidate_id == case_id:
                continue
            candidate = self._case_loader(candidate_id)
            cause_match = candidate.get("case_cause") == source.get("case_cause")
            semantic_score = 1 / (1 + float(distance))
            results.append(
                {
                    **candidate,
                    "similarity_score": round(semantic_score + (self.cause_boost if cause_match else 0), 4),
                    "case_cause_match": cause_match,
                }
            )
        results.sort(key=lambda item: item["similarity_score"], reverse=True)
        return results[:top_k]
