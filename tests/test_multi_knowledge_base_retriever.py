from types import SimpleNamespace

from src.retrieval.multi_knowledge_base_retriever import MultiKnowledgeBaseLawRetriever
from src.workflow.legal_evidence_workflow import QueryEnhancedLawRetriever


def test_retrieves_each_selected_knowledge_base_and_preserves_its_scope():
    class Retriever:
        def __init__(self, value):
            self.value = value

        def retrieve(self, question, *, top_k):
            assert question == "公司违反劳动合同怎么办？"
            assert top_k == 5
            return [SimpleNamespace(article_id=self.value)]

    result = MultiKnowledgeBaseLawRetriever(
        {
            "company-law": Retriever("company-1"),
            "labor-contract-law": Retriever("labor-contract-1"),
        }
    ).retrieve("公司违反劳动合同怎么办？", top_k=5)

    assert [(item.knowledge_base_slug, item.result.article_id) for item in result] == [
        ("company-law", "company-1"),
        ("labor-contract-law", "labor-contract-1"),
    ]


def test_multi_knowledge_base_reuses_one_rewrite_and_hyde_per_request():
    class Rewriter:
        def __init__(self):
            self.rewrite_calls = 0
            self.hyde_calls = 0

        def rewrite_candidates(self, question):
            self.rewrite_calls += 1
            return SimpleNamespace(search_queries=[question, "劳动合同解除条件"])

        def generate_hyde(self, _question):
            self.hyde_calls += 1
            return "假设性法律回答"

    class Retriever:
        def __init__(self):
            self.calls = []

        def retrieve_multi_query(self, search_queries, *, hyde_query, top_k):
            self.calls.append((search_queries, hyde_query, top_k))
            return []

    rewriter = Rewriter()
    first = Retriever()
    second = Retriever()
    MultiKnowledgeBaseLawRetriever(
        {
            "civil-code": QueryEnhancedLawRetriever(first, rewriter, enable_hyde=True),
            "labor-contract-law": QueryEnhancedLawRetriever(second, rewriter, enable_hyde=True),
        }
    ).retrieve("公司解除劳动合同合法吗？", top_k=5)

    assert rewriter.rewrite_calls == 1
    assert rewriter.hyde_calls == 1
    assert (
        first.calls
        == second.calls
        == [(["公司解除劳动合同合法吗？", "劳动合同解除条件"], "假设性法律回答", 5)]
    )
