"""查询 API 的缓存命中契约。"""

import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import api


class FakeKnowledgeBaseService:
    def get_ready_collection_name(self, slug):
        assert slug == "civil-code"
        return "kb_civil_code"


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
    assert cache.scope["knowledge_base_slug"] == "civil-code"
    assert cache.scope["user_scope"] != "Bearer a-user-token"


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
