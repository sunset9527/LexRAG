"""
SQLAlchemy 声明式基类

所有数据模型继承自此 Base
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类"""
    pass
