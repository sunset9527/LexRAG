"""
认证服务

JWT 令牌生成/验证 + 密码哈希/校验
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
import bcrypt
from sqlalchemy.orm import Session

from config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

# JWT 算法
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """对密码进行 bcrypt 哈希"""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希值匹配"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    生成 JWT 访问令牌

    Args:
        data: 要编码的 payload（至少包含 "sub" 字段）
        expires_delta: 过期时间增量，默认使用配置值

    Returns:
        JWT 令牌字符串
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta
        if expires_delta
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    encoded_jwt = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """
    解码 JWT 令牌

    Args:
        token: JWT 令牌字符串

    Returns:
        解码后的 payload 字典，失败返回 None
    """
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[ALGORITHM]
        )
        return payload
    except JWTError as e:
        logger.warning(f"JWT 解码失败: {e}")
        return None


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """根据用户名查询用户"""
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """根据 ID 查询用户"""
    return db.query(User).filter(User.id == user_id).first()


def create_user(
    db: Session,
    username: str,
    password: str,
    email: Optional[str] = None,
) -> User:
    """
    创建新用户

    Args:
        db: 数据库会话
        username: 用户名
        password: 明文密码
        email: 邮箱（可选）

    Returns:
        新创建的 User 对象

    Raises:
        ValueError: 用户名已存在
    """
    # 检查用户名唯一性
    existing = get_user_by_username(db, username)
    if existing:
        raise ValueError(f"用户名 '{username}' 已被注册")

    user = User(
        username=username,
        hashed_password=hash_password(password),
        email=email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"用户已创建: {username}")
    return user


def authenticate_user(
    db: Session, username: str, password: str
) -> Optional[User]:
    """
    认证用户

    Args:
        db: 数据库会话
        username: 用户名
        password: 明文密码

    Returns:
        认证成功返回 User 对象，失败返回 None
    """
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
