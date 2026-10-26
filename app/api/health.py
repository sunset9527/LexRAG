"""Liveness and dependency-aware readiness endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_runtime
from app.runtime import RuntimeContainer
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.readiness_service import ReadinessService

router = APIRouter(tags=["健康检查"])


@router.get("/", response_model=dict[str, str])
def root() -> dict[str, str]:
    """Return the stable API discovery payload."""

    return {"message": "LexRAG 法律智能知识平台 API", "version": "3.0.0", "docs": "/docs"}


@router.get("/health", response_model=HealthResponse)
def health_check(runtime: RuntimeContainer = Depends(get_runtime)) -> HealthResponse:
    """Report process-owned component availability without probing dependencies."""

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC).isoformat(),
        version="3.0.0",
        components={
            "workflow": "ready" if runtime.get("workflow") else "not_ready",
            "law_indexer": "ready" if runtime.get("law_indexer") else "not_ready",
            "law_graph": "ready" if runtime.get("law_graph") else "not_ready",
        },
    )


@router.get("/health/live", response_model=dict[str, str])
def health_live() -> dict[str, str]:
    """Process liveness only; dependencies are intentionally not probed here."""

    return {"status": "alive"}


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
def health_ready(runtime: RuntimeContainer = Depends(get_runtime)) -> ReadinessResponse:
    """Return a safe dependency-aware readiness result."""

    service = runtime.get("readiness_service")
    if not isinstance(service, ReadinessService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "components": {"runtime": "not_ready"}},
        )
    report = service.check()
    payload = ReadinessResponse(
        status="ready" if report.ready else "not_ready", components=report.components
    )
    if not report.ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=payload.model_dump()
        )
    return payload
