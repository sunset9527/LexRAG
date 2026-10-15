"""v3.0 组织管理员 API。"""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.auth import get_current_user
from app.db import session as db_session
from app.models.user import User
from app.services.agent_config_service import AgentConfigService
from app.services.audit_service import AuditService
from app.services.authorization_service import (
    AuthorizationContext,
    AuthorizationError,
    AuthorizationService,
)

router = APIRouter(prefix="/admin", tags=["组织管理"])


class MemberRoleRequest(BaseModel):
    role_code: str = Field(pattern="^(admin|lawyer|member)$")


class AgentConfigRequest(BaseModel):
    case_search_enabled: bool | None = None
    graph_search_enabled: bool | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    timeout_seconds: int | None = Field(default=None, ge=5, le=120)
    model_alias: str | None = Field(default=None, min_length=1, max_length=64)
    version_note: str | None = Field(default=None, max_length=256)


def get_authorization_service() -> AuthorizationService:
    if db_session.SessionLocal is None:
        raise HTTPException(status_code=503, detail="数据库服务未初始化")
    return AuthorizationService(db_session.SessionLocal)


def get_agent_config_service() -> AgentConfigService:
    if db_session.SessionLocal is None:
        raise HTTPException(status_code=503, detail="数据库服务未初始化")
    return AgentConfigService(db_session.SessionLocal)


def get_authorization_context(
    x_organization_id: Annotated[int | None, Header(alias="X-Organization-ID")] = None,
    current_user: User = Depends(get_current_user),
    service: AuthorizationService = Depends(get_authorization_service),
) -> AuthorizationContext:
    try:
        if x_organization_id is None:
            return service.build_default_context(user_id=current_user.id)
        return service.build_context(user_id=current_user.id, organization_id=x_organization_id)
    except AuthorizationError as exc:
        status_code = 400 if x_organization_id is None else 403
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


def _require(context: AuthorizationContext, permission_code: str) -> None:
    if not context.can(permission_code):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


def _audit(
    service: object,
    context: AuthorizationContext,
    *,
    action: str,
    target_type: str,
    target_id: str | None,
    metadata: dict | None = None,
) -> None:
    """审计故障不得阻断授权已成功的管理操作。"""
    try:
        AuditService(service.session_factory).append_event(
            event_id=str(uuid4()),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            status="success",
            metadata=metadata,
        )
    except Exception:
        pass


@router.get("/organization")
def get_current_organization(
    context: AuthorizationContext = Depends(get_authorization_context),
    service: AuthorizationService = Depends(get_authorization_service),
) -> dict[str, object]:
    with service.session_factory() as db:
        from app.models.organization import Organization

        organization = db.get(Organization, context.organization_id)
        if organization is None:
            raise HTTPException(status_code=404, detail="组织不存在")
        return {"id": organization.id, "name": organization.name, "role": context.role_code}


@router.get("/members")
def list_members(
    context: AuthorizationContext = Depends(get_authorization_context),
    service: AuthorizationService = Depends(get_authorization_service),
) -> dict[str, list[dict[str, object]]]:
    _require(context, "members:manage")
    return {"items": service.list_members(organization_id=context.organization_id)}


@router.put("/members/{user_id}/role", status_code=status.HTTP_204_NO_CONTENT)
def change_member_role(
    user_id: int,
    request: MemberRoleRequest,
    context: AuthorizationContext = Depends(get_authorization_context),
    service: AuthorizationService = Depends(get_authorization_service),
) -> None:
    _require(context, "members:manage")
    try:
        service.assign_role(
            user_id=user_id,
            organization_id=context.organization_id,
            role_code=request.role_code,
        )
        _audit(
            service,
            context,
            action="member.role_changed",
            target_type="member",
            target_id=str(user_id),
            metadata={"role_code": request.role_code},
        )
    except AuthorizationError as exc:
        raise HTTPException(status_code=404, detail="成员或角色不存在") from exc


@router.get("/usage")
def get_usage(
    context: AuthorizationContext = Depends(get_authorization_context),
    service: AuthorizationService = Depends(get_authorization_service),
) -> dict[str, list[dict[str, object]]]:
    """按组织返回聚合统计；不暴露单条问答或用户 Token。"""
    _require(context, "analytics:read")
    from app.models.usage_daily import UsageDaily

    with service.session_factory() as db:
        items = db.scalars(
            select(UsageDaily)
            .where(UsageDaily.organization_id == context.organization_id)
            .order_by(UsageDaily.stat_date.desc())
            .limit(90)
        ).all()
        return {
            "items": [
                {
                    "date": item.stat_date.isoformat(),
                    "query_count": item.query_count,
                    "success_count": item.success_count,
                    "failure_count": item.failure_count,
                    "cache_hit_count": item.cache_hit_count,
                    "total_latency_ms": item.total_latency_ms,
                }
                for item in items
            ]
        }


@router.get("/audit-logs")
def list_audit_logs(
    context: AuthorizationContext = Depends(get_authorization_context),
    service: AuthorizationService = Depends(get_authorization_service),
) -> dict[str, list[dict[str, object]]]:
    """返回脱敏审计事件；metadata 中只有哈希、长度和白名单字段。"""
    _require(context, "audit:read")
    from app.models.audit_log import AuditLog

    with service.session_factory() as db:
        items = db.scalars(
            select(AuditLog)
            .where(AuditLog.organization_id == context.organization_id)
            .order_by(AuditLog.created_at.desc())
            .limit(200)
        ).all()
        return {
            "items": [
                {
                    "event_id": item.event_id,
                    "action": item.action,
                    "target_type": item.target_type,
                    "status": item.status,
                    "request_id": item.request_id,
                    "metadata": item.metadata_,
                    "created_at": item.created_at.isoformat(),
                }
                for item in items
            ]
        }


@router.get("/agent-config")
def get_agent_config(
    context: AuthorizationContext = Depends(get_authorization_context),
    service: AgentConfigService = Depends(get_agent_config_service),
) -> dict[str, object]:
    _require(context, "agents:manage")
    return service.get(organization_id=context.organization_id)


@router.put("/agent-config")
def update_agent_config(
    request: AgentConfigRequest,
    context: AuthorizationContext = Depends(get_authorization_context),
    service: AgentConfigService = Depends(get_agent_config_service),
) -> dict[str, object]:
    _require(context, "agents:manage")
    try:
        result = service.upsert(
            organization_id=context.organization_id,
            values=request.model_dump(exclude_none=True),
        )
        _audit(
            service,
            context,
            action="agent_config.updated",
            target_type="agent_config",
            target_id=str(context.organization_id),
            metadata={"field_count": len(request.model_dump(exclude_none=True))},
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
