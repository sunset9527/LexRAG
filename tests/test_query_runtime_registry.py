"""阶段 6 只读检索运行时复用契约。"""

from types import SimpleNamespace

from app.api.knowledge_bases import rebuild_knowledge_base
from app.runtime import RuntimeContainer
from app.schemas.knowledge_bases import KnowledgeBaseRebuildRequest
from app.services.query_runtime_registry import QueryRuntimeRegistry


def test_registry_reuses_one_runtime_per_collection_and_invalidates_only_that_collection():
    registry = QueryRuntimeRegistry()
    built = []

    first = registry.get_or_create("kb_civil_code_v1", lambda: built.append("v1") or object())
    again = registry.get_or_create("kb_civil_code_v1", lambda: built.append("unexpected") or object())
    other = registry.get_or_create("kb_criminal_code_v1", lambda: built.append("criminal") or object())

    registry.invalidate("kb_civil_code_v1")
    refreshed = registry.get_or_create("kb_civil_code_v1", lambda: built.append("v1-refresh") or object())

    assert first is again
    assert other is not first
    assert refreshed is not first
    assert built == ["v1", "criminal", "v1-refresh"]


def test_registry_reuses_one_chroma_client_for_multiple_collections():
    registry = QueryRuntimeRegistry()
    built = []

    first = registry.get_or_create_chroma_client("C:/indexes", lambda: built.append("client") or object())
    again = registry.get_or_create_chroma_client("C:/indexes", lambda: built.append("unexpected") or object())

    assert first is again
    assert built == ["client"]


def test_rebuild_invalidates_only_its_collection_runtime(monkeypatch):
    invalidated = []

    class KnowledgeBaseService:
        def get_visible_knowledge_base(self, slug, *, organization_id, require_owner):
            assert (slug, organization_id, require_owner) == ("civil-code", 9, True)
            return {"slug": slug}

        def rebuild_knowledge_base(self, slug, *, content):
            assert (slug, content) == ("civil-code", "第一条")
            return {"collection_name": "kb_civil_code"}

    runtime = RuntimeContainer(
        knowledge_base_service=KnowledgeBaseService(),
        query_runtime_registry=SimpleNamespace(invalidate=invalidated.append),
    )

    result = rebuild_knowledge_base(
        "civil-code",
        KnowledgeBaseRebuildRequest(content="第一条"),
        SimpleNamespace(organization_id=9, can=lambda permission: permission == "knowledge_bases:manage"),
        runtime,
    )

    assert result == {"collection_name": "kb_civil_code"}
    assert invalidated == ["kb_civil_code"]
