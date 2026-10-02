"""
认证 API 路由

端点：
- POST /auth/register — 注册
- POST /auth/login — 登录（返回 JWT）
- GET  /auth/me — 获取当前用户信息
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.db import session as db_session
from app.services import auth_service
from app.services.authorization_service import AuthorizationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["认证"])

# OAuth2 Password Bearer 令牌提取
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ========== 请求/响应模型 ==========

class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=3, max_length=64, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    email: str | None = Field(None, max_length=128, description="邮箱（可选）")


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class TokenResponse(BaseModel):
    """令牌响应"""
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field("bearer", description="令牌类型")
    username: str = Field(..., description="用户名")
    user_id: int = Field(..., description="用户 ID")


class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    username: str
    email: str | None = None
    is_active: bool
    is_superuser: bool


class MessageResponse(BaseModel):
    """通用消息响应"""
    message: str


# ========== 认证依赖注入 ==========

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> auth_service.User:
    """
    从 JWT 令牌中提取当前用户

    用作受保护端点的 Depends 依赖：
        @router.get("/me")
        def me(current_user: User = Depends(get_current_user)):
            ...
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = auth_service.decode_access_token(token)
    if payload is None:
        raise credentials_exception

    username: str | None = payload.get("sub")
    if username is None:
        raise credentials_exception

    user = auth_service.get_user_by_username(db, username)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="用户已被停用")

    return user


# ========== 端点 ==========

@router.post("/register", response_model=TokenResponse, summary="用户注册")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """
    注册新用户

    - **username**: 3-64 字符，唯一
    - **password**: 至少 6 字符
    - **email**: 可选

    注册成功直接返回 JWT 令牌
    """
    try:
        user = auth_service.create_user(
            db,
            username=request.username,
            password=request.password,
            email=request.email,
        )
        # v3 本机演示必须把新用户放入真实组织成员关系；首位用户仅作为初始管理员。
        if db_session.SessionLocal is None:
            raise RuntimeError("数据库服务未初始化")
        AuthorizationService(db_session.SessionLocal).enroll_new_local_user(user_id=user.id)
        # 注册即登录，生成令牌
        token = auth_service.create_access_token(
            data={"sub": user.username, "user_id": user.id}
        )
        return TokenResponse(
            access_token=token,
            username=user.username,
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"注册失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="注册失败，请稍后重试",
        )


@router.post("/login", response_model=TokenResponse, summary="用户登录")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    用户名 + 密码登录，返回 JWT 访问令牌

    令牌有效期为配置的 `jwt_access_token_expire_minutes` 分钟
    """
    user = auth_service.authenticate_user(
        db,
        username=request.username,
        password=request.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    token = auth_service.create_access_token(
        data={"sub": user.username, "user_id": user.id}
    )
    return TokenResponse(
        access_token=token,
        username=user.username,
        user_id=user.id,
    )


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
def get_me(
    current_user: auth_service.User = Depends(get_current_user),
):
    """返回当前登录用户的个人信息"""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
    )
