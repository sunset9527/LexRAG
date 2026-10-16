"""八库检索评测运行器的路线与分库路由测试。"""

from types import SimpleNamespace

from src.evaluation.multikb_retrieval import collect_ranked_article_ids


class _FakeRetriever:
    def __init__(self):
        self.vector_queries: list[tuple[str, int]] = []
        self.optimized_queries: list[tuple[str, int, str | None]] = []
        self._bm25 = None

    def retrieve(self, query: str, *, top_k: int):
        self.vector_queries.append((query, top_k))
        return [SimpleNamespace(article_id="vector-1"), SimpleNamespace(article_id="vector-2")]

    def _ensure_optimization_data(self):
        self._bm25 = SimpleNamespace(
            retrieve=lambda query, top_k: [
                SimpleNamespace(metadata={"article_id": "bm25-1"}),
                SimpleNamespace(metadata={"article_id": "bm25-2"}),
            ]
        )

    def retrieve_optimized(self, query: str, *, top_k: int, law_name: str | None = None):
        self.optimized_queries.append((query, top_k, law_name))
        return [SimpleNamespace(article_id="rrf-1"), SimpleNamespace(article_id="rrf-2")], "", []


def test_collect_ranked_article_ids_uses_requested_route():
    """向量、BM25、RRF 都必须返回其自身的条文排序。"""
    retriever = _FakeRetriever()

    assert collect_ranked_article_ids(retriever, "问题", mode="vector", top_k=2) == [
        "vector-1",
        "vector-2",
    ]
    assert collect_ranked_article_ids(retriever, "问题", mode="bm25", top_k=2) == [
        "bm25-1",
        "bm25-2",
    ]
    assert collect_ranked_article_ids(
        retriever,
        "问题",
        mode="rrf",
        top_k=2,
        law_name="中华人民共和国刑法",
    ) == [
        "rrf-1",
        "rrf-2",
    ]
    assert retriever.vector_queries == [("问题", 2)]
    assert retriever.optimized_queries == [("问题", 2, "中华人民共和国刑法")]


def test_collect_ranked_article_ids_deduplicates_bm25_article_chunks():
    """BM25 可能命中同一法条的多个分块，评测候选必须按条文去重。"""
    retriever = _FakeRetriever()
    retriever._ensure_optimization_data = lambda: setattr(
        retriever,
        "_bm25",
        SimpleNamespace(
            retrieve=lambda _query, top_k: [
                SimpleNamespace(metadata={"article_id": "bm25-1"}),
                SimpleNamespace(metadata={"article_id": "bm25-1"}),
                SimpleNamespace(metadata={"article_id": "bm25-2"}),
            ][:top_k]
        ),
    )

    assert collect_ranked_article_ids(retriever, "问题", mode="bm25", top_k=3) == [
        "bm25-1",
        "bm25-2",
    ]
