"""Annual-case library endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.admin import get_authorization_context
from app.api.dependencies import get_runtime
from app.runtime import RuntimeContainer
from app.services.authorization_service import AuthorizationContext

router = APIRouter(tags=["案例库"])


def _component(runtime: RuntimeContainer, name: str, message: str) -> Any:
    component = runtime.get(name)
    if component is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message)
    return component


def _require_cases_read(context: AuthorizationContext) -> None:
    if not context.can("cases:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


@router.get("/cases")
def list_cases(
    domain: str | None = Query(default=None, description="法律领域"),
    case_cause: str | None = Query(default=None, description="案由"),
    source_id: int | None = Query(default=None, ge=1, description="案例源 ID"),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, list[dict[str, Any]]]:
    _require_cases_read(authorization_context)
    service = _component(runtime, "case_ingestion_service", "案例库服务未初始化")
    return {
        "items": service.list_cases(
            domain=domain,
            case_cause=case_cause,
            source_id=source_id,
        )
    }


@router.get("/case-sources")
def list_case_sources(
    domain: str | None = Query(default=None, description="法律领域"),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, list[dict[str, Any]]]:
    _require_cases_read(authorization_context)
    service = _component(runtime, "case_ingestion_service", "案例库服务未初始化")
    return {"items": service.list_sources(domain=domain)}


@router.get("/cases/{case_id}")
def get_case(
    case_id: str,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, Any]:
    _require_cases_read(authorization_context)
    service = _component(runtime, "case_ingestion_service", "案例库服务未初始化")
    try:
        return service.get_case(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/cases/{case_id}/similar")
def similar_cases(
    case_id: str,
    top_k: int = Query(default=5, ge=1, le=20),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> dict[str, list[dict[str, Any]]]:
    _require_cases_read(authorization_context)
    retriever = _component(runtime, "annual_case_retriever", "年度案例检索服务未初始化")
    try:
        return {"items": retriever.similar_cases(case_id, top_k=top_k)}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
