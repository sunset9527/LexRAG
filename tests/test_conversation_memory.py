"""会话历史只能辅助理解，不能成为可引用证据。"""

from types import SimpleNamespace

import api
from app.services.session_service import ConversationTurn
from src.workflow.evidence import CitationVerifier, EvidenceItem, EvidenceLedger


class FakeLLM:
    def __init__(self):
        self.prompt = ""

    def invoke(self, prompt):
        self.prompt = prompt
        return SimpleNamespace(
            content="依据【中华人民共和国民法典第17条】，年满十八周岁的自然人为成年人。"
        )


def statute() -> EvidenceItem:
    return EvidenceItem(
        source_id="civil-17",
        source_type="statute",
        knowledge_base_slug="civil-code",
        law_name="中华人民共和国民法典",
        article_id="17",
        content="十八周岁以上的自然人为成年人。",
        score=0.9,
        retrieval_path="statute",
    )


def test_memory_is_marked_as_non_evidence_and_only_verified_citations_are_rendered():
    llm = FakeLLM()
    generator = api.build_evidence_answer_generator(
        llm,
        memory_turns=[
            ConversationTurn(
                question="上次的劳动问题",
                answer="此前回答",
                verified_citations=["中华人民共和国劳动合同法第47条"],
            )
        ],
    )

    generator("成年人多大？", [statute()])

    assert "历史上下文（仅帮助理解，不构成本轮证据）" in llm.prompt
    assert "中华人民共和国劳动合同法第47条" in llm.prompt
    assert "新法律结论和引用只能来自本轮检索证据" in llm.prompt


def test_historical_citation_is_rejected_when_missing_from_current_ledger():
    verification = CitationVerifier().verify(
        "依据【中华人民共和国劳动合同法第47条】，可以主张补偿。",
        EvidenceLedger([statute()]),
        knowledge_base_slug="civil-code",
    )

    assert verification.status == "fail"
