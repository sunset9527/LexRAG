from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.main import create_application


@asynccontextmanager
async def empty_lifespan(_app: FastAPI):
    yield


def test_application_factory_registers_platform_and_health_routers() -> None:
    app = create_application(lifespan=empty_lifespan)

    paths = [route.path for route in app.routes if getattr(route, "path", None)]
    paths.extend(
        child.path
        for route in app.routes
        if hasattr(route, "original_router")
        for child in route.original_router.routes
        if getattr(child, "path", None)
    )

    assert app.title == "LexRAG 法律智能知识平台 API"
    assert {
        "/health",
        "/intent/{intent_type}",
        "/auth/login",
        "/cases",
        "/admin/organization",
        "/dashboard/stats",
        "/document-libraries",
        "/knowledge-bases",
        "/query",
        "/query-runs",
        "/upload",
        "/sessions",
    } <= set(paths)
    assert "/graph" not in paths
    assert "/graph/query" not in paths


def test_api_module_uses_the_application_factory() -> None:
    source = (Path(__file__).parent.parent / "api.py").read_text(encoding="utf-8")

    assert "app = create_application(lifespan=lifespan)" in source
