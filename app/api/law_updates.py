"""法规更新订阅 API。

自动任务只负责发现变化；将来源内容投入索引前必须由组织管理员确认。
"""

from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, HttpUrl

from app.api.admin import get_authorization_context
from app.db import session as db_session
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthorizationContext
from app.services.law_update_service import LawUpdateService
from app.services.legal_source_intake_service import LegalSourceIntakeService
from app.services.statute_version_chain_service import (
    StatuteVersionChainError,
    StatuteVersionChainService,
)

router = APIRouter(prefix="/law-updates", tags=["法规更新"])


class SubscriptionRequest(BaseModel):
    law_name: str = Field(min_length=1, max_length=128)
    source_url: HttpUrl
    knowledge_base_slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SnapshotRequest(BaseModel):
    """仅用于本机演示或由受信采集任务调用；不接收用户上传法规作为正式来源。"""

    content: str = Field(min_length=1)


class LocalSourceVerificationRequest(BaseModel):
    authority_url: HttpUrl


class VersionChainMemberRequest(BaseModel):
    source_import_id: int = Field(gt=0)
    role: str = Field(min_length=1, max_length=32)


class VersionChainRequest(BaseModel):
    law_slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    target_version_id: str = Field(min_length=1, max_length=128)
    effective_from: date
    effective_to: date | None = None
    consolidated_source_import_id: int | None = Field(default=None, gt=0)
    members: list[VersionChainMemberRequest] = Field(min_length=1)


def get_law_update_service() -> LawUpdateService:
    if db_session.SessionLocal is None:
        raise HTTPException(status_code=503, detail="数据库服务未初始化")
    return LawUpdateService(db_session.SessionLocal)


def get_legal_source_intake_service() -> LegalSourceIntakeService:
    if db_session.SessionLocal is None:
        raise HTTPException(status_code=503, detail="数据库服务未初始化")
    return LegalSourceIntakeService(db_session.SessionLocal)


def get_statute_version_chain_service() -> StatuteVersionChainService:
    if db_session.SessionLocal is None:
        raise HTTPException(status_code=503, detail="数据库服务未初始化")
    return StatuteVersionChainService(db_session.SessionLocal)


def _require_admin(context: AuthorizationContext) -> None:
    if not context.can("law_updates:manage"):
        raise HTTPException(status_code=403, detail="权限不足")


def _audit(
    service: LawUpdateService, context: AuthorizationContext, action: str, target_id: str
) -> None:
    try:
        AuditService(service.session_factory).append_event(
            event_id=str(uuid4()),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            action=action,
            target_type="law_update",
            target_id=target_id,
            status="success",
        )
    except Exception:
        pass


@router.get("/subscriptions")
def list_subscriptions(
    context: AuthorizationContext = Depends(get_authorization_context),
    service: LawUpdateService = Depends(get_law_update_service),
) -> dict:
    _require_admin(context)
    return {"items": service.list_subscriptions(organization_id=context.organization_id)}


@router.get("/local-sources")
def list_local_sources(
    context: AuthorizationContext = Depends(get_authorization_context),
    service: LegalSourceIntakeService = Depends(get_legal_source_intake_service),
) -> dict:
    """供管理员核验下载原件的版本、生效日、哈希和权威状态。"""
    _require_admin(context)
    return {"items": service.list_candidates()}


@router.post("/local-sources/{candidate_id}/verify")
def verify_local_source(
    candidate_id: int,
    request: LocalSourceVerificationRequest,
    context: AuthorizationContext = Depends(get_authorization_context),
    service: LegalSourceIntakeService = Depends(get_legal_source_intake_service),
) -> dict:
    """记录管理员对本地法规原件及官方出处的人工核验。"""
    _require_admin(context)
    try:
        return service.verify_candidate(
            candidate_id,
            authority_url=str(request.authority_url),
            reviewer_user_id=context.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/version-chains")
def list_version_chains(
    context: AuthorizationContext = Depends(get_authorization_context),
    service: StatuteVersionChainService = Depends(get_statute_version_chain_service),
) -> dict:
    _require_admin(context)
    return {"items": service.list_chains()}


@router.post("/version-chains", status_code=status.HTTP_201_CREATED)
def create_version_chain(
    request: VersionChainRequest,
    context: AuthorizationContext = Depends(get_authorization_context),
    service: StatuteVersionChainService = Depends(get_statute_version_chain_service),
) -> dict:
    _require_admin(context)
    try:
        return service.create_chain(
            law_slug=request.law_slug,
            target_version_id=request.target_version_id,
            effective_from=request.effective_from,
            effective_to=request.effective_to,
            consolidated_source_import_id=request.consolidated_source_import_id,
            members=[member.model_dump() for member in request.members],
        )
    except StatuteVersionChainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
def create_subscription(
    request: SubscriptionRequest,
    context: AuthorizationContext = Depends(get_authorization_context),
    service: LawUpdateService = Depends(get_law_update_service),
) -> dict:
    _require_admin(context)
    item = service.subscribe(
        organization_id=context.organization_id,
        law_name=request.law_name,
        source_url=str(request.source_url),
        knowledge_base_slug=request.knowledge_base_slug,
    )
    _audit(service, context, "law_subscription.created", str(item["id"]))
    return item


@router.post("/subscriptions/{subscription_id}/observe", status_code=status.HTTP_201_CREATED)
def observe_snapshot(
    subscription_id: int,
    request: SnapshotRequest,
    response: Response,
    context: AuthorizationContext = Depends(get_authorization_context),
    service: LawUpdateService = Depends(get_law_update_service),
) -> dict | None:
    _require_admin(context)
    try:
        event = service.observe(
            subscription_id=subscription_id,
            organization_id=context.organization_id,
            content=request.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if event is None:
        response.status_code = status.HTTP_204_NO_CONTENT
    else:
        _audit(service, context, "law_update.detected", str(event["id"]))
    return event


@router.post("/events/{event_id}/confirm")
def confirm_event(
    event_id: int,
    context: AuthorizationContext = Depends(get_authorization_context),
    service: LawUpdateService = Depends(get_law_update_service),
) -> dict:
    _require_admin(context)
    try:
        result = service.confirm(
            event_id=event_id,
            organization_id=context.organization_id,
            reviewer_user_id=context.user_id,
        )
        _audit(service, context, "law_update.confirmed", str(event_id))
        if result.get("knowledge_base_slug"):
            from app.tasks.law_update_tasks import rebuild_confirmed_law_version_task

            rebuild_confirmed_law_version_task.delay(event_id, context.organization_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
