from __future__ import annotations

from app.api.health import health_check, health_live, health_ready, root
from app.runtime import RuntimeContainer
from app.services.readiness_service import ReadinessService


def test_health_router_reports_runtime_status_with_utc_timestamp() -> None:
    payload = health_check(
        RuntimeContainer(workflow=object(), law_indexer=None, law_graph=object())
    )

    assert payload.status == "healthy"
    assert payload.components == {
        "workflow": "ready",
        "law_indexer": "not_ready",
        "law_graph": "ready",
    }
    assert payload.timestamp.endswith("+00:00")


def test_health_live_and_root_keep_existing_public_contract() -> None:
    assert health_live() == {"status": "alive"}
    assert root() == {
        "message": "LexRAG 法律智能知识平台 API",
        "version": "3.0.0",
        "docs": "/docs",
    }


def test_health_ready_returns_typed_readiness_payload() -> None:
    runtime = RuntimeContainer(readiness_service=ReadinessService({"database": lambda: None}))

    assert health_ready(runtime).model_dump() == {
        "status": "ready",
        "components": {"database": "ready"},
    }


def test_application_registers_the_extracted_health_router() -> None:
    import api

    routes = [route for route in api.app.routes if getattr(route, "path", None)]
    routes.extend(
        child
        for route in api.app.routes
        if hasattr(route, "original_router")
        for child in route.original_router.routes
        if getattr(child, "path", None)
    )
    health_route = next(route for route in routes if route.path == "/health")

    assert health_route.endpoint.__module__ == "app.api.health"
