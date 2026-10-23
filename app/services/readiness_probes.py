"""Concrete, read-only runtime probes used by the API readiness endpoint."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.services.readiness_service import ReadinessProbe
from src.graph.law_graph import LawGraph


@dataclass(frozen=True)
class RuntimeReadinessDependencies:
    """Injectable dependency surface so probes remain fast unit-test contracts."""

    session_factory: Callable[[], Any]
    alembic_head: Callable[[], str]
    redis_client_factory: Callable[[str], Any]
    redis_url: str
    embedding_loader: Callable[[], object]
    graph_checker: Callable[[], None]
    statute_checker: Callable[[], None]
    timeouts: Mapping[str, float] = field(default_factory=dict)


_DEFAULT_TIMEOUT_SECONDS = 3.0


def alembic_head_revision(project_root: Path) -> str:
    """Read the repository's single migration head without touching the database."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(project_root / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


def check_persisted_law_graph(graph_path: Path) -> None:
    """Fail closed unless the configured graph artifact is readable and useful.

    API request handling may deliberately retain an empty in-memory graph when a
    graph artifact is unavailable.  That compatibility fallback is not evidence
    that graph retrieval can serve production traffic, so readiness validates the
    persisted artifact independently.
    """
    if not graph_path.is_file():
        raise RuntimeError("GRAPH_ARTIFACT_MISSING")

    try:
        graph = LawGraph.from_json(str(graph_path))
        if graph.graph.number_of_nodes() == 0:
            raise ValueError("GRAPH_ARTIFACT_EMPTY")
    except Exception as exc:
        raise RuntimeError("GRAPH_ARTIFACT_INVALID") from exc


def build_runtime_checks(
    dependencies: RuntimeReadinessDependencies,
) -> dict[str, ReadinessProbe]:
    """Return the full, independently bounded production readiness contract."""

    def with_timeout(name: str, check: Callable[[], None]) -> ReadinessProbe:
        return ReadinessProbe(
            check=check,
            timeout_seconds=dependencies.timeouts.get(name, _DEFAULT_TIMEOUT_SECONDS),
        )

    def check_database() -> None:
        with dependencies.session_factory() as session:
            if session.execute(text("SELECT 1")).scalar_one() != 1:
                raise RuntimeError("DATABASE_CONNECTIVITY_FAILED")

    def check_migration() -> None:
        expected_head = dependencies.alembic_head()
        with dependencies.session_factory() as session:
            current_head = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if current_head != expected_head:
            raise RuntimeError("ALEMBIC_REVISION_MISMATCH")

    def check_redis() -> None:
        client = dependencies.redis_client_factory(dependencies.redis_url)
        if client.ping() is not True:
            raise RuntimeError("REDIS_PING_FAILED")

    def check_embedding() -> None:
        dependencies.embedding_loader()

    return {
        "database": with_timeout("database", check_database),
        "migration": with_timeout("migration", check_migration),
        "redis": with_timeout("redis", check_redis),
        "embedding": with_timeout("embedding", check_embedding),
        "graph": with_timeout("graph", dependencies.graph_checker),
        "statutes": with_timeout("statutes", dependencies.statute_checker),
    }
