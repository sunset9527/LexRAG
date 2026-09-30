"""当前登录用户的法律问答收藏 API。"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.db import session as db_session
from app.models.user import User
from app.services.favorite_service import FavoriteService


router = APIRouter(prefix="/favorites", tags=["收藏"])


class FavoriteCreateRequest(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_base_slug: Optional[str] = Field(None, max_length=128)
    law_area: Optional[str] = Field(None, max_length=64)


def _service() -> FavoriteService:
    if db_session.SessionLocal is None:
        raise HTTPException(status_code=503, detail="数据库服务未初始化")
    return FavoriteService(db_session.SessionLocal)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_favorite(
    request: FavoriteCreateRequest,
    current_user: User = Depends(get_current_user),
):
    return _service().create(user_id=current_user.id, **request.model_dump())


@router.get("")
def list_favorites(
    law_area: Optional[str] = Query(default=None),
    knowledge_base_slug: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    return {
        "items": _service().list_for_user(
            user_id=current_user.id,
            law_area=law_area,
            knowledge_base_slug=knowledge_base_slug,
        )
    }


@router.delete("/{favorite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_favorite(
    favorite_id: int,
    current_user: User = Depends(get_current_user),
):
    if not _service().delete(user_id=current_user.id, favorite_id=favorite_id):
        raise HTTPException(status_code=404, detail="收藏不存在")
