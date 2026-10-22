"""Static contracts for the database schema ownership boundary.

These checks deliberately do not connect to a developer database.  Schema
creation belongs to Alembic; application startup only configures connections.
"""

import ast
import importlib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIRECTORY = REPOSITORY_ROOT / "alembic" / "versions"
INITIAL_REVISION = "20260930_00"
FIRST_BUSINESS_REVISION = "20261001_01"
INDEX_IDENTITY_REVISION = "20261022_01"
HISTORICAL_BASE_TABLES = {
    "users",
    "chat_history",
    "prompts",
    "knowledge_bases",
    "document_jobs",
    "favorites",
    "case_sources",
    "case_ingestion_jobs",
    "legal_cases",
}


def _migration_definitions() -> dict[str, tuple[object, Path, ast.Module]]:
    definitions: dict[str, tuple[object, Path, ast.Module]] = {}
    for migration_path in VERSIONS_DIRECTORY.glob("*.py"):
        tree = ast.parse(migration_path.read_text(encoding="utf-8"))
        assignments = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in {"revision", "down_revision"}
        }
        definitions[assignments["revision"]] = (
            assignments.get("down_revision"),
            migration_path,
            tree,
        )
    return definitions


def _created_tables(tree: ast.Module) -> set[str]:
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_table"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


def test_init_db_does_not_create_schema() -> None:
    tree = ast.parse((REPOSITORY_ROOT / "app" / "db" / "session.py").read_text(encoding="utf-8"))

    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_all"
        for node in ast.walk(tree)
    )


def test_migration_graph_has_one_root_and_one_head() -> None:
    definitions = _migration_definitions()
    parents = {revision: parent for revision, (parent, _, _) in definitions.items()}
    roots = {revision for revision, parent in parents.items() if parent is None}
    referenced_revisions = {
        parent for parent in parents.values() if isinstance(parent, str) and parent in parents
    }
    heads = set(parents) - referenced_revisions

    assert roots == {INITIAL_REVISION}
    assert heads == {INDEX_IDENTITY_REVISION}


def test_first_business_migration_depends_on_initial_schema() -> None:
    definitions = _migration_definitions()

    assert definitions[FIRST_BUSINESS_REVISION][0] == INITIAL_REVISION


def test_initial_schema_creates_every_historical_base_table() -> None:
    definitions = _migration_definitions()
    _, _, initial_schema = definitions[INITIAL_REVISION]

    assert _created_tables(initial_schema) == HISTORICAL_BASE_TABLES


def test_all_registered_model_tables_are_owned_by_a_migration() -> None:
    for module_name in (
        "agent_config",
        "audit_log",
        "case_source",
        "chat_history",
        "document_job",
        "document_page",
        "document_relation",
        "document_structure",
        "favorite",
        "knowledge_base",
        "law_update",
        "organization",
        "prompt",
        "rbac",
        "scenario_job",
        "session",
        "usage_daily",
        "user",
        "user_profile",
    ):
        importlib.import_module(f"app.models.{module_name}")
    from app.db.base import Base

    definitions = _migration_definitions()
    migration_tables = set().union(*(_created_tables(tree) for _, _, tree in definitions.values()))

    assert set(Base.metadata.tables) <= migration_tables


def test_index_identity_migration_is_the_current_descendant() -> None:
    definitions = _migration_definitions()
    parent, _, migration = definitions[INDEX_IDENTITY_REVISION]
    column_names = {
        node.args[0].value
        for node in ast.walk(migration)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Column"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }

    assert parent == "20261021_01"
    assert {"source_hash", "embedding_fingerprint", "index_schema_version"} <= column_names


def test_api_lifespan_does_not_run_migrations() -> None:
    tree = ast.parse((REPOSITORY_ROOT / "api.py").read_text(encoding="utf-8"))
    lifespan = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "lifespan"
    )
    call_names = {
        node.func.attr
        for node in ast.walk(lifespan)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "upgrade" not in call_names
    assert "run_migrations" not in call_names
    assert "create_all" not in call_names
