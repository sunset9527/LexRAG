"""首页统计必须来自真实服务，而不是前端常量。"""

import asyncio

import httpx

import api


class FakeCaseService:
    def get_statistics(self):
        return {"case_count": 623, "source_count": 10}


def test_dashboard_stats_returns_persisted_case_counts(monkeypatch):
    api.components["case_ingestion_service"] = FakeCaseService()
    api.app.dependency_overrides[api.get_current_user] = lambda: object()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/dashboard/stats")

    try:
        response = asyncio.run(request())
    finally:
        api.app.dependency_overrides.pop(api.get_current_user, None)

    assert response.status_code == 200
    assert response.json() == {"case_count": 623, "source_count": 10}
