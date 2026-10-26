from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from app.api.dependencies import get_runtime
from app.runtime import RuntimeComponentUnavailable, RuntimeContainer


def test_runtime_container_returns_registered_component() -> None:
    query_service = object()

    runtime = RuntimeContainer(query_service=query_service)

    assert runtime.require("query_service") is query_service


def test_runtime_container_rejects_missing_component_with_stable_code() -> None:
    runtime = RuntimeContainer()

    with pytest.raises(RuntimeComponentUnavailable) as exc_info:
        runtime.require("query_service")

    assert exc_info.value.component == "query_service"
    assert exc_info.value.code == "RUNTIME_COMPONENT_UNAVAILABLE"


def test_runtime_container_supports_a_compatibility_registration_during_migration() -> None:
    runtime = RuntimeContainer()

    runtime.register("query_service", "ready")

    assert runtime.require("query_service") == "ready"


def test_runtime_container_keeps_legacy_mapping_access_temporarily() -> None:
    runtime = RuntimeContainer()

    runtime["query_service"] = "ready"

    assert runtime["query_service"] == "ready"


def test_runtime_container_replaces_startup_components_without_changing_identity() -> None:
    runtime = RuntimeContainer(workflow="old")
    shared_reference = runtime

    runtime.replace(workflow="new", graph="ready")

    assert runtime is shared_reference
    assert shared_reference.require("workflow") == "new"
    assert shared_reference.require("graph") == "ready"


def test_runtime_dependency_reads_container_from_the_application_state() -> None:
    app = FastAPI()
    app.state.runtime = RuntimeContainer(query_service="ready")

    request = Request({"type": "http", "app": app})

    runtime = get_runtime(request)

    assert runtime.require("query_service") == "ready"
