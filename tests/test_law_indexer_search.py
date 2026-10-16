"""LawIndexer 对新版 Chroma 检索接口的契约测试。"""

from types import SimpleNamespace

from src.ingestion.indexer import LawIndexer


def test_search_uses_relevance_score_api_and_preserves_rank_filter_and_score():
    """索引器必须调用新版 API，并向上层交付可排序的真实相关度分数。"""

    class FakeVectorStore:
        def __init__(self):
            self.calls = []

        def similarity_search_with_relevance_scores(self, query, *, k, filter):
            self.calls.append((query, k, filter))
            return [
                (SimpleNamespace(page_content="第十七条", metadata={"article_number": "17"}), 0.91),
                (SimpleNamespace(page_content="第十八条", metadata={"article_number": "18"}), 0.73),
            ]

    store = FakeVectorStore()
    indexer = LawIndexer.__new__(LawIndexer)
    indexer.vectorstore = store

    result = indexer.search(
        "成年人的年龄规定",
        top_k=2,
        filter_metadata={"law_name": "中华人民共和国民法典"},
    )

    assert store.calls == [
        ("成年人的年龄规定", 2, {"law_name": "中华人民共和国民法典"})
    ]
    assert result == [
        {
            "rank": 1,
            "content": "第十七条",
            "metadata": {"article_number": "17"},
            "score": 0.91,
        },
        {
            "rank": 2,
            "content": "第十八条",
            "metadata": {"article_number": "18"},
            "score": 0.73,
        },
    ]


def test_search_can_omit_scores_for_legacy_callers():
    """调用方显式关闭分数时，返回结构仍保留排名、原文和元数据。"""

    class FakeVectorStore:
        def similarity_search_with_relevance_scores(self, _query, *, k, filter):
            assert k == 1
            assert filter is None
            return [(SimpleNamespace(page_content="第十七条", metadata={}), 0.91)]

    indexer = LawIndexer.__new__(LawIndexer)
    indexer.vectorstore = FakeVectorStore()

    assert indexer.search("年龄", top_k=1, include_relevance_score=False) == [
        {"rank": 1, "content": "第十七条", "metadata": {}}
    ]
