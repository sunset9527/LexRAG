"""阶段 6 查询运行与 SSE 协议契约。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import api
from app.services.query_event_store import InMemoryQueryEventStore
from src.workflow.legal_evidence_workflow import QueryCancelled


@pytest.fixture(autouse=True)
def authenticated_user(monkeypatch):
    api.app.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(id=7)
    api.app.dependency_overrides[api.get_authorization_context] = lambda: SimpleNamespace(
        organization_id=9,
        can=lambda permission: permission == "queries:create",
    )
    store = InMemoryQueryEventStore()
    monkeypatch.setattr(api, "components", {"query_event_store": store})
    yield store
    api.app.dependency_overrides.pop(api.get_current_user, None)
    api.app.dependency_overrides.pop(api.get_authorization_context, None)


def test_query_run_returns_a_query_id_and_replays_events_after_cancellation(monkeypatch):
    async def idle_executor(**_kwargs):
        return None

    monkeypatch.setattr(api, "execute_query_run", idle_executor)

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            accepted = await client.post("/query-runs", json={"query": "成年人多大"})
            query_id = accepted.json()["query_id"]
            cancelled = await client.post(f"/query-runs/{query_id}/cancel")
            events = await client.get(f"/query-runs/{query_id}/events")
            return accepted, cancelled, events

    accepted, cancelled, events = asyncio.run(request())

    assert accepted.status_code == 202
    assert accepted.json()["query_id"]
    assert cancelled.status_code == 202
    assert events.headers["content-type"].startswith("text/event-stream")
    assert "event: accepted" in events.text
    assert "event: cancelled" in events.text


def test_query_run_cancel_requires_ownership_and_is_idempotent(authenticated_user):
    authenticated_user.create_run("owned-run", user_id=7, organization_id=9)

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post("/query-runs/owned-run/cancel")
            second = await client.post("/query-runs/owned-run/cancel")
            return first, second

    first, second = asyncio.run(request())

    assert first.status_code == 202
    assert first.json() == {"query_id": "owned-run", "cancelled": True}
    assert second.status_code == 202
    assert second.json() == {"query_id": "owned-run", "cancelled": False}


def test_query_run_executor_emits_a_final_response_without_repeating_the_question(monkeypatch):
    store = InMemoryQueryEventStore()
    store.create_run("run-1", user_id=7, organization_id=9)

    async def fake_query(**kwargs):
        kwargs["http_request"].state.workflow_event_sink(
            {
                "node": "routing",
                "status": "completed",
                "duration_ms": 1.0,
                "input_count": 0,
                "output_count": 1,
            }
        )
        return api.QueryResponse(
            query_id="session-1",
            query="不应写进事件载荷的咨询原文",
            answer="年满十八周岁的自然人为成年人。",
            intent="law_query",
            citations=[],
            verification_status="pass",
            verification_issues=[],
            sub_questions=[],
            metadata={},
        )

    monkeypatch.setattr(api, "query", fake_query)
    monkeypatch.setattr(api, "components", {"query_event_store": store})

    asyncio.run(
        api.execute_query_run(
            query_id="run-1",
            http_request=SimpleNamespace(state=SimpleNamespace()),
            request=api.QueryRequest(query="成年人多大"),
            x_api_key=None,
            x_model=None,
            x_base_url=None,
            x_request_id=None,
            authorization=None,
            current_user=SimpleNamespace(id=7),
            authorization_context=SimpleNamespace(organization_id=9),
        )
    )

    events = store.events_after("run-1")
    assert [event.type for event in events] == ["stage_started", "stage_completed", "completed"]
    assert events[-1].data["response"]["answer"] == "年满十八周岁的自然人为成年人。"
    assert "query" not in events[-1].data["response"]


def test_query_run_starts_the_executor_after_acceptance(monkeypatch, authenticated_user):
    started = []

    async def fake_executor(**kwargs):
        started.append(kwargs["query_id"])
        authenticated_user.append(kwargs["query_id"], "completed", {"response": {}})

    monkeypatch.setattr(api, "execute_query_run", fake_executor)

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/query-runs", json={"query": "成年人多大"})
            await asyncio.sleep(0)
            return response

    response = asyncio.run(request())

    query_id = response.json()["query_id"]
    assert started == [query_id]
    assert [event.type for event in authenticated_user.events_after(query_id)] == [
        "accepted",
        "completed",
    ]


def test_query_run_executor_does_not_turn_a_cancellation_into_a_failure(monkeypatch):
    store = InMemoryQueryEventStore()
    store.create_run("run-1", user_id=7, organization_id=9)

    async def cancelled_query(**_kwargs):
        raise QueryCancelled()

    monkeypatch.setattr(api, "query", cancelled_query)
    monkeypatch.setattr(api, "components", {"query_event_store": store})

    asyncio.run(
        api.execute_query_run(
            query_id="run-1",
            http_request=SimpleNamespace(state=SimpleNamespace()),
            request=api.QueryRequest(query="成年人多大"),
            x_api_key=None,
            x_model=None,
            x_base_url=None,
            x_request_id=None,
            authorization=None,
            current_user=SimpleNamespace(id=7),
            authorization_context=SimpleNamespace(organization_id=9),
        )
    )

    assert [event.type for event in store.events_after("run-1")] == ["stage_started"]


def test_sse_event_iterator_polls_for_new_events_without_waiting_a_heartbeat(monkeypatch):
    store = InMemoryQueryEventStore()
    store.create_run("run-1", user_id=7, organization_id=9)
    store.append("run-1", "stage_completed", {"stage": "routing"})
    sleep_delays = []
    disconnect_checks = 0

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    async def is_disconnected():
        nonlocal disconnect_checks
        disconnect_checks += 1
        return disconnect_checks >= 2

    monkeypatch.setattr(api.asyncio, "sleep", fake_sleep)

    async def collect():
        return [
            event
            async for event in api.iter_query_run_events(
                store=store,
                query_id="run-1",
                after_sequence=0,
                is_disconnected=is_disconnected,
            )
        ]

    events = asyncio.run(collect())

    assert events == ['id: 1\nevent: stage_completed\ndata: {"stage":"routing"}\n\n']
    assert sleep_delays == [0.25]
