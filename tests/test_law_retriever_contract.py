"""LawRetriever 的 Chroma 边界与降级行为测试。"""

from types import SimpleNamespace

from src.retrieval.law_retriever import LawRetriever


def test_retrieve_filters_before_deduplicating_article_chunks():
    """同一法条多 chunk 只能返回一次，且法规过滤必须原样传给向量库。"""

    class FakeVectorStore:
        def __init__(self):
            self.calls = []

        def similarity_search_with_score(self, query, *, k, filter):
            self.calls.append((query, k, filter))
            return [
                (
                    SimpleNamespace(
                        page_content="第十七条原文",
                        metadata={
                            "chunk_id": "17-a",
                            "article_id": "民法典第17条",
                            "article_number": "17",
                            "law_name": "中华人民共和国民法典",
                        },
                    ),
                    0.1,
                ),
                (
                    SimpleNamespace(
                        page_content="第十七条补充",
                        metadata={
                            "chunk_id": "17-b",
                            "article_id": "民法典第17条",
                            "article_number": "17",
                            "law_name": "中华人民共和国民法典",
                        },
                    ),
                    0.2,
                ),
                (
                    SimpleNamespace(
                        page_content="第十八条原文",
                        metadata={
                            "chunk_id": "18-a",
                            "article_id": "民法典第18条",
                            "article_number": "18",
                            "law_name": "中华人民共和国民法典",
                        },
                    ),
                    0.3,
                ),
            ]

    store = FakeVectorStore()
    retriever = LawRetriever.__new__(LawRetriever)
    retriever.vectorstore = store

    results = retriever.retrieve("成年人的年龄规定", top_k=2, law_name="中华人民共和国民法典")

    assert store.calls == [
        ("成年人的年龄规定", 4, {"law_name": "中华人民共和国民法典"})
    ]
    assert [item.article_id for item in results] == ["民法典第17条", "民法典第18条"]
    assert results[0].content == "第十七条原文"


def test_retrieve_returns_empty_result_when_vector_store_fails():
    """向量库异常不能中断法律工作流，检索器必须按契约降级为空证据。"""

    class FailingVectorStore:
        def similarity_search_with_score(self, *_args, **_kwargs):
            raise RuntimeError("chroma unavailable")

    retriever = LawRetriever.__new__(LawRetriever)
    retriever.vectorstore = FailingVectorStore()

    assert retriever.retrieve("年龄规定") == []
