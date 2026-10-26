"""Protocol-neutral execution support for streaming query runs."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import HTTPException, Request

from app.services.authorization_service import AuthorizationContext
from app.services.query_event_store import QueryEvent
from src.workflow.legal_evidence_workflow import QueryCancelled

logger = logging.getLogger(__name__)


class QueryRunService:
    def __init__(self, *, run_query: Callable[..., Awaitable[Any]]) -> None:
        self._run_query = run_query

    @staticmethod
    def encode_event(event: QueryEvent) -> str:
        payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
        return f"id: {event.sequence}\nevent: {event.type}\ndata: {payload}\n\n"

    async def iter_events(
        self,
        *,
        store: Any,
        query_id: str,
        after_sequence: int,
        is_disconnected: Callable[[], Awaitable[bool]],
    ) -> AsyncIterator[str]:
        sequence = after_sequence
        terminal_events = {"completed", "cancelled", "failed"}
        next_heartbeat_at = time.monotonic() + 10
        while True:
            for event in store.events_after(query_id, after_sequence=sequence):
                sequence = event.sequence
                yield self.encode_event(event)
                if event.type in terminal_events:
                    return
            if await is_disconnected():
                return
            if time.monotonic() >= next_heartbeat_at:
                yield ": heartbeat\n\n"
                next_heartbeat_at = time.monotonic() + 10
            await asyncio.sleep(0.25)

    async def invoke_workflow(self, workflow: Any, question: str, **kwargs: Any) -> Any:
        return await asyncio.to_thread(workflow.invoke, question, **kwargs)

    async def execute(
        self,
        *,
        store: Any,
        query_id: str,
        http_request: Request,
        request: Any,
        x_api_key: str | None,
        x_model: str | None,
        x_base_url: str | None,
        x_request_id: str | None,
        authorization: str | None,
        current_user: Any,
        authorization_context: AuthorizationContext,
    ) -> None:
        if store.is_cancel_requested(query_id):
            return
        store.append(query_id, "stage_started", {"stage": "workflow"})

        def emit_workflow_trace(trace: dict[str, Any]) -> None:
            if store.is_cancel_requested(query_id):
                return
            payload = {
                key: trace[key]
                for key in ("node", "status", "duration_ms", "input_count", "output_count", "reason")
                if key in trace
            }
            if "node" in payload:
                payload["stage"] = payload.pop("node")
                store.append(query_id, "stage_completed", payload)

        http_request.state.workflow_event_sink = emit_workflow_trace
        http_request.state.workflow_cancel_requested = lambda: store.is_cancel_requested(query_id)
        try:
            response = await self._run_query(
                http_request=http_request,
                request=request,
                x_api_key=x_api_key,
                x_model=x_model,
                x_base_url=x_base_url,
                x_request_id=x_request_id,
                authorization=authorization,
                current_user=current_user,
                authorization_context=authorization_context,
            )
        except HTTPException as exc:
            if not store.is_cancel_requested(query_id):
                store.append(query_id, "failed", {"code": f"HTTP_{exc.status_code}"})
            return
        except QueryCancelled:
            return
        except Exception as exc:
            logger.error("流式查询执行失败 query_id=%s error_type=%s", query_id, type(exc).__name__)
            if not store.is_cancel_requested(query_id):
                store.append(query_id, "failed", {"code": "QUERY_EXECUTION_FAILED"})
            return
        finally:
            for attribute in ("workflow_event_sink", "workflow_cancel_requested"):
                if hasattr(http_request.state, attribute):
                    delattr(http_request.state, attribute)
        if not store.is_cancel_requested(query_id):
            store.append(query_id, "completed", {"response": response.model_dump(exclude={"query"})})
