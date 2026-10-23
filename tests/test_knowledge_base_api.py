"""知识库管理 API 的契约测试。"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import api
from app.services.knowledge_base_service import KnowledgeBaseBusyError
from src.ingestion.index_identity import (
    IndexIdentityError,
    IndexIdentityMismatchError,
    LegacyCollectionIdentityError,
)


class FakeKnowledgeBaseService:
    """避免 API 契约测试依赖 MySQL 和 Chroma。"""

    def list_knowledge_bases(self):
        return [
            {
                "id": "civil-code",
                "name": "中华人民共和国民法典",
                "slug": "civil-code",
                "type": "statute",
                "law_area": "civil",
                "collection_name": "kb_civil_code",
                "status": "READY",
                "document_count": 1260,
                "chunk_count": 1636,
                "last_indexed_at": "2026-08-02T00:00:00",
                "error_message": None,
            }
        ]

    def list_visible_knowledge_bases(self, *, organization_id):
        assert organization_id == 1
        return self.list_knowledge_bases()

    def get_visible_knowledge_base(self, slug, *, organization_id, require_owner=False):
        assert slug == "civil-code"
        assert organization_id == 1
        return self.list_knowledge_bases()[0]

    def create_knowledge_base(self, *, name, slug, law_area, organization_id):
        assert organization_id == 1
        return {
            "id": slug,
            "name": name,
            "slug": slug,
            "type": "statute",
            "law_area": law_area,
            "collection_name": f"kb_{slug.replace('-', '_')}",
            "status": "EMPTY",
            "document_count": 0,
            "chunk_count": 0,
            "last_indexed_at": None,
            "error_message": None,
        }

    def rebuild_knowledge_base(self, slug, *, content):
        assert slug == "civil-code"
        assert content == "民法典原文"
        return {
            **self.list_knowledge_bases()[0],
            "status": "READY",
            "document_count": 1260,
            "chunk_count": 1636,
        }

    def list_law_articles(self, slug, start_article=None, end_article=None):
        assert slug == "civil-code"
        assert start_article is None
        assert end_article is None
        return [{"id": "民法典第1条", "content": "为了保护民事主体的合法权益。"}]

    def delete_knowledge_base(self, slug):
        assert slug == "civil-code"


@pytest.fixture(autouse=True)
def authorized_knowledge_base_client():
    api.app.dependency_overrides[api.get_authorization_context] = lambda: SimpleNamespace(
        organization_id=1, can=lambda _permission: True
    )
    yield
    api.app.dependency_overrides.pop(api.get_authorization_context, None)


def test_list_knowledge_bases_returns_registered_libraries(monkeypatch):
    """知识库列表接口返回服务层注册的真实状态和统计。"""
    api.components["knowledge_base_service"] = FakeKnowledgeBaseService()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/knowledge-bases")

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "id": "civil-code",
            "name": "中华人民共和国民法典",
            "slug": "civil-code",
            "type": "statute",
            "law_area": "civil",
            "collection_name": "kb_civil_code",
            "status": "READY",
            "document_count": 1260,
            "chunk_count": 1636,
            "last_indexed_at": "2026-08-02T00:00:00",
            "error_message": None,
        }
    ]


def test_create_knowledge_base_registers_an_empty_statute_library():
    """创建法规库时，接口返回独立 collection 的空注册记录。"""
    api.components["knowledge_base_service"] = FakeKnowledgeBaseService()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/knowledge-bases",
                json={
                    "name": "中华人民共和国劳动合同法",
                    "slug": "labor-contract-law",
                    "law_area": "labor",
                },
            )

    response = asyncio.run(request())

    assert response.status_code == 201
    assert response.json()["collection_name"] == "kb_labor_contract_law"
    assert response.json()["status"] == "EMPTY"


def test_create_document_library_registers_an_empty_document_library():
    """文档解析中心必须创建 document 类型库，而不复用法规库入口。"""

    class DocumentLibraryService(FakeKnowledgeBaseService):
        def create_document_library(self, *, name, slug, law_area, organization_id):
            return {
                **self.create_knowledge_base(
                    name=name, slug=slug, law_area=law_area, organization_id=organization_id
                ),
                "type": "document",
            }

    api.components["knowledge_base_service"] = DocumentLibraryService()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/document-libraries",
                json={
                    "name": "劳动仲裁材料",
                    "slug": "labor-arbitration-materials",
                    "law_area": "labor",
                },
            )

    response = asyncio.run(request())

    assert response.status_code == 201
    assert response.json()["type"] == "document"


def test_rebuild_knowledge_base_returns_the_target_library_status():
    """重建接口只接收目标库的法条原文，并返回该库的新状态。"""
    api.components["knowledge_base_service"] = FakeKnowledgeBaseService()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/knowledge-bases/civil-code/rebuild",
                json={"content": "民法典原文"},
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json()["slug"] == "civil-code"
    assert response.json()["chunk_count"] == 1636


def test_rebuild_returns_conflict_when_the_library_is_already_indexing():
    """正在重建的知识库必须返回 409，供前端阻止重复操作。"""

    class BusyService(FakeKnowledgeBaseService):
        def rebuild_knowledge_base(self, slug, *, content):
            raise KnowledgeBaseBusyError(f"知识库正在重建: {slug}")

    api.components["knowledge_base_service"] = BusyService()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/knowledge-bases/civil-code/rebuild",
                json={"content": "民法典原文"},
            )

    response = asyncio.run(request())

    assert response.status_code == 409


def test_rebuild_returns_a_structured_conflict_when_existing_index_identity_is_legacy():
    """重建不能把旧 collection 身份问题伪装成成功或通用 500。"""

    class IdentityFailureService(FakeKnowledgeBaseService):
        def rebuild_knowledge_base(self, slug, *, content):
            raise LegacyCollectionIdentityError()

    api.components["knowledge_base_service"] = IdentityFailureService()

    with pytest.raises(HTTPException) as error:
        handler = api.rebuild_knowledge_base(
            slug="civil-code",
            request=api.KnowledgeBaseRebuildRequest(content="民法典原文"),
            authorization_context=SimpleNamespace(organization_id=1, can=lambda _permission: True),
        )
        handler.send(None)

    assert error.value.status_code == 409
    assert error.value.detail == {
        "code": "INDEX_IDENTITY_REBUILD_REQUIRED",
        "message": "知识库索引与当前嵌入配置不兼容，需要以新索引身份重新构建",
    }


def test_list_laws_returns_real_articles_for_the_selected_knowledge_base():
    api.components["knowledge_base_service"] = FakeKnowledgeBaseService()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/knowledge-bases/civil-code/laws")

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "民法典第1条"


def test_list_laws_passes_catalog_range_to_the_service():
    class RangeService(FakeKnowledgeBaseService):
        def list_law_articles(self, slug, start_article=None, end_article=None):
            assert slug == "civil-code"
            assert start_article == 463
            assert end_article == 988
            return [{"id": "民法典第463条", "article_number": 463, "content": "合同编"}]

    api.components["knowledge_base_service"] = RangeService()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(
                "/knowledge-bases/civil-code/laws?start_article=463&end_article=988"
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json()["items"][0]["article_number"] == 463


@pytest.mark.parametrize(
    "identity_error,expected_code",
    [
        (LegacyCollectionIdentityError(), "INDEX_IDENTITY_LEGACY_REBUILD_REQUIRED"),
        (IndexIdentityMismatchError(), "INDEX_IDENTITY_MISMATCH"),
        (IndexIdentityError("E:\\private\\chroma-metadata"), "INDEX_IDENTITY_REBUILD_REQUIRED"),
    ],
)
def test_list_laws_returns_a_safe_conflict_for_an_incompatible_collection(
    identity_error, expected_code
):
    """浏览接口用 409 表示 collection 需重建，且不能泄漏底层存储细节。"""

    class IdentityFailureService(FakeKnowledgeBaseService):
        def list_law_articles(self, _slug, start_article=None, end_article=None):
            raise identity_error

    api.components["knowledge_base_service"] = IdentityFailureService()

    with pytest.raises(HTTPException) as error:
        handler = api.list_knowledge_base_laws(
            slug="civil-code",
            authorization_context=SimpleNamespace(
                organization_id=1, can=lambda _permission: True
            )
        )
        handler.send(None)

    assert error.value.status_code == 409
    assert error.value.detail == {
        "code": expected_code,
        "message": "知识库索引与当前嵌入配置不兼容，请重建后重试",
    }


def test_delete_knowledge_base_returns_no_content():
    api.components["knowledge_base_service"] = FakeKnowledgeBaseService()

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.delete("/knowledge-bases/civil-code")

    response = asyncio.run(request())

    assert response.status_code == 204
