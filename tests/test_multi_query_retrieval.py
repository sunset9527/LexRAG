"""原问题、改写候选与 HyDE 的多路 RRF 融合测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.retrieval.law_retriever import LawRetriever, RetrievalResult


def _result(article_id: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=article_id,
        article_id=article_id,
        article_number=article_id.removeprefix("article-"),
        law_name="测试法",
        content=article_id,
        full_content=article_id,
        chapter="第一章",
        section="",
        score=0.5,
        metadata={},
    )


def test_multi_query_retrieval_fuses_original_candidates_and_hyde():
    """三路检索以 RRF 融合、按法条去重，并保留来源查询。"""
    retriever = LawRetriever.__new__(LawRetriever)
    calls: list[str] = []
    responses = {
        "原问题": [_result("article-a"), _result("article-b")],
        "候选问题": [_result("article-b"), _result("article-c")],
        "HyDE 假设答案": [_result("article-b"), _result("article-d")],
    }

    def fake_retrieve(query, *, top_k, **_kwargs):
        calls.append(query)
        return responses[query][:top_k]

    retriever.retrieve = fake_retrieve

    results = retriever.retrieve_multi_query(
        ["原问题", "候选问题"],
        hyde_query="HyDE 假设答案",
        top_k=3,
    )

    assert calls == ["原问题", "候选问题", "HyDE 假设答案"]
    assert [item.article_id for item in results] == ["article-b", "article-a", "article-c"]
    assert results[0].metadata["retrieval_queries"] == ["原问题", "候选问题", "HyDE 假设答案"]
