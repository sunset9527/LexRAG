"""FastAPI application factory and process-wide HTTP wiring."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.api.dashboard import router as dashboard_router
from app.api.documents import router as documents_router
from app.api.favorites import router as favorites_router
from app.api.graph import router as graph_router
from app.api.health import router as health_router
from app.api.intent import router as intent_router
from app.api.knowledge_bases import router as knowledge_bases_router
from app.api.law_updates import router as law_updates_router
from app.api.prompts import router as prompts_router
from app.api.queries import router as queries_router
from app.api.scenarios import router as scenarios_router
from app.api.sessions import router as sessions_router
from app.security.request_security import RequestSecurityMiddleware


def create_application(*, lifespan: Callable[..., Any]) -> FastAPI:
    """Build LexRAG's HTTP application without creating runtime services.

    Runtime services remain lifespan-owned so imports and API-schema generation
    cannot open databases, models, or vector collections.
    """

    app = FastAPI(
        title="LexRAG 法律智能知识平台 API",
        description="基于结构化RAG + 证据工作流 + 法条自校验的法律智能知识平台 API",
        version="3.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestSecurityMiddleware)
    app.mount("/metrics", make_asgi_app())

    for router in (
        auth_router,
        cases_router,
        admin_router,
        law_updates_router,
        prompts_router,
        queries_router,
        favorites_router,
        scenarios_router,
        sessions_router,
        health_router,
        intent_router,
        graph_router,
        dashboard_router,
        documents_router,
        knowledge_bases_router,
    ):
        app.include_router(router)
    return app
