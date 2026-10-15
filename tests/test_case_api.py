"""案例库 API 契约测试。"""

import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import api


class FakeCaseService:
    def list_cases(self, *, domain=None, case_cause=None, source_id=None):
        assert domain == "labor"
        assert case_cause == "确认劳动关系纠纷"
        assert source_id is None
        return [
            {
                "id": "case-1",
                "domain": "labor",
                "case_cause": "确认劳动关系纠纷",
                "title": "某甲诉某公司劳动争议案",
            }
        ]

    def list_sources(self, *, domain=None):
        assert domain == "labor"
        return [{"id": 1, "domain": "labor", "status": "OCR_RUNNING", "processed_pages": 20}]

    def get_case(self, case_id):
        assert case_id == "case-1"
        return {"id": case_id, "source_start_page": 14, "source_end_page": 16}


class FakeSimilarCaseRetriever:
    def similar_cases(self, case_id, *, top_k):
        assert case_id == "case-1"
        assert top_k == 3
        return [{"id": "case-2", "similarity_score": 0.91, "case_cause_match": True}]


def test_list_cases_filters_independent_case_library():
    """案例列表使用独立服务，并将领域和案由条件传透。"""
    api.components["case_ingestion_service"] = FakeCaseService()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/cases?domain=labor&case_cause=确认劳动关系纠纷")

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "case-1"


def test_get_case_sources_and_detail_keep_progress_and_page_traceability():
    """案例页面可独立展示来源进度，并打开可回溯的单案详情。"""
    api.components["case_ingestion_service"] = FakeCaseService()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            source_response = await client.get("/case-sources?domain=labor")
            detail_response = await client.get("/cases/case-1")
            return source_response, detail_response

    source_response, detail_response = asyncio.run(request())

    assert source_response.status_code == 200
    assert source_response.json()["items"][0]["processed_pages"] == 20
    assert detail_response.status_code == 200
    assert detail_response.json()["source_start_page"] == 14


def test_similar_cases_uses_the_annual_case_retriever_only():
    api.components["annual_case_retriever"] = FakeSimilarCaseRetriever()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/cases/case-1/similar?top_k=3")

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json()["items"][0]["case_cause_match"] is True
