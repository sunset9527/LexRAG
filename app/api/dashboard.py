"""Dashboard endpoints backed by persisted services."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import get_current_user
from app.api.dependencies import get_runtime
from app.models.user import User
from app.runtime import RuntimeContainer
from app.schemas.dashboard import DashboardStatsResponse

router = APIRouter(prefix="/dashboard", tags=["工作台"])


@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    runtime: RuntimeContainer = Depends(get_runtime),
) -> DashboardStatsResponse:
    """Return persisted case-library counts rather than frontend constants."""

    del current_user
    service = runtime.get("case_ingestion_service")
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="案例服务未初始化"
        )
    return DashboardStatsResponse.model_validate(service.get_statistics())
