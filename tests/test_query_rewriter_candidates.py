"""多候选法律查询改写的行为测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.retrieval import query_rewriter
from src.retrieval.query_rewriter import QueryRewriter


class FakeResponse:
    content = """{
      "rewritten_queries": [
        "劳动关系认定标准",
        "劳动关系认定标准",
        "确认劳动关系的从属性要件",
        "劳动争议中劳动关系举证",
        "超出上限的候选"
      ],
      "search_keywords": ["劳动关系", "从属性"]
    }"""


class FakeLLM:
    def invoke(self, _prompt):
        return FakeResponse()


def test_rewrite_candidates_deduplicates_and_keeps_at_most_three_queries():
    """改写输出去重后最多保留三条，原问题始终作为首个检索查询。"""
    rewriter = QueryRewriter.__new__(QueryRewriter)
    rewriter.llm = FakeLLM()

    rewritten = rewriter.rewrite_candidates("我和公司算不算劳动关系")

    assert rewritten.search_queries == [
        "我和公司算不算劳动关系",
        "劳动关系认定标准",
        "确认劳动关系的从属性要件",
        "劳动争议中劳动关系举证",
    ]
    assert rewritten.search_keywords == ["劳动关系", "从属性"]


def test_query_rewriter_forwards_explicit_operation_budget(monkeypatch):
    observed = {}

    def fake_create_llm(**kwargs):
        observed.update(kwargs)
        return object()

    monkeypatch.setattr(query_rewriter, "create_llm", fake_create_llm)

    QueryRewriter(
        api_key="test-key",
        base_url="https://api.example.test/v1",
        model="test-model",
        request_timeout=15,
        max_retries=0,
    )

    assert observed["request_timeout"] == 15
    assert observed["max_retries"] == 0
