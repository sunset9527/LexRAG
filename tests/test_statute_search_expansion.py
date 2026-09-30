"""Agent 法条检索工具接入多候选与 HyDE 的契约测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.agent import tools
from src.retrieval.law_retriever import RetrievalResult
from src.retrieval.query_rewriter import RewrittenQuery


class FakeRewriter:
    def rewrite_candidates(self, query):
        assert query == "员工是否与公司存在劳动关系"
        return RewrittenQuery(
            original_query=query,
            rewritten_query="劳动关系认定标准",
            search_keywords=["劳动关系"],
            search_queries=[query, "劳动关系认定标准"],
        )

    def generate_hyde(self, query):
        assert query == "员工是否与公司存在劳动关系"
        return "劳动关系的从属性与报酬支付"


class FakeLawRetriever:
    def __init__(self):
        self.calls = []

    def retrieve_multi_query(self, queries, *, hyde_query, top_k):
        self.calls.append((queries, hyde_query, top_k))
        return [
            RetrievalResult(
                chunk_id="article-1",
                article_id="劳动合同法第7条",
                article_number="7",
                law_name="劳动合同法",
                content="用人单位自用工之日起即与劳动者建立劳动关系。",
                full_content="用人单位自用工之日起即与劳动者建立劳动关系。",
                chapter="第一章",
                section="",
                score=1.0,
                metadata={},
            )
        ]


def test_search_statute_uses_multi_query_and_hyde_when_rewriter_is_available():
    """工具层必须调用多路检索，而非只计算改写文本后继续检索原问题。"""
    retriever = FakeLawRetriever()
    tools._retriever_registry.clear()
    tools._retriever_registry.update(
        {
            "law_retriever": retriever,
            "bm25_retriever": None,
            "reranker": None,
            "query_rewriter": FakeRewriter(),
        }
    )

    result = tools.search_statute.invoke({"query": "员工是否与公司存在劳动关系"})

    assert retriever.calls == [
        (
            ["员工是否与公司存在劳动关系", "劳动关系认定标准"],
            "劳动关系的从属性与报酬支付",
            10,
        )
    ]
    assert "劳动合同法第7条" in result
