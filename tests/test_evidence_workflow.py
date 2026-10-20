"""证据驱动法律工作流与 LangGraph 主链契约。"""

import asyncio
import json

from langgraph.graph.state import CompiledStateGraph

from src.workflow import legal_evidence_workflow as workflow_module
from src.workflow.evidence import CitationVerifier, EvidenceItem, EvidenceLedger
from src.workflow.legal_evidence_workflow import (
    LegalEvidenceWorkflow,
    QueryEnhancedLawRetriever,
    RouteDecision,
)


def statute(
    *,
    source_id: str = "civil-1254",
    knowledge_base_slug: str = "civil-code",
    law_name: str = "中华人民共和国民法典",
    article_id: str = "1254",
    score: float = 0.6,
    retrieval_path: str = "statute",
) -> EvidenceItem:
    return EvidenceItem(
        source_id=source_id,
        source_type="statute",
        knowledge_base_slug=knowledge_base_slug,
        law_name=law_name,
        article_id=article_id,
        content="禁止从建筑物中抛掷物品。",
        score=score,
        retrieval_path=retrieval_path,
    )


def test_ledger_merges_same_source_and_keeps_best_score_and_paths():
    ledger = EvidenceLedger()

    assert ledger.add(statute(score=0.4, retrieval_path="vector"))
    assert ledger.add(statute(score=0.9, retrieval_path="graph"))

    assert len(ledger.items) == 1
    item = ledger.items[0]
    assert item.score == 0.9
    assert item.retrieval_paths == {"vector", "graph"}


def test_ledger_does_not_merge_same_source_id_across_knowledge_bases():
    ledger = EvidenceLedger()

    assert ledger.add(statute(knowledge_base_slug="civil-code"))
    assert ledger.add(statute(knowledge_base_slug="company-law"))

    assert len(ledger.items) == 2


def test_ledger_rejects_statute_without_law_identity():
    ledger = EvidenceLedger()
    missing_law_name = statute(law_name="")
    missing_article_id = statute(article_id="")

    assert not ledger.add(missing_law_name)
    assert not ledger.add(missing_article_id)
    assert ledger.items == []
    assert ledger.rejected_count == 2


def test_citation_verifier_accepts_only_citation_present_in_current_ledger():
    ledger = EvidenceLedger([statute()])

    result = CitationVerifier().verify(
        "依据【中华人民共和国民法典第1254条】，应当依法调查责任主体。",
        ledger,
        knowledge_base_slug="civil-code",
    )

    assert result.status == "pass"
    assert result.issues == []
    assert result.citations[0].is_verified is True


def test_citation_verifier_returns_source_text_and_deduplicates_repeated_citations():
    """溯源面板必须取得已校验证据的原文，且同一法条只显示一次。"""
    ledger = EvidenceLedger([statute()])

    result = CitationVerifier().verify(
        "依据【中华人民共和国民法典第1254条】处理。再次参照【中华人民共和国民法典第1254条】。",
        ledger,
        knowledge_base_slug="civil-code",
    )

    assert result.status == "pass"
    assert len(result.citations) == 1
    assert result.citations[0].original_text == "禁止从建筑物中抛掷物品。"


def test_citation_verifier_rejects_fabricated_article_wrong_law_and_missing_citation():
    ledger = EvidenceLedger([statute()])
    verifier = CitationVerifier()

    fabricated = verifier.verify(
        "依据【中华人民共和国民法典第9999条】，可以直接要求赔偿。",
        ledger,
        knowledge_base_slug="civil-code",
    )
    wrong_law = verifier.verify(
        "依据【中华人民共和国公司法第1254条】，可以直接要求赔偿。",
        ledger,
        knowledge_base_slug="civil-code",
    )
    missing = verifier.verify(
        "可以直接要求赔偿。",
        ledger,
        knowledge_base_slug="civil-code",
    )

    assert fabricated.status == "fail"
    assert "不在本次证据账本中" in fabricated.issues[0]
    assert wrong_law.status == "fail"
    assert "法律名称不匹配" in wrong_law.issues[0]
    assert missing.status == "fail"
    assert missing.issues == ["回答中未包含可校验的法条引用"]


class FakeLawRetriever:
    def __init__(self, results=None):
        self.results = results or [statute()]
        self.calls = 0

    def retrieve(self, query, top_k=5):
        self.calls += 1
        return self.results


def test_workflow_exports_one_shared_compiled_langgraph_with_explicit_nodes():
    graph = getattr(workflow_module, "COMPILED_LEGAL_EVIDENCE_GRAPH", None)

    assert isinstance(graph, CompiledStateGraph)
    assert {
        "planning",
        "routing",
        "statute_retrieval",
        "case_retrieval",
        "graph_retrieval",
        "evidence_ledger",
        "answer",
        "citation_verifier",
        "repair",
        "finalize",
        "evidence_insufficient",
    }.issubset(graph.get_graph().nodes)

    first = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        answer_generator=lambda question, evidence, issues=None: "",
    )
    second = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        answer_generator=lambda question, evidence, issues=None: "",
    )

    assert first.graph is graph
    assert second.graph is graph


def test_simple_question_skips_planning_and_returns_verified_workflow_result():
    planner_calls = []

    workflow = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        planner=lambda question: planner_calls.append(question),
        answer_generator=lambda question, evidence, issues=None: (
            "依据【中华人民共和国民法典第1254条】，应当依法调查责任主体。"
        ),
    )

    result = workflow.query("第1254条规定什么？", knowledge_base_slug="civil-code")

    assert planner_calls == []
    assert result.verification_status == "pass"
    assert result.metadata["evidence_count"] == 1
    assert result.metadata["orchestration_engine"] == "langgraph-stategraph"
    assert [event["node"] for event in result.metadata["workflow_trace"]] == [
        "planning",
        "routing",
        "statute_retrieval",
        "evidence_ledger",
        "answer",
        "citation_verifier",
        "finalize",
    ]


def test_complex_question_uses_normalized_planner_output():
    planned = [
        {"question": "劳动合同解除是否合法？", "depends_on": ""},
        {"question": "可以主张哪些补偿？", "depends_on": "劳动合同解除是否合法？"},
    ]
    planner_calls = []
    workflow = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        planner=lambda question: planner_calls.append(question) or planned,
        answer_generator=lambda question, evidence, issues=None: (
            "依据【中华人民共和国民法典第1254条】，应当依法调查责任主体。"
        ),
    )

    result = workflow.query(
        "公司解除劳动合同是否合法，并且劳动者可以主张哪些补偿？",
        knowledge_base_slug="civil-code",
    )

    assert planner_calls == ["公司解除劳动合同是否合法，并且劳动者可以主张哪些补偿？"]
    assert result.sub_questions == planned
    planning_event = result.metadata["workflow_trace"][0]
    assert planning_event["node"] == "planning"
    assert planning_event["status"] == "completed"
    assert planning_event["output_count"] == 2


def test_planner_failure_uses_original_question_and_records_only_exception_type():
    private_question = "合同解除是否合法，并且如何赔偿？PRIVATE-QUESTION"

    def failing_planner(question):
        raise RuntimeError("PRIVATE-PLANNER-ERROR")

    workflow = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        planner=failing_planner,
        answer_generator=lambda question, evidence, issues=None: (
            "依据【中华人民共和国民法典第1254条】，应当依法调查责任主体。"
        ),
    )

    result = workflow.query(private_question, knowledge_base_slug="civil-code")

    assert result.sub_questions == [{"question": private_question, "depends_on": ""}]
    assert result.metadata["workflow_status"] == "degraded"
    assert result.metadata["degradation_reasons"] == [
        {"node": "planning", "reason": "RuntimeError"}
    ]
    serialized_trace = json.dumps(result.metadata["workflow_trace"], ensure_ascii=False)
    assert private_question not in serialized_trace
    assert "PRIVATE-PLANNER-ERROR" not in serialized_trace


def test_routing_and_optional_retrieval_failures_degrade_to_statute_evidence_without_leaking_query():
    class FailingCaseRetriever:
        def retrieve(self, query, top_k=3):
            raise RuntimeError("case backend unavailable")

    class FailingGraphRetriever:
        def retrieve(self, article_id, max_hops=1):
            raise RuntimeError("graph backend unavailable")

    workflow = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        router=lambda question: (_ for _ in ()).throw(RuntimeError("router unavailable")),
        case_retriever=FailingCaseRetriever(),
        graph_retriever=FailingGraphRetriever(),
        answer_generator=lambda question, evidence, issues=None: (
            "依据【中华人民共和国民法典第1254条】，应当依法调查责任主体。"
        ),
    )

    result = workflow.query("我的私人案情 SECRET-DO-NOT-LEAK", knowledge_base_slug="civil-code")

    assert result.verification_status == "pass"
    assert result.metadata["workflow_status"] == "degraded"
    assert "SECRET-DO-NOT-LEAK" not in str(result.metadata["workflow_trace"])
    assert any(
        event["node"] == "routing" and event["status"] == "degraded"
        for event in result.metadata["workflow_trace"]
    )


def test_failed_answer_is_repaired_once_using_same_evidence_then_verified():
    calls = []

    def answer_generator(question, evidence, issues=None):
        calls.append(issues)
        if issues is None:
            return "依据【中华人民共和国民法典第9999条】，可以要求赔偿。"
        return "依据【中华人民共和国民法典第1254条】，应当依法调查责任主体。"

    workflow = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        answer_generator=answer_generator,
    )

    result = workflow.query("高空抛物致人损害怎么办？", knowledge_base_slug="civil-code")

    assert result.verification_status == "pass"
    assert result.metadata["verification_attempts"] == 1
    assert len(calls) == 2
    assert any(event["node"] == "repair" for event in result.metadata["workflow_trace"])


def test_second_failed_answer_returns_evidence_insufficient_response_and_is_not_verified():
    workflow = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        answer_generator=lambda question, evidence, issues=None: (
            "依据【中华人民共和国民法典第9999条】，可以要求赔偿。"
        ),
    )

    result = workflow.query("高空抛物致人损害怎么办？", knowledge_base_slug="civil-code")

    assert result.verification_status == "fail"
    assert result.metadata["verification_attempts"] == 1
    assert result.metadata["cacheable"] is False
    assert "现有证据不足以支持可靠结论" in result.answer


def test_empty_statute_retrieval_stops_before_answer_and_is_not_cacheable():
    answer_calls = []

    class EmptyLawRetriever:
        def retrieve(self, query, top_k=5):
            return []

    workflow = LegalEvidenceWorkflow(
        law_retriever=EmptyLawRetriever(),
        answer_generator=lambda question, evidence, issues=None: answer_calls.append(
            (question, evidence, issues)
        ),
    )

    result = workflow.query("没有匹配法条的问题", knowledge_base_slug="civil-code")

    assert answer_calls == []
    assert result.verification_status == "fail"
    assert result.verification_issues == ["本次检索未获得可引用的法条证据"]
    assert result.metadata["cacheable"] is False
    assert result.metadata["workflow_trace"][-1]["node"] == "evidence_insufficient"


def test_failed_statute_retrieval_is_safely_degraded_and_not_cacheable():
    answer_calls = []

    class FailingLawRetriever:
        def retrieve(self, query, top_k=5):
            raise RuntimeError("PRIVATE-RETRIEVER-ERROR")

    workflow = LegalEvidenceWorkflow(
        law_retriever=FailingLawRetriever(),
        answer_generator=lambda question, evidence, issues=None: answer_calls.append(
            (question, evidence, issues)
        ),
    )

    result = workflow.query("检索失败的问题", knowledge_base_slug="civil-code")

    assert answer_calls == []
    assert result.verification_status == "fail"
    assert result.metadata["cacheable"] is False
    assert result.metadata["workflow_status"] == "degraded"
    assert {"node": "statute_retrieval", "reason": "RuntimeError"} in result.metadata[
        "degradation_reasons"
    ]
    serialized_metadata = json.dumps(result.metadata, ensure_ascii=False)
    assert "PRIVATE-RETRIEVER-ERROR" not in serialized_metadata


def test_conversation_context_never_enters_evidence_or_result_metadata():
    private_history = "PRIVATE-HISTORY-CONTENT"
    evidence_seen_by_answer = []

    def answer_generator(question, evidence, issues=None):
        evidence_seen_by_answer.extend(evidence)
        return "依据【中华人民共和国民法典第1254条】，应当依法调查责任主体。"

    workflow = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        answer_generator=answer_generator,
    )

    result = workflow.query(
        "第1254条规定什么？",
        knowledge_base_slug="civil-code",
        conversation_context=[{"role": "user", "content": private_history}],
    )

    assert [item.source_id for item in evidence_seen_by_answer] == ["civil-1254"]
    assert private_history not in json.dumps(result.metadata, ensure_ascii=False)
    assert all(private_history not in item.content for item in evidence_seen_by_answer)


def test_query_enhanced_retriever_preserves_v2_multi_query_and_hyde_retrieval():
    class Rewriter:
        def rewrite_candidates(self, question):
            return type("Rewrite", (), {"search_queries": [question, "法律术语"]})()

        def generate_hyde(self, question):
            return "仅用于召回的假设文本"

    class BaseRetriever:
        def __init__(self):
            self.calls = []

        def retrieve_multi_query(self, search_queries, hyde_query, top_k):
            self.calls.append((search_queries, hyde_query, top_k))
            return [statute()]

    base = BaseRetriever()
    wrapper = QueryEnhancedLawRetriever(base, Rewriter())

    results = wrapper.retrieve("高空抛物怎么办", top_k=5)

    assert results[0].article_id == "1254"
    assert base.calls == [(["高空抛物怎么办", "法律术语"], "仅用于召回的假设文本", 5)]


def test_query_enhanced_retriever_falls_back_to_original_question_when_expansion_errors():
    class FailingRewriter:
        def rewrite_candidates(self, question):
            raise RuntimeError("LLM unavailable")

    class BaseRetriever:
        def __init__(self):
            self.queries = []

        def retrieve(self, query, top_k):
            self.queries.append((query, top_k))
            return [statute()]

    base = BaseRetriever()
    wrapper = QueryEnhancedLawRetriever(base, FailingRewriter())

    wrapper.retrieve("高空抛物怎么办", top_k=5)

    assert base.queries == [("高空抛物怎么办", 5)]


def test_case_and_graph_results_are_recorded_in_evidence_ledger_when_routed():
    case_evidence = EvidenceItem(
        source_id="case-1",
        source_type="case",
        knowledge_base_slug="annual-cases",
        law_name="",
        article_id="",
        content="高空抛物案件裁判摘要",
        score=0.7,
        retrieval_path="case",
    )
    graph_evidence = EvidenceItem(
        source_id="graph-1255",
        source_type="graph",
        knowledge_base_slug="civil-code",
        law_name="中华人民共和国民法典",
        article_id="1255",
        content="相邻法条关系",
        score=1.0,
        retrieval_path="graph",
    )

    class CaseRetriever:
        def retrieve(self, query, top_k=3):
            return [case_evidence]

    class GraphRetriever:
        def retrieve(self, article_id, max_hops=1):
            return type("Graph", (), {"retrieved_articles": [graph_evidence]})()

    workflow = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        router=lambda question: RouteDecision(
            intent="comparative", include_case=True, include_graph=True
        ),
        case_retriever=CaseRetriever(),
        graph_retriever=GraphRetriever(),
        answer_generator=lambda question, evidence, issues=None: (
            "依据【中华人民共和国民法典第1254条】，应当依法调查责任主体。"
        ),
    )

    result = workflow.query("高空抛物与坠物的区别", knowledge_base_slug="civil-code")

    assert result.verification_status == "pass"
    assert result.metadata["evidence_count"] == 3
    assert any(
        event["node"] == "case_retrieval" and event["output_count"] == 1
        for event in result.metadata["workflow_trace"]
    )
    assert any(
        event["node"] == "graph_retrieval" and event["output_count"] == 1
        for event in result.metadata["workflow_trace"]
    )


def test_ainvoke_returns_the_graph_backed_result_contract():
    workflow = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        answer_generator=lambda question, evidence, issues=None: (
            "依据【中华人民共和国民法典第1254条】，应当依法调查责任主体。"
        ),
    )

    result = asyncio.run(
        asyncio.wait_for(
            workflow.ainvoke("第1254条规定什么？", knowledge_base_slug="civil-code"),
            timeout=3,
        )
    )

    assert result.verification_status == "pass"
    assert result.metadata["orchestration_engine"] == "langgraph-stategraph"
    assert result.metadata["workflow_trace"][-1]["node"] == "finalize"


def test_astream_events_exposes_only_safe_structural_node_events():
    workflow = LegalEvidenceWorkflow(
        law_retriever=FakeLawRetriever(),
        answer_generator=lambda question, evidence, issues=None: (
            "依据【中华人民共和国民法典第1254条】，应当依法调查责任主体。"
        ),
    )

    assert callable(getattr(workflow, "astream_events", None))

    async def collect_events():
        return [
            event
            async for event in workflow.astream_events(
                "第1254条规定什么？ PRIVATE-QUESTION",
                knowledge_base_slug="civil-code",
                conversation_context=[
                    {"role": "user", "content": "PRIVATE-HISTORY-CONTENT"}
                ],
            )
        ]

    events = asyncio.run(asyncio.wait_for(collect_events(), timeout=3))
    serialized_events = json.dumps(events, ensure_ascii=False)
    allowed_keys = {
        "event",
        "node",
        "status",
        "duration_ms",
        "input_count",
        "output_count",
        "reason",
    }
    known_nodes = {
        "planning",
        "routing",
        "statute_retrieval",
        "case_retrieval",
        "graph_retrieval",
        "evidence_ledger",
        "answer",
        "citation_verifier",
        "repair",
        "finalize",
        "evidence_insufficient",
    }

    assert events
    assert all(set(event) <= allowed_keys for event in events)
    assert all(event["node"] in known_nodes for event in events)
    assert all(event["event"] in {"node_start", "node_end", "node_error"} for event in events)
    assert all(event["status"] in {"started", "completed", "degraded", "failed"} for event in events)
    assert any(event["node"] == "planning" and event["event"] == "node_start" for event in events)
    assert any(event["node"] == "finalize" and event["event"] == "node_end" for event in events)
    assert "PRIVATE-QUESTION" not in serialized_events
    assert "PRIVATE-HISTORY-CONTENT" not in serialized_events
    assert all("data" not in event for event in events)
    assert all("input" not in event for event in events)
    assert all("output" not in event for event in events)
    assert all("metadata" not in event for event in events)
