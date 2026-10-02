"""登录用户的会话管理与可解释推荐 API。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.api.admin import get_authorization_context
from app.db import session as db_session
from app.models.user import User
from app.services.session_service import SessionNotFoundError, SessionService
from app.services.authorization_service import AuthorizationContext


router = APIRouter(tags=["会话"])


class SessionCreateRequest(BaseModel):
    initial_question: str | None = Field(default=None, max_length=2000)


class SessionRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


def _service() -> SessionService:
    if db_session.SessionLocal is None:
        raise HTTPException(status_code=503, detail="数据库服务未初始化")
    return SessionService(db_session.SessionLocal)


def _not_found(exc: SessionNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail="会话不存在或不可用")


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(
    request: SessionCreateRequest,
    current_user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict[str, Any]:
    return _service().create(user_id=current_user.id, organization_id=context.organization_id, initial_question=request.initial_question)


@router.get("/sessions")
def list_sessions(
    q: str | None = Query(default=None, max_length=120),
    current_user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict[str, Any]:
    return {"items": _service().list_for_user(user_id=current_user.id, organization_id=context.organization_id, query=q)}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, current_user: User = Depends(get_current_user), context: AuthorizationContext = Depends(get_authorization_context)) -> dict[str, Any]:
    try:
        return _service().get_for_user(user_id=current_user.id, organization_id=context.organization_id, session_id=session_id)
    except SessionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.patch("/sessions/{session_id}")
def rename_session(
    session_id: str,
    request: SessionRenameRequest,
    current_user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
) -> dict[str, Any]:
    try:
        return _service().rename(user_id=current_user.id, organization_id=context.organization_id, session_id=session_id, title=request.title)
    except SessionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_session(session_id: str, current_user: User = Depends(get_current_user), context: AuthorizationContext = Depends(get_authorization_context)) -> None:
    try:
        _service().archive(user_id=current_user.id, organization_id=context.organization_id, session_id=session_id)
    except SessionNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/recommendations")
def get_recommendations(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return _service().get_recommendations(user_id=current_user.id)
