from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import HTTPException

from app.services.query_event_store import InMemoryQueryEventStore
from app.services.query_event_store import QueryEvent
from app.services.query_run_service import QueryRunService


def test_query_run_service_encodes_sse_events_with_sequence_and_json_payload() -> None:
    service = QueryRunService(run_query=lambda **_kwargs: None)

    encoded = service.encode_event(QueryEvent(sequence=3, type="accepted", data={"query_id": "q-1"}))

    assert encoded == 'id: 3\nevent: accepted\ndata: {"query_id":"q-1"}\n\n'


def test_query_run_service_logs_safe_http_failure_status(caplog) -> None:
    async def rejected_query(**_kwargs):
        raise HTTPException(status_code=422, detail="sensitive internal detail")

    store = InMemoryQueryEventStore()
    store.create_run("run-1", user_id=7, organization_id=9)
    service = QueryRunService(run_query=rejected_query)

    asyncio.run(
        service.execute(
            store=store,
            query_id="run-1",
            http_request=SimpleNamespace(state=SimpleNamespace()),
            request=SimpleNamespace(),
            x_api_key=None,
            x_model=None,
            x_base_url=None,
            x_request_id=None,
            authorization=None,
            current_user=SimpleNamespace(id=7),
            authorization_context=SimpleNamespace(organization_id=9),
        )
    )

    assert store.events_after("run-1")[-1].data == {"code": "HTTP_422"}
    assert "query_id=run-1 http_status=422" in caplog.text
    assert "sensitive internal detail" not in caplog.text
