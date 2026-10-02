"""收藏 API 的登录用户隔离契约。"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.api import favorites


class FakeFavoriteService:
    def __init__(self):
        self.created = None

    def create(self, **kwargs):
        self.created = kwargs
        return {"id": 1, **kwargs}

    def list_for_user(self, **kwargs):
        return [{"id": 1, "user_id": kwargs["user_id"]}]

    def delete(self, **kwargs):
        return kwargs["user_id"] == 7 and kwargs["favorite_id"] == 1


def test_favorite_routes_use_authenticated_user_not_request_user_id(monkeypatch):
    """API 从 JWT 依赖取用户，客户端无法伪造收藏归属。"""
    fake_service = FakeFavoriteService()
    app = FastAPI()
    app.include_router(favorites.router)
    app.dependency_overrides[favorites.get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[favorites.get_authorization_context] = lambda: SimpleNamespace(organization_id=1)
    monkeypatch.setattr(favorites, "_service", lambda: fake_service)

    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/favorites",
                json={
                    "question": "成年人多大",
                    "answer": "十八周岁",
                    "citations": [],
                    "knowledge_base_slug": "civil-code",
                    "law_area": "民法",
                },
            )
            listed = await client.get("/favorites?law_area=民法")
            deleted = await client.delete("/favorites/1")
            return created, listed, deleted

    created, listed, deleted = asyncio.run(request())

    assert created.status_code == 201
    assert fake_service.created["user_id"] == 7
    assert listed.json()["items"] == [{"id": 1, "user_id": 7}]
    assert deleted.status_code == 204
