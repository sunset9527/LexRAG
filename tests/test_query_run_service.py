from __future__ import annotations

from app.services.query_event_store import QueryEvent
from app.services.query_run_service import QueryRunService


def test_query_run_service_encodes_sse_events_with_sequence_and_json_payload() -> None:
    service = QueryRunService(run_query=lambda **_kwargs: None)

    encoded = service.encode_event(QueryEvent(sequence=3, type="accepted", data={"query_id": "q-1"}))

    assert encoded == 'id: 3\nevent: accepted\ndata: {"query_id":"q-1"}\n\n'
