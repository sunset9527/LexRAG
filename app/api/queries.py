"""HTTP and SSE transport for legal query orchestration."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.admin import get_authorization_context
from app.api.auth import get_current_user
from app.api.dependencies import get_runtime
from app.models.user import User
from app.runtime import RuntimeContainer
from app.schemas.query import QueryRequest, QueryResponse, QueryRunAccepted
from app.services.authorization_service import AuthorizationContext
from app.services.query_route_service import QueryRouteService

router = APIRouter(tags=["法律问答"])


def _service(runtime: RuntimeContainer) -> QueryRouteService:
    service = runtime.get("query_route_service")
    if service is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="查询服务未初始化")
    return service


def _require_query_access(context: AuthorizationContext) -> None:
    if not context.can("queries:create"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


@router.post("/query-runs", response_model=QueryRunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_query_run(
    http_request: Request,
    request: QueryRequest,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_model: str | None = Header(None, alias="X-Model"),
    x_base_url: str | None = Header(None, alias="X-Base-URL"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    authorization: str | None = Header(None, alias="Authorization"),
    current_user: User = Depends(get_current_user),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> QueryRunAccepted:
    _require_query_access(authorization_context)
    service = _service(runtime)
    store = service.get_event_store()
    query_id = uuid.uuid4().hex
    store.create_run(query_id, user_id=current_user.id, organization_id=authorization_context.organization_id)
    store.append(query_id, "accepted", {"query_id": query_id})
    asyncio.create_task(
        service.execute_query_run(
            query_id=query_id,
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
    )
    return QueryRunAccepted(query_id=query_id)


@router.get("/query-runs/{query_id}/events")
async def stream_query_run_events(
    query_id: str,
    http_request: Request,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    current_user: User = Depends(get_current_user),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> StreamingResponse:
    service = _service(runtime)
    store = service.get_event_store()
    if not store.can_access(query_id, user_id=current_user.id, organization_id=authorization_context.organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="查询不存在或无访问权限")
    try:
        sequence = max(0, int(last_event_id or "0"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Last-Event-ID 无效") from exc

    async def event_stream() -> AsyncIterator[str]:
        async for event in service.iterate_events(
            store=store,
            query_id=query_id,
            after_sequence=sequence,
            is_disconnected=http_request.is_disconnected,
        ):
            yield event

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/query-runs/{query_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_query_run(
    query_id: str,
    current_user: User = Depends(get_current_user),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    service = _service(runtime)
    store = service.get_event_store()
    if not store.can_access(query_id, user_id=current_user.id, organization_id=authorization_context.organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="查询不存在或无访问权限")
    return {"query_id": query_id, "cancelled": store.request_cancel(query_id)}


@router.post("/query", response_model=QueryResponse)
async def query(
    http_request: Request,
    request: QueryRequest,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_model: str | None = Header(None, alias="X-Model"),
    x_base_url: str | None = Header(None, alias="X-Base-URL"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    authorization: str | None = Header(None, alias="Authorization"),
    current_user: User = Depends(get_current_user),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> QueryResponse:
    _require_query_access(authorization_context)
    return await _service(runtime).execute_query(
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
