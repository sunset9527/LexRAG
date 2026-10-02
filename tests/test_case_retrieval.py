"""案例语义检索与案由加分测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.retrieval.annual_case_retriever import AnnualCaseRetriever


class Document:
    def __init__(self, case_id, case_cause):
        self.page_content = "案件焦点与裁判理由"
        self.metadata = {"case_id": case_id, "case_cause": case_cause}


class VectorStore:
    def similarity_search_with_score(self, _query, k, filter=None):
        assert k == 12
        assert filter is None
        return [
            (Document("case-1", "确认劳动关系纠纷"), 0.01),
            (Document("case-2", "确认劳动关系纠纷"), 0.10),
            (Document("case-3", "劳动报酬纠纷"), 0.05),
        ]


def test_similar_cases_excludes_self_and_boosts_same_cause():
    """相似案例不可返回自身；案由一致的候选在相同语义量级下应优先。"""
    retriever = AnnualCaseRetriever(
        VectorStore(),
        case_loader=lambda case_id: {
            "case-1": {"id": "case-1", "case_cause": "确认劳动关系纠纷", "issues": "是否存在劳动关系", "court_reasoning": "从属性"},
            "case-2": {"id": "case-2", "title": "案例二", "case_cause": "确认劳动关系纠纷"},
            "case-3": {"id": "case-3", "title": "案例三", "case_cause": "劳动报酬纠纷"},
        }[case_id],
    )

    results = retriever.similar_cases("case-1", top_k=3)

    assert [item["id"] for item in results] == ["case-2", "case-3"]
    assert results[0]["case_cause_match"] is True
    assert results[0]["similarity_score"] > results[1]["similarity_score"]


def test_search_returns_traceable_case_evidence_for_free_text_query():
    retriever = AnnualCaseRetriever(
        VectorStore(),
        case_loader=lambda case_id: {
            "case-1": {"id": "case-1", "title": "案例一", "case_cause": "确认劳动关系纠纷", "issues": "劳动关系", "court_reasoning": "从属性", "source_start_page": 12, "source_end_page": 15},
            "case-2": {"id": "case-2", "title": "案例二", "case_cause": "确认劳动关系纠纷", "issues": "劳动关系", "court_reasoning": "从属性", "source_start_page": 20, "source_end_page": 24},
            "case-3": {"id": "case-3", "title": "案例三", "case_cause": "劳动报酬纠纷", "issues": "加班费", "court_reasoning": "工资", "source_start_page": 30, "source_end_page": 32},
        }[case_id],
    )

    results = retriever.search("劳动关系争议", top_k=3)

    assert results[0]["case_id"] == "case-1"
    assert results[0]["source_pages"] == "12-15"
