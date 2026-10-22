"""文档深度解析结果 API 契约测试。"""

import asyncio
import io
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import api


def _minimal_pdf() -> bytes:
    return b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF"


def _minimal_docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<w:document />")
    return buffer.getvalue()


class FakeDocumentResultService:
    def __init__(self):
        self.calls = []

    def get_result(self, document_id):
        self.calls.append(("result", document_id))
        return {"id": document_id, "page_count": 2, "storage_path": None}

    def get_knowledge_base_slug(self, document_id):
        return "contracts"

    def list_pages(self, document_id, *, page, page_size):
        self.calls.append(("pages", document_id, page, page_size))
        return {"total": 2, "page": page, "page_size": page_size, "items": []}

    def list_relations(self, document_id):
        self.calls.append(("relations", document_id))
        return {"items": [{"target_id": "civil-code:509"}]}


class FakeDocumentIngestionService:
    def __init__(self):
        self.calls = []

    def submit_documents(self, **kwargs):
        self.calls.append(kwargs)
        return [
            {"original_filename": item["original_filename"], "job": {"id": f"job-{index}"}}
            for index, item in enumerate(kwargs["submissions"])
        ]


def test_batch_document_route_delegates_all_files_once_and_returns_independent_items():
    """批量路由将文件逐项交给服务，并返回逐文件结果而非全批事务。"""
    service = FakeDocumentIngestionService()
    api.components["document_ingestion_service"] = service
    api.components["knowledge_base_service"] = SimpleNamespace(
        get_visible_knowledge_base=lambda slug, **_kwargs: {"slug": slug}
    )
    api.app.dependency_overrides[api.get_authorization_context] = lambda: SimpleNamespace(
        organization_id=1, can=lambda _permission: True
    )

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/document-libraries/contracts/documents/batch",
                data={"chunk_size": "900", "chunk_overlap": "100"},
                files=[
                    ("files", ("one.pdf", _minimal_pdf(), "application/pdf")),
                    (
                        "files",
                        (
                            "two.docx",
                            _minimal_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        ),
                    ),
                ],
            )

    try:
        response = asyncio.run(request())
    finally:
        api.app.dependency_overrides.pop(api.get_authorization_context, None)

    assert response.status_code == 202
    assert [item["original_filename"] for item in response.json()["items"]] == [
        "one.pdf",
        "two.docx",
    ]
    assert len(service.calls) == 1
    assert service.calls[0]["knowledge_base_slug"] == "contracts"
    assert service.calls[0]["chunk_size"] == 900
    assert [item["original_filename"] for item in service.calls[0]["submissions"]] == [
        "one.pdf",
        "two.docx",
    ]
    assert all(not item["source_path"].exists() for item in service.calls[0]["submissions"])


def test_document_result_routes_delegate_to_result_service_without_starting_worker():
    """结果端点应只调用结果服务，并传透分页参数。"""
    service = FakeDocumentResultService()
    api.components["document_result_service"] = service
    api.components["knowledge_base_service"] = SimpleNamespace(
        get_visible_knowledge_base=lambda slug, **_kwargs: {"slug": slug}
    )
    api.app.dependency_overrides[api.get_authorization_context] = lambda: SimpleNamespace(
        organization_id=1, can=lambda _permission: True
    )

    async def request():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            result = await client.get("/documents/document-1/result")
            pages = await client.get(
                "/documents/document-1/pages", params={"page": 2, "page_size": 10}
            )
            relations = await client.get("/documents/document-1/relations")
            return result, pages, relations

    try:
        result, pages, relations = asyncio.run(request())
    finally:
        api.app.dependency_overrides.pop(api.get_authorization_context, None)

    assert result.status_code == 200
    assert result.json()["id"] == "document-1"
    assert pages.status_code == 200
    assert pages.json()["page"] == 2
    assert relations.status_code == 200
    assert relations.json()["items"][0]["target_id"] == "civil-code:509"
    assert service.calls == [
        ("result", "document-1"),
        ("pages", "document-1", 2, 10),
        ("relations", "document-1"),
    ]
