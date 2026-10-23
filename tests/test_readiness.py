"""Stage 3 readiness contracts independent from FastAPI startup."""

from pathlib import Path
import ast

from app.services.readiness_service import ReadinessService


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


def test_api_declares_separate_live_and_readiness_routes() -> None:
    """Avoid importing the heavyweight API graph in this unit-level contract."""

    source = (Path(__file__).parent.parent / "api.py").read_text(encoding="utf-8")

    assert '@app.get("/health/live")' in source
    assert '@app.get("/health/ready")' in source
    assert 'return {"status": "alive"}' in source
    assert 'status_code=503' in source


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
