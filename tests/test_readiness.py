"""Stage 3 readiness contracts independent from FastAPI startup."""

import ast
import time
from pathlib import Path

from app.services.readiness_service import ReadinessProbe, ReadinessService


def test_readiness_is_ready_only_when_every_required_check_passes() -> None:
    service = ReadinessService(
        {
            "database": lambda: None,
            "migration": lambda: None,
            "catalog": lambda: None,
        }
    )

    report = service.check()

    assert report.ready is True
    assert report.components == {
        "database": "ready",
        "migration": "ready",
        "catalog": "ready",
    }


def test_readiness_reports_a_safe_not_ready_state_for_a_failed_dependency() -> None:
    def unavailable() -> None:
        raise RuntimeError("mysql://root:password@E:/private/database")

    service = ReadinessService({"database": unavailable})

    report = service.check()

    assert report.ready is False
    assert report.components == {"database": "not_ready"}
    assert "password" not in str(report)
    assert "E:/private" not in str(report)


def test_readiness_marks_only_the_timed_out_probe_not_ready() -> None:
    """One stalled optional dependency must not hang the readiness endpoint."""

    service = ReadinessService(
        {
            "database": ReadinessProbe(lambda: None, timeout_seconds=0.1),
            "embedding": ReadinessProbe(lambda: time.sleep(0.2), timeout_seconds=0.01),
        }
    )

    report = service.check()

    assert report.ready is False
    assert report.components == {"database": "ready", "embedding": "not_ready"}


def test_runtime_probe_builder_checks_all_required_dependencies_with_injection() -> None:
    """Runtime wiring must retain explicit checks instead of startup side effects."""

    from app.services.readiness_probes import RuntimeReadinessDependencies, build_runtime_checks

    calls: list[str] = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement):
            if "alembic_version" in str(_statement):
                calls.append("migration")
                return type("Result", (), {"scalar_one": lambda _self: "head-revision"})()
            calls.append("database")
            return type("Result", (), {"scalar_one": lambda _self: 1})()

    class FakeRedis:
        def ping(self):
            calls.append("redis")
            return True

    dependencies = RuntimeReadinessDependencies(
        session_factory=FakeSession,
        alembic_head=lambda: "head-revision",
        redis_client_factory=lambda _url: FakeRedis(),
        redis_url="redis://safe",
        embedding_loader=lambda: calls.append("embedding"),
        statute_checker=lambda: calls.append("statutes"),
    )

    report = ReadinessService(build_runtime_checks(dependencies)).check()

    assert report.ready is True
    assert report.components == {
        "database": "ready",
        "migration": "ready",
        "redis": "ready",
        "embedding": "ready",
        "statutes": "ready",
    }
    assert calls == ["database", "migration", "redis", "embedding", "statutes"]


def test_runtime_migration_probe_rejects_a_database_not_at_alembic_head() -> None:
    """A reachable database is not ready when its schema revision is stale."""

    from app.services.readiness_probes import RuntimeReadinessDependencies, build_runtime_checks

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement):
            if "alembic_version" in str(_statement):
                return type("Result", (), {"scalar_one": lambda _self: "old-revision"})()
            return type("Result", (), {"scalar_one": lambda _self: 1})()

    dependencies = RuntimeReadinessDependencies(
        session_factory=FakeSession,
        alembic_head=lambda: "head-revision",
        redis_client_factory=lambda _url: type("Redis", (), {"ping": lambda self: True})(),
        redis_url="redis://safe",
        embedding_loader=lambda: None,
        statute_checker=lambda: None,
    )

    report = ReadinessService(build_runtime_checks(dependencies)).check()

    assert report.components["database"] == "ready"
    assert report.components["migration"] == "not_ready"


def test_api_declares_separate_live_and_readiness_routes() -> None:
    """The extracted router must retain liveness/readiness separation."""

    root = Path(__file__).parent.parent
    source = (root / "app" / "main.py").read_text(encoding="utf-8")
    router_source = (root / "app" / "api" / "health.py").read_text(encoding="utf-8")

    assert "health_router" in source
    assert "app.include_router(router)" in source
    assert '@router.get("/health/live"' in router_source
    assert '@router.get(\n    "/health/ready"' in router_source
    assert 'return {"status": "alive"}' in router_source
    assert "status.HTTP_503_SERVICE_UNAVAILABLE" in router_source


def test_api_lifespan_does_not_seed_or_open_the_legacy_law_collection() -> None:
    source = (Path(__file__).parent.parent / "api.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    lifecycle = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "lifespan"
    )
    initializer = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "initialize_components"
    )

    assert "seed_default_prompts" not in ast.unparse(lifecycle)
    assert "LawIndexer(" not in ast.unparse(initializer)


def test_api_wires_all_runtime_readiness_probes_without_startup_mutations() -> None:
    """The endpoint contract must be built from explicit probes, not boot side effects."""
    source = (Path(__file__).parent.parent / "api.py").read_text(encoding="utf-8")

    assert "RuntimeReadinessDependencies" in source
    assert "build_runtime_checks" in source
    assert "assert_system_shared_statutes_ready" in source
    assert '"database"' in source
    assert '"migration"' in source
    assert '"redis"' in source
    assert '"embedding"' in source
    assert '"statutes"' in source
