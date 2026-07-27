"""
Prompt 管理 API 路由

端点：
- GET    /prompts          — 列出所有活跃 Prompt
- GET    /prompts/{name}   — 获取指定 Prompt 最新版本
- POST   /prompts          — 创建新 Prompt
- PUT    /prompts/{name}   — 更新 Prompt（版本递增）
- DELETE /prompts/{name}   — 删除 Prompt（软删除）
- GET    /prompts/{name}/history — 查看版本历史
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.services import prompt_service
from app.api.auth import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["Prompt 管理"])


# ========== 请求/响应模型 ==========

class PromptCreateRequest(BaseModel):
    """创建 Prompt 请求"""
    name: str = Field(..., min_length=1, max_length=128, description="Prompt 名称")
    content: str = Field(..., min_length=1, description="Prompt 内容")
    description: str | None = Field(None, max_length=512, description="描述")
    category: str | None = Field(None, max_length=64, description="分类")


class PromptUpdateRequest(BaseModel):
    """更新 Prompt 请求（版本递增）"""
    content: str = Field(..., min_length=1, description="新的 Prompt 内容")
    description: str | None = Field(None, max_length=512, description="描述")


class PromptResponse(BaseModel):
    """Prompt 响应"""
    id: int
    name: str
    content: str
    version: int
    description: str | None = None
    category: str | None = None
    is_active: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_orm_obj(cls, prompt) -> "PromptResponse":
        return cls(
            id=prompt.id,
            name=prompt.name,
            content=prompt.content,
            version=prompt.version,
            description=prompt.description,
            category=prompt.category,
            is_active=prompt.is_active,
            created_at=prompt.created_at.isoformat() if prompt.created_at else "",
            updated_at=prompt.updated_at.isoformat() if prompt.updated_at else "",
        )


class PromptListResponse(BaseModel):
    """Prompt 列表响应"""
    total: int
    prompts: list[PromptResponse]


class MessageResponse(BaseModel):
    message: str


# ========== 端点 ==========

@router.get("", response_model=PromptListResponse, summary="列出所有活跃 Prompt")
def list_prompts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回所有活跃 Prompt 模板（每个 name 返回最新版本）"""
    prompts = prompt_service.get_all_active_prompts(db)
    return PromptListResponse(
        total=len(prompts),
        prompts=[PromptResponse.from_orm_obj(p) for p in prompts],
    )


@router.get("/{name}", response_model=PromptResponse, summary="获取 Prompt 详情")
def get_prompt(
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按名称获取 Prompt 的最新活跃版本"""
    prompt = prompt_service.get_prompt_by_name(db, name)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt '{name}' 不存在",
        )
    return PromptResponse.from_orm_obj(prompt)


@router.post(
    "", response_model=PromptResponse, status_code=status.HTTP_201_CREATED,
    summary="创建新 Prompt"
)
def create_prompt(
    request: PromptCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新的 Prompt 模板，版本号从 1 开始"""
    try:
        prompt = prompt_service.create_prompt(
            db,
            name=request.name,
            content=request.content,
            description=request.description,
            category=request.category,
        )
        return PromptResponse.from_orm_obj(prompt)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.put("/{name}", response_model=PromptResponse, summary="更新 Prompt")
def update_prompt(
    name: str,
    request: PromptUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新 Prompt 内容，版本号自动 +1

    旧版本标记为 inactive，新版本立即生效（热加载）
    """
    try:
        prompt = prompt_service.update_prompt(
            db,
            name=name,
            content=request.content,
            description=request.description,
        )
        return PromptResponse.from_orm_obj(prompt)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete("/{name}", response_model=MessageResponse, summary="删除 Prompt")
def delete_prompt(
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """软删除 Prompt（标记为 inactive，可恢复）"""
    success = prompt_service.delete_prompt(db, name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt '{name}' 不存在",
        )
    return MessageResponse(message=f"Prompt '{name}' 已删除")


@router.get("/{name}/history", summary="查看 Prompt 版本历史")
def get_prompt_history(
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回指定 Prompt 的所有历史版本（包括 inactive）"""
    versions = prompt_service.get_prompt_history(db, name)
    if not versions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt '{name}' 不存在",
        )
    return {
        "name": name,
        "total_versions": len(versions),
        "versions": [PromptResponse.from_orm_obj(v) for v in versions],
    }
