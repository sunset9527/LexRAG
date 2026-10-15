"""会话 API 必须从 JWT 依赖取得用户身份。"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    from app.api import sessions
except ImportError:
    sessions = None


class FakeSessionService:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return {
            "id": "session-1",
            "user_id": kwargs["user_id"],
            "title": "新法律咨询",
            "is_active": True,
        }

    def list_for_user(self, **kwargs):
        self.calls.append(("list", kwargs))
        return []

    def get_for_user(self, **kwargs):
        self.calls.append(("get", kwargs))
        return {"id": kwargs["session_id"], "messages": []}

    def rename(self, **kwargs):
        self.calls.append(("rename", kwargs))
        return {"id": kwargs["session_id"], "title": kwargs["title"]}

    def archive(self, **kwargs):
        self.calls.append(("archive", kwargs))
        return True

    def get_recommendations(self, **kwargs):
        self.calls.append(("recommendations", kwargs))
        return {"based_on_law_area": "civil-code", "items": []}


def test_session_routes_take_user_identity_from_auth_dependency(monkeypatch):
    assert sessions is not None, "v2.4 应提供 sessions 路由模块"
    fake_service = FakeSessionService()
    app = FastAPI()
    app.include_router(sessions.router)
    app.dependency_overrides[sessions.get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[sessions.get_authorization_context] = lambda: SimpleNamespace(
        organization_id=1
    )
    monkeypatch.setattr(sessions, "_service", lambda: fake_service)

    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/sessions", json={"initial_question": "劳动合同"})
            listed = await client.get("/sessions?q=劳动")
            detail = await client.get("/sessions/session-1")
            renamed = await client.patch("/sessions/session-1", json={"title": "劳动合同咨询"})
            archived = await client.delete("/sessions/session-1")
            recommended = await client.get("/recommendations")
            return created, listed, detail, renamed, archived, recommended

    responses = asyncio.run(request())

    assert [response.status_code for response in responses] == [201, 200, 200, 200, 204, 200]
    assert all(call[1]["user_id"] == 7 for call in fake_service.calls)
    assert responses[-1].json()["based_on_law_area"] == "civil-code"


def test_application_registers_session_routes():
    import api

    paths = set(api.app.openapi()["paths"])

    assert "/sessions" in paths
    assert "/recommendations" in paths
