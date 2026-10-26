from __future__ import annotations

from types import SimpleNamespace

from app.api.documents import create_document_library
from app.runtime import RuntimeContainer
from app.schemas.knowledge_bases import KnowledgeBaseCreateRequest


class FakeKnowledgeBaseService:
    def create_document_library(self, **kwargs):
        return {"type": "document", **kwargs}


def test_document_router_creates_an_organization_owned_library() -> None:
    response = create_document_library(
        request=KnowledgeBaseCreateRequest(
            name="劳动仲裁材料", slug="labor-arbitration", law_area="labor"
        ),
        authorization_context=SimpleNamespace(
            organization_id=7, can=lambda permission: permission == "knowledge_bases:manage"
        ),
        runtime=RuntimeContainer(knowledge_base_service=FakeKnowledgeBaseService()),
    )

    assert response == {
        "type": "document",
        "name": "劳动仲裁材料",
        "slug": "labor-arbitration",
        "law_area": "labor",
        "organization_id": 7,
    }
