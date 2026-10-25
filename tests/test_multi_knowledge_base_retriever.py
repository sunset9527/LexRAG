from types import SimpleNamespace

from src.retrieval.multi_knowledge_base_retriever import MultiKnowledgeBaseLawRetriever


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
