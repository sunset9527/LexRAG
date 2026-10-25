"""阶段 5：知识库路由的纯规则契约。"""

from src.retrieval.knowledge_base_router import KnowledgeBaseRouter


def _libraries(*slugs: str) -> list[dict[str, str]]:
    names = {
        "civil-code": "中华人民共和国民法典",
        "criminal-law": "中华人民共和国刑法",
        "labor-law": "中华人民共和国劳动法",
        "labor-contract-law": "中华人民共和国劳动合同法",
        "company-law": "中华人民共和国公司法",
        "patent-law": "中华人民共和国专利法",
        "trademark-law": "中华人民共和国商标法",
        "copyright-law": "中华人民共和国著作权法",
    }
    return [
        {"slug": slug, "name": names[slug], "law_area": slug.removesuffix("-law")}
        for slug in slugs
    ]


def test_explicit_knowledge_base_selection_always_wins_over_automatic_routing():
    decision = KnowledgeBaseRouter().route(
        "劳动合同到期后公司不续签，需要赔偿吗？",
        _libraries("civil-code", "labor-law", "labor-contract-law"),
        explicit_slugs=["civil-code"],
    )

    assert decision.mode == "explicit"
    assert decision.selected_slugs == ["civil-code"]
    assert decision.candidates[0].reason_code == "explicit_selection"


def test_automatic_routing_selects_labor_law_and_labor_contract_law_for_labor_contract_dispute():
    decision = KnowledgeBaseRouter().route(
        "用人单位违法解除劳动合同，应当如何支付经济补偿？",
        _libraries("civil-code", "labor-law", "labor-contract-law", "company-law"),
    )

    assert decision.mode == "automatic"
    assert decision.selected_slugs == ["labor-contract-law", "labor-law"]
    assert all(item.confidence >= 0.7 for item in decision.candidates)


def test_automatic_routing_selects_company_law_and_civil_code_for_company_contract_dispute():
    decision = KnowledgeBaseRouter().route(
        "公司签订买卖合同后违约，股东需要承担责任吗？",
        _libraries("civil-code", "labor-law", "labor-contract-law", "company-law"),
    )

    assert decision.mode == "automatic"
    assert decision.selected_slugs == ["company-law", "civil-code"]


def test_unknown_question_requires_clarification_instead_of_silently_guessing_a_library():
    decision = KnowledgeBaseRouter().route(
        "我遇到一点麻烦，怎么办？",
        _libraries("civil-code", "criminal-law", "labor-law"),
    )

    assert decision.mode == "clarification"
    assert decision.selected_slugs == []
    assert decision.requires_clarification is True
    assert [item.slug for item in decision.candidates] == [
        "civil-code",
        "criminal-law",
        "labor-law",
    ]
    assert all(item.reason_code == "clarification_required" for item in decision.candidates)
