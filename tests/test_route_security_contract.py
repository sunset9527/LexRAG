"""Static API route security contracts that do not require an ASGI socket."""

import inspect

import api
from app.api import documents as document_api
from app.api import knowledge_bases as knowledge_base_api
from app.api import prompts as prompt_api


def _route(path: str, method: str):
    for route in api.app.routes:
        nested_router = getattr(route, "original_router", None)
        candidates = nested_router.routes if nested_router is not None else [route]
        for candidate in candidates:
            if getattr(candidate, "path", None) == path and method in getattr(candidate, "methods", set()):
                return candidate
    raise LookupError(f"route not found: {method} {path}")


def _dependency_calls(route) -> set[object]:
    return {dependency.call for dependency in route.dependant.dependencies}


def test_case_routes_require_authorization_context():
    for path, method in [
        ("/cases", "GET"),
        ("/case-sources", "GET"),
        ("/cases/{case_id}", "GET"),
        ("/cases/{case_id}/similar", "GET"),
    ]:
        calls = _dependency_calls(_route(path, method))
        assert api.get_authorization_context in calls, f"{method} {path} is not authorization scoped"


def test_legacy_verification_registry_and_endpoint_are_removed():
    assert not hasattr(api, "query_results")
    assert not any(getattr(route, "path", None) == "/verify/{query_id}" for route in api.app.routes)


def test_statute_upload_requires_owned_target_knowledge_base():
    route = _route("/upload", "POST")
    assert api.get_authorization_context in _dependency_calls(route)
    assert "knowledge_base_slug" in api.UploadRequest.model_fields


def test_sensitive_document_mutations_append_redacted_audit_events():
    for endpoint in (
        document_api.upload_document,
        document_api.upload_documents,
        document_api.retry_document,
    ):
        source = inspect.getsource(endpoint)
        assert "_append_audit_event(" in source
    assert "_append_rebuild_audit(" in inspect.getsource(knowledge_base_api.upload_law)


def test_prompt_mutations_append_organization_scoped_audit_events():
    for endpoint in (
        prompt_api.create_prompt,
        prompt_api.update_prompt,
        prompt_api.delete_prompt,
    ):
        assert "_audit_prompt_mutation(" in inspect.getsource(endpoint)
