"""
数据库会话管理

支持 SQLite（开发）和 PostgreSQL + pgvector（生产）自动切换
"""

import logging
from typing import Generator

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings

logger = logging.getLogger(__name__)

# 模块级引擎和会话工厂
_engine: Engine = None
SessionLocal: sessionmaker = None


def get_database_url() -> str:
    """
    根据配置返回数据库连接 URL

    优先 DATABASE_URL 环境变量，否则使用 MySQL 配置
    """
    if settings.database_url:
        return settings.database_url
    return (
        f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
        f"?charset=utf8mb4"
    )


def create_engine_instance() -> Engine:
    """创建 SQLAlchemy 引擎"""
    url = get_database_url()

    engine = create_engine(
        url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
    )

    logger.info(f"数据库引擎已创建: MySQL")
    return engine


def init_db():
    """
    初始化数据库连接

    在应用启动时调用，创建引擎和会话工厂
    """
    global _engine, SessionLocal

    _engine = create_engine_instance()
    SessionLocal = sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    # 自动创建所有表（开发便利，生产应使用 Alembic 迁移）
    from app.db.base import Base
    Base.metadata.create_all(bind=_engine)

    logger.info("数据库初始化完成，所有表已就绪")


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话（FastAPI Depends 使用）

    用法：
        @app.get("/users/me")
        def get_current_user(db: Session = Depends(get_db)):
            ...

    每次请求自动创建会话，请求结束后自动关闭
    """
    if SessionLocal is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_engine() -> Engine:
    """获取当前数据库引擎（供 LangGraph Checkpointer 等使用）"""
    if _engine is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    return _engine
