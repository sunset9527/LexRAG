"""用户收藏服务的边界测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.user  # noqa: F401
import app.services as services
from app.db.base import Base


def test_favorite_service_is_exposed_separately_from_query_routes():
    """收藏持久化和授权规则必须收敛到服务层。"""
    assert hasattr(services, "FavoriteService")


def test_favorites_are_idempotent_and_isolated_by_user():
    """重复收藏不产生副本，用户只能读取和删除自己的收藏。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    service = services.FavoriteService(sessionmaker(bind=engine, expire_on_commit=False))

    first = service.create(
        user_id=1,
        question="成年人多大",
        answer="年满十八周岁的自然人为成年人。",
        citations=[{"article_id": "中华人民共和国民法典第17条"}],
        knowledge_base_slug="civil-code",
        law_area="民法",
    )
    duplicate = service.create(
        user_id=1,
        question="成年人多大",
        answer="年满十八周岁的自然人为成年人。",
        citations=[{"article_id": "中华人民共和国民法典第17条"}],
        knowledge_base_slug="civil-code",
        law_area="民法",
    )

    assert duplicate["id"] == first["id"]
    assert [item["id"] for item in service.list_for_user(user_id=1)] == [first["id"]]
    assert service.list_for_user(user_id=2) == []
    assert service.delete(user_id=2, favorite_id=first["id"]) is False
    assert service.delete(user_id=1, favorite_id=first["id"]) is True
