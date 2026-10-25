"""查询 API 的缓存命中契约。"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import api


class FakeSessionService:
    def __init__(self, _factory):
        self.turns = []

    def create(self, *, user_id, initial_question, organization_id=None):
        return {"id": "session-1", "user_id": user_id, "is_active": True}

    def get_for_user(self, **_kwargs):
        return {"id": "session-1", "is_active": True}

    def load_memory(self, **_kwargs):
        return []

    def record_turn(self, **kwargs):
        self.turns.append(kwargs)


@pytest.fixture(autouse=True)
def authenticated_query(monkeypatch):
    """v2.4 后 /query 必须在登录用户的会话内执行。"""
    api.app.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(id=7)
    api.app.dependency_overrides[api.get_authorization_context] = lambda: SimpleNamespace(
        organization_id=9,
        can=lambda permission: permission == "queries:create",
    )
    monkeypatch.setattr(api.db_session, "SessionLocal", object())
    monkeypatch.setattr(api, "SessionService", FakeSessionService)
    yield
    api.app.dependency_overrides.pop(api.get_current_user, None)
    api.app.dependency_overrides.pop(api.get_authorization_context, None)


class FakeKnowledgeBaseService:
    def list_visible_knowledge_bases(self, *, organization_id):
        assert organization_id == 9
        return [
            {
                "slug": "civil-code",
                "name": "中华人民共和国民法典",
                "type": "statute",
                "status": "READY",
            }
        ]

    def get_ready_collection_name(self, slug):
        assert slug == "civil-code"
        return "kb_civil_code"

    def get_ready_collection_name_for_organization(self, slug, *, organization_id):
        assert organization_id == 9
        return self.get_ready_collection_name(slug)


class ExactHitCache:
    def __init__(self):
        self.scope = None

    def get_exact(self, query, scope):
        assert query == "成年人多大"
        self.scope = scope
        return {
            "query_id": "cached-query",
            "query": query,
            "answer": "年满十八周岁的自然人为成年人。",
            "intent": "law_query",
            "citations": [],
            "verification_status": "pass",
            "verification_issues": [],
            "sub_questions": [],
            "metadata": {"retrieval_version": "v2.0"},
        }


class FakeAuditService:
    def __init__(self):
        self.calls = []

    def append_query(self, **kwargs):
        self.calls.append(kwargs)
        return True


class FakeUsageService:
    def __init__(self):
        self.calls = []

    def record_query(self, **kwargs):
        self.calls.append(kwargs)
        return True


def test_query_returns_exact_cache_before_constructing_a_retriever(monkeypatch):
    """精确命中时不应加载 Chroma 或再次调用 LLM。"""
    cache = ExactHitCache()
    monkeypatch.setattr(
        api,
        "components",
        {
            "workflow": object(),
            "knowledge_base_service": FakeKnowledgeBaseService(),
            "query_cache_service": cache,
        },
    )

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/query",
                headers={"Authorization": "Bearer a-user-token"},
                json={"query": "成年人多大", "knowledge_base_ids": ["civil-code"]},
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json()["metadata"]["cache_hit"] == "exact"
    assert response.json()["metadata"]["knowledge_base_routing"]["selected_slugs"] == [
        "civil-code"
    ]
    assert cache.scope["knowledge_base_slug"] == "civil-code"
    assert cache.scope["user_scope"] != "Bearer a-user-token"


def test_query_case_date_selects_version_and_keeps_it_in_cache_scope(monkeypatch):
    cache = ExactHitCache()
    observed = {}

    class FakeVersionService:
        def resolve(self, slug, *, organization_id, case_date):
            observed.update({"slug": slug, "organization_id": organization_id, "case_date": case_date})
            return SimpleNamespace(
                collection_name="kb_civil_code_v_abcdef123456",
                provenance={
                    "version_id": "civil-code@2020-05-28",
                    "effective_from": "2021-01-01",
                    "effective_to": "",
                    "source_url": "https://flk.npc.gov.cn/",
                    "content_hash": "a" * 64,
                },
                timeline=[],
                assumption=None,
                as_of=__import__("datetime").date(2025, 1, 1),
            )

    monkeypatch.setattr(
        api,
        "components",
        {
            "workflow": object(),
            "knowledge_base_service": FakeKnowledgeBaseService(),
            "query_cache_service": cache,
            "query_version_service": FakeVersionService(),
        },
    )

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/query",
                headers={"Authorization": "Bearer a-user-token"},
                json={
                    "query": "成年人多大",
                    "knowledge_base_ids": ["civil-code"],
                    "case_date": "2025-01-01",
                },
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert observed == {
        "slug": "civil-code",
        "organization_id": 9,
        "case_date": __import__("datetime").date(2025, 1, 1),
    }
    assert cache.scope["case_date"] == "2025-01-01"
    assert response.json()["metadata"]["version_selection"]["version_id"] == "civil-code@2020-05-28"


def test_exact_cache_hit_writes_redacted_audit_and_idempotent_usage_event(monkeypatch):
    cache = ExactHitCache()
    audit = FakeAuditService()
    usage = FakeUsageService()
    monkeypatch.setattr(
        api,
        "components",
        {
            "workflow": object(),
            "knowledge_base_service": FakeKnowledgeBaseService(),
            "query_cache_service": cache,
            "audit_service": audit,
            "usage_service": usage,
        },
    )

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/query",
                headers={"Authorization": "Bearer a-user-token", "X-Request-ID": "request-42"},
                json={"query": "成年人多大", "knowledge_base_ids": ["civil-code"]},
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert audit.calls[0]["event_id"] == "request-42"
    assert audit.calls[0]["organization_id"] == 9
    assert audit.calls[0]["actor_user_id"] == 7
    assert audit.calls[0]["question"] == "成年人多大"
    assert audit.calls[0]["metadata"]["cache_hit"] == "exact"
    assert usage.calls[0]["event_id"] == "request-42"


def test_query_rejects_invalid_runtime_base_url_before_cache_or_llm(monkeypatch):
    """模型运行时配置只能接受 HTTP(S) 地址，避免把无效配置带入工作流。"""
    monkeypatch.setattr(api, "components", {"workflow": object()})

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/query",
                headers={"X-Base-URL": "file:///not-an-llm-endpoint"},
                json={"query": "成年人多大", "knowledge_base_ids": ["civil-code"]},
            )

    response = asyncio.run(request())

    assert response.status_code == 422
    assert "Base URL" in response.json()["detail"]


def test_query_invokes_graph_with_scoped_collection_and_request_context(monkeypatch):
    """缓存未命中时应调用 Graph 入口，并显式传入非敏感请求上下文。"""

    memory_turns = [
        {
            "question": "之前的问题",
            "answer": "之前的回答",
            "verified_citations": [],
        }
    ]
    observed = {}

    class MemorySessionService(FakeSessionService):
        def load_memory(self, **_kwargs):
            return memory_turns

    class FakeIndexer:
        def __init__(self, **_kwargs):
            self.vectorstore = object()

    class FakeWorkflow:
        def __init__(self, **_kwargs):
            pass

        def invoke(
            self,
            question,
            *,
            knowledge_base_slugs,
            conversation_context,
            request_context,
        ):
            observed.update(
                {
                    "question": question,
                    "knowledge_base_slugs": knowledge_base_slugs,
                    "conversation_context": conversation_context,
                    "request_context": request_context,
                }
            )
            return SimpleNamespace(
                query=question,
                answer="合同成立需符合要约与承诺等条件。",
                intent="law_query",
                citations=[],
                verification_status="pass",
                verification_issues=[],
                sub_questions=[],
                metadata={},
            )

    monkeypatch.setattr(
        api,
        "components",
        {
            "workflow": object(),
            "knowledge_base_service": FakeKnowledgeBaseService(),
            "query_cache_service": None,
            "case_retriever": None,
            "graph_retriever": None,
            "query_rewriter": None,
        },
    )
    monkeypatch.setattr(api, "LawIndexer", FakeIndexer)
    monkeypatch.setattr(api, "LawRetriever", lambda **_kwargs: object())
    monkeypatch.setattr(api, "create_llm", lambda **_kwargs: object())
    monkeypatch.setattr(api, "LegalEvidenceWorkflow", FakeWorkflow)
    monkeypatch.setattr(api, "SessionService", MemorySessionService)
    monkeypatch.setattr(api, "build_evidence_answer_generator", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(api, "build_evidence_planner", lambda *_args, **_kwargs: object())

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/query",
                headers={"Authorization": "Bearer a-user-token"},
                json={
                    "query": "合同成立需要满足哪些条件？",
                    "knowledge_base_ids": ["civil-code"],
                    "config": {"cache_bypass": True},
                },
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json()["answer"] == "合同成立需符合要约与承诺等条件。"
    assert observed == {
        "question": "合同成立需要满足哪些条件？",
        "knowledge_base_slugs": ["civil-code"],
        "conversation_context": memory_turns,
        "request_context": {
            "user_id": 7,
            "organization_id": 9,
            "session_id": "session-1",
            "model_id": api.settings.deepseek_model,
        },
    }


def test_only_verified_evidence_workflow_results_are_cacheable():
    """校验失败或明确标记不可缓存的回答不能进入 v2.0 缓存。"""
    assert api.is_cacheable_query_result(
        {"verification_status": "pass", "metadata": {"cacheable": True}}
    )
    assert not api.is_cacheable_query_result(
        {"verification_status": "fail", "metadata": {"cacheable": False}}
    )
    assert not api.is_cacheable_query_result(
        {"verification_status": "pass", "metadata": {"cacheable": False}}
    )
