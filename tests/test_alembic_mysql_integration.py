"""Real MySQL migration contracts, isolated from every developer database.

Run explicitly with ``RUN_MYSQL_MIGRATION_INTEGRATION=1``.  The fixture starts
an ephemeral Docker container, creates only temporary schemas inside it, and
removes the container after the test session.
"""

import importlib
import os
import secrets
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL, Engine

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUN_INTEGRATION = os.getenv("RUN_MYSQL_MIGRATION_INTEGRATION") == "1"
MYSQL_IMAGE = "mysql:8.4"
LEGACY_HEAD = "20261021_01"
CURRENT_HEAD = "20261022_01"

pytestmark = pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="set RUN_MYSQL_MIGRATION_INTEGRATION=1 to run isolated Docker MySQL checks",
)


def _run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=True,
        cwd=REPOSITORY_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _wait_for_mysql(url: URL, timeout_seconds: int = 90) -> None:
    engine = sa.create_engine(url, pool_pre_ping=True)
    try:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                with engine.connect() as connection:
                    connection.execute(sa.text("SELECT 1"))
                return
            except sa.exc.OperationalError:
                time.sleep(1)
        pytest.fail("isolated MySQL container did not become ready")
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def mysql_server_url() -> Iterator[URL]:
    container_name = f"lexrag-alembic-contract-{uuid.uuid4().hex[:12]}"
    root_password = secrets.token_urlsafe(24)
    _run(
        [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--name",
            container_name,
            "--label",
            "lexrag.test=alembic-contract",
            "--env",
            f"MYSQL_ROOT_PASSWORD={root_password}",
            "--publish",
            "127.0.0.1::3306",
            MYSQL_IMAGE,
        ]
    )
    try:
        port = _run(["docker", "port", container_name, "3306/tcp"]).stdout.strip().rsplit(":", 1)[1]
        url = URL.create(
            "mysql+pymysql",
            username="root",
            password=root_password,
            host="127.0.0.1",
            port=int(port),
            database="mysql",
            query={"charset": "utf8mb4"},
        )
        _wait_for_mysql(url)
        yield url
    finally:
        subprocess.run(
            ["docker", "rm", "--force", container_name],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )


def _database_url(server_url: URL, database_name: str) -> URL:
    assert database_name.startswith("lexrag_alembic_contract_")
    assert database_name.replace("_", "").isalnum()
    engine = sa.create_engine(server_url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4"))
    finally:
        engine.dispose()
    return server_url.set(database=database_name)


def _drop_database(server_url: URL, database_name: str) -> None:
    assert database_name.startswith("lexrag_alembic_contract_")
    assert database_name.replace("_", "").isalnum()
    engine = sa.create_engine(server_url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f"DROP DATABASE IF EXISTS `{database_name}`"))
    finally:
        engine.dispose()


@pytest.fixture
def mysql_database_url(mysql_server_url: URL) -> Iterator[URL]:
    database_name = f"lexrag_alembic_contract_{uuid.uuid4().hex}"
    database_url = _database_url(mysql_server_url, database_name)
    try:
        yield database_url
    finally:
        _drop_database(mysql_server_url, database_name)


def _upgrade(database_url: URL, revision: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url.render_as_string(hide_password=False)
    _run([sys.executable, "-m", "alembic", "upgrade", revision], env=environment)


def _current_revision(database_url: URL) -> str:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url.render_as_string(hide_password=False)
    return _run([sys.executable, "-m", "alembic", "current"], env=environment).stdout


def _registered_metadata() -> sa.MetaData:
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

    return Base.metadata


def _normalized_default(value: object) -> str | None:
    if value is None:
        return None
    rendered = str(value).replace("'", "").replace("(", "").replace(")", "").upper()
    return rendered.replace("CURRENT_TIMESTAMP", "NOW")


def _expected_server_default(column: sa.Column[object]) -> str | None:
    if column.server_default is None:
        return None
    return _normalized_default(column.server_default.arg)


def _actual_indexes(
    inspector: sa.Inspector, table_name: str, unique_constraint_names: set[str]
) -> set[tuple[str, tuple[str, ...], bool]]:
    return {
        (index["name"], tuple(index["column_names"]), bool(index.get("unique")))
        for index in inspector.get_indexes(table_name)
        if index["name"] != "PRIMARY" and index["name"] not in unique_constraint_names
    }


def _expected_indexes(table: sa.Table) -> set[tuple[str, tuple[str, ...], bool]]:
    return {
        (index.name, tuple(column.name for column in index.columns), bool(index.unique))
        for index in table.indexes
    }


def _actual_unique_constraints(
    inspector: sa.Inspector, table_name: str, expected_names: set[str]
) -> set[tuple[str, tuple[str, ...]]]:
    return {
        (constraint["name"], tuple(constraint["column_names"]))
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint["name"] in expected_names
    }


def _expected_unique_constraints(table: sa.Table) -> set[tuple[str, tuple[str, ...]]]:
    return {
        (constraint.name, tuple(column.name for column in constraint.columns))
        for constraint in table.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }


def _normalized_check_sqltext(value: object) -> str:
    rendered = " ".join(str(value).replace("`", "").split()).lower()
    while rendered.startswith("(") and rendered.endswith(")"):
        rendered = rendered[1:-1].strip()
    return rendered


def _actual_check_constraints(inspector: sa.Inspector, table_name: str) -> set[tuple[str, str]]:
    return {
        (str(constraint["name"]), _normalized_check_sqltext(constraint["sqltext"]))
        for constraint in inspector.get_check_constraints(table_name)
    }


def _expected_check_constraints(table: sa.Table) -> set[tuple[str, str]]:
    return {
        (str(constraint.name), _normalized_check_sqltext(constraint.sqltext))
        for constraint in table.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }


def _foreign_keys(table: sa.Table) -> set[tuple[str, str, str | None]]:
    return {
        (foreign_key.parent.name, foreign_key.target_fullname, foreign_key.ondelete)
        for foreign_key in table.foreign_keys
    }


def _assert_column_type(
    engine: Engine, table_name: str, expected_column: sa.Column[object], actual_column: dict[str, object]
) -> None:
    actual_type = actual_column["type"]
    actual_rendered = actual_type.compile(dialect=engine.dialect).upper()
    if isinstance(expected_column.type, sa.Boolean):
        # MySQL persists BOOLEAN as its documented TINYINT alias.
        assert actual_rendered in {"BOOL", "BOOLEAN", "TINYINT", "TINYINT(1)"}, (
            f"{table_name}.{expected_column.name} type"
        )
    else:
        expected_rendered = expected_column.type.compile(dialect=engine.dialect).upper()
        assert expected_rendered == actual_rendered, f"{table_name}.{expected_column.name} type"

    assert getattr(actual_type, "length", None) == getattr(expected_column.type, "length", None), (
        f"{table_name}.{expected_column.name} length"
    )


def _assert_schema_matches_metadata(database_url: URL) -> None:
    metadata = _registered_metadata()
    engine = sa.create_engine(database_url)
    try:
        inspector = sa.inspect(engine)
        actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
        assert actual_tables == set(metadata.tables)

        for table_name, expected_table in metadata.tables.items():
            actual_columns = {column["name"]: column for column in inspector.get_columns(table_name)}
            assert set(actual_columns) == set(expected_table.columns), table_name
            actual_primary_key = tuple(inspector.get_pk_constraint(table_name)["constrained_columns"])
            assert actual_primary_key == tuple(column.name for column in expected_table.primary_key), table_name
            expected_unique_constraints = _expected_unique_constraints(expected_table)
            expected_unique_names = {name for name, _ in expected_unique_constraints}
            assert _actual_indexes(
                inspector, table_name, expected_unique_names
            ) == _expected_indexes(expected_table), table_name
            assert _actual_unique_constraints(
                inspector, table_name, expected_unique_names
            ) == expected_unique_constraints, table_name
            assert _actual_check_constraints(
                inspector, table_name
            ) == _expected_check_constraints(expected_table), table_name

            actual_foreign_keys = {
                (
                    foreign_key["constrained_columns"][0],
                    f"{foreign_key['referred_table']}.{foreign_key['referred_columns'][0]}",
                    foreign_key.get("options", {}).get("ondelete"),
                )
                for foreign_key in inspector.get_foreign_keys(table_name)
            }
            assert actual_foreign_keys == _foreign_keys(expected_table), table_name

            for expected_column in expected_table.columns:
                actual_column = actual_columns[expected_column.name]
                _assert_column_type(engine, table_name, expected_column, actual_column)
                assert actual_column["nullable"] is expected_column.nullable, (
                    f"{table_name}.{expected_column.name} nullability"
                )
                assert _normalized_default(actual_column["default"]) == _expected_server_default(
                    expected_column
                ), f"{table_name}.{expected_column.name} server default"
    finally:
        engine.dispose()


def test_empty_mysql_upgrade_head_matches_metadata_and_is_idempotent(mysql_database_url: URL) -> None:
    database_url = mysql_database_url
    _upgrade(database_url, "head")
    _assert_schema_matches_metadata(database_url)
    _upgrade(database_url, "head")

    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == CURRENT_HEAD
    finally:
        engine.dispose()
    assert CURRENT_HEAD in _current_revision(database_url)


def test_previous_head_upgrades_to_current_head(mysql_database_url: URL) -> None:
    database_url = mysql_database_url
    _upgrade(database_url, LEGACY_HEAD)
    _upgrade(database_url, "head")
    _assert_schema_matches_metadata(database_url)
    assert CURRENT_HEAD in _current_revision(database_url)
