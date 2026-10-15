"""年度案例独立向量索引测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ingestion.annual_case_indexer import AnnualCaseIndexer


class VectorStore:
    def __init__(self):
        self.documents = None
        self.ids = None

    def add_documents(self, documents, ids):
        self.documents = documents
        self.ids = ids


def test_index_cases_writes_independent_case_ids_and_retrieval_metadata():
    """案例向量只写入独立 collection 所需的字段，不混入法条文档 ID。"""
    store = VectorStore()
    indexer = AnnualCaseIndexer(vectorstore=store)

    count = indexer.upsert_cases(
        [
            {
                "id": "case-1",
                "source_id": 8,
                "domain": "labor",
                "case_cause": "确认劳动关系纠纷",
                "title": "某甲诉某公司劳动争议案",
                "issues": "是否存在劳动关系",
                "court_reasoning": "从属性审查",
                "judgment_result": "驳回诉讼请求",
                "source_start_page": 14,
                "source_end_page": 16,
            }
        ]
    )

    assert count == 1
    assert store.ids == ["case:case-1"]
    assert store.documents[0].metadata == {
        "case_id": "case-1",
        "source_id": 8,
        "domain": "labor",
        "case_cause": "确认劳动关系纠纷",
        "source_start_page": 14,
        "source_end_page": 16,
    }
    assert "从属性审查" in store.documents[0].page_content
