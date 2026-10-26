from __future__ import annotations

from types import SimpleNamespace

from app.api.knowledge_bases import list_knowledge_bases
from app.runtime import RuntimeContainer


class FakeKnowledgeBaseService:
    def list_visible_knowledge_bases(self, *, organization_id: int):
        assert organization_id == 7
        return [{"slug": "civil-code", "status": "READY"}]


def test_knowledge_base_router_reads_visible_libraries_from_runtime() -> None:
    response = list_knowledge_bases(
        authorization_context=SimpleNamespace(can=lambda permission: permission == "knowledge_bases:read", organization_id=7),
        runtime=RuntimeContainer(knowledge_base_service=FakeKnowledgeBaseService()),
    )

    assert response.model_dump() == {
        "items": [{"slug": "civil-code", "status": "READY"}],
    }
