from __future__ import annotations

from types import SimpleNamespace

from app.api.knowledge_bases import list_knowledge_bases
from app.runtime import RuntimeContainer
from src.retrieval.knowledge_base_router import KnowledgeBaseRouter


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


def test_knowledge_base_router_routes_adult_age_question_to_civil_code() -> None:
    decision = KnowledgeBaseRouter().route(
        "成年人是指年满多少周岁？",
        [{"slug": "civil-code"}, {"slug": "criminal-law"}],
    )

    assert decision.mode == "automatic"
    assert decision.selected_slugs == ["civil-code"]
