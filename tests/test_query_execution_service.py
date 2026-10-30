from __future__ import annotations

from app.services.query_execution_service import (
    build_cache_scope,
    build_evidence_answer_generator,
    is_cacheable_query_result,
    load_or_create_session,
    record_query_observability,
    resolve_collections,
    route_evidence_workflow,
)


def test_evidence_answer_generator_uses_repair_llm_only_for_verifier_issues() -> None:
    class FakeLLM:
        def __init__(self, answer: str) -> None:
            self.answer = answer
            self.calls = []

        def invoke(self, prompt: str):
            self.calls.append(prompt)
            return type("Response", (), {"content": self.answer})()

    answer_llm = FakeLLM("initial answer")
    repair_llm = FakeLLM("repaired answer")
    generator = build_evidence_answer_generator(answer_llm, repair_llm=repair_llm)
    evidence = [
        type(
            "Evidence",
            (),
            {
                "source_type": "statute",
                "law_name": "中华人民共和国民法典",
                "normalized_article_id": "17",
                "content": "十八周岁以上的自然人为成年人。",
            },
        )()
    ]

    assert generator("成年人多大？", evidence) == "initial answer"
    assert generator("成年人多大？", evidence, ["citation missing"]) == "repaired answer"
    assert len(answer_llm.calls) == 1
    assert len(repair_llm.calls) == 1


def test_query_execution_service_routes_comparative_questions_without_graph_expansion() -> None:
    decision = route_evidence_workflow("定金和订金有什么区别？")

    assert decision.intent == "comparative"
    assert decision.include_case is False


def test_query_execution_service_only_caches_verified_cacheable_results() -> None:
    assert is_cacheable_query_result(
        {"verification_status": "pass", "metadata": {"cacheable": True}}
    )
    assert not is_cacheable_query_result(
        {"verification_status": "fail", "metadata": {"cacheable": True}}
    )


def test_query_execution_service_records_metrics_without_persistence_services() -> None:
    captured = {}

    record_query_observability(
        event_id="request-1",
        organization_id=1,
        current_user_id=2,
        question="成年人多大",
        answer="十八周岁",
        verification_status="pass",
        metadata={"workflow_trace": [{"node": "answer", "duration_ms": 1}]},
        latency_ms=3,
        audit_service=None,
        usage_service=None,
        metrics_recorder=lambda **kwargs: captured.update(kwargs),
    )

    assert captured["workflow_trace"] == [{"node": "answer", "duration_ms": 1}]


def test_query_execution_service_creates_session_and_loads_memory() -> None:
    class FakeSessionService:
        def create(self, *, user_id, initial_question, organization_id):
            assert (user_id, initial_question, organization_id) == (2, "合同有效吗", 1)
            return {"id": "session-1"}

        def load_memory(self, *, user_id, session_id, organization_id):
            assert (user_id, session_id, organization_id) == (2, "session-1", 1)
            return ["history"]

    session_id, memory = load_or_create_session(
        FakeSessionService(),
        user_id=2,
        organization_id=1,
        requested_session_id=None,
        question="合同有效吗",
    )

    assert (session_id, memory) == ("session-1", ["history"])


def test_query_execution_service_resolves_collections_through_version_service() -> None:
    class Selection:
        collection_name = "kb_civil_code_v2"

    class FakeVersionService:
        def resolve(self, slug, *, organization_id, case_date):
            assert (slug, organization_id, case_date) == ("civil-code", 1, "2025-01-01")
            return Selection()

    primary, selections, collections = resolve_collections(
        knowledge_base_service=None,
        query_version_service=FakeVersionService(),
        selected_slugs=["civil-code"],
        organization_id=1,
        case_date="2025-01-01",
    )

    assert primary is selections["civil-code"]
    assert collections == {"civil-code": "kb_civil_code_v2"}


def test_query_execution_service_builds_cache_scope_without_secret_material() -> None:
    scope = build_cache_scope(
        user_id=2,
        session_id="session-1",
        selected_slugs=["civil-code"],
        base_url="https://api.example.com",
        model="model-a",
        retrieval_version="r1",
        case_date=None,
        version_selections={},
    )

    assert scope["user_scope"] == "user:2"
    assert scope["knowledge_base_slug"] == "civil-code"
    assert "api_key" not in scope
    assert "authorization" not in scope
