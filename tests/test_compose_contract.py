"""Static contract for the Stage 3 authoritative Compose topology.

These checks intentionally inspect the declared topology instead of starting
containers.  Runtime acceptance uses a separately named, empty Docker project
and must never operate on a developer's existing MySQL or Chroma data.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _compose() -> str:
    return (ROOT / "compose.yaml").read_text(encoding="utf-8")


def _service_block(compose: str, service_name: str) -> str:
    lines = compose.splitlines()
    header = f"  {service_name}:"
    try:
        start = lines.index(header) + 1
    except ValueError as exc:
        raise AssertionError(f"missing {service_name} service") from exc

    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            break
        body.append(line)
    return "\n".join(body)


def test_root_compose_is_the_authoritative_runtime_topology():
    compose = _compose()

    for service in ("mysql", "redis", "migrate", "bootstrap", "api", "worker", "beat", "web"):
        assert f"  {service}:" in compose
    assert "docker-compose.yml" not in compose
    assert "docker-compose.v3.yml" not in compose


def test_mysql_creates_an_application_user_and_runtime_never_uses_root():
    compose = _compose()

    assert "MYSQL_USER: ${MYSQL_APP_USER:?set MYSQL_APP_USER}" in compose
    assert "MYSQL_PASSWORD: ${MYSQL_APP_PASSWORD:?set MYSQL_APP_PASSWORD}" in compose
    assert "MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:?set MYSQL_ROOT_PASSWORD}" in compose
    assert "mysql+pymysql://${MYSQL_APP_USER:?set MYSQL_APP_USER}:${MYSQL_APP_PASSWORD:?set MYSQL_APP_PASSWORD}@mysql" in compose
    assert "mysql+pymysql://root:" not in compose


def test_api_and_redis_are_private_by_default_and_web_is_the_only_default_port():
    compose = _compose()

    assert '      - "${LEXRAG_WEB_PORT:?set LEXRAG_WEB_PORT}:3000"' in compose
    for service_name in ("mysql", "redis", "api"):
        segment = _service_block(compose, service_name)
        assert "ports:" not in segment


def test_model_seed_and_runtime_data_mounts_are_isolated():
    compose = _compose()

    assert "${LEXRAG_LOCAL_EMBEDDING_MODEL_PATH:?set LEXRAG_LOCAL_EMBEDDING_MODEL_PATH}:/models/bge-m3:ro" in compose
    assert "lexrag_chroma:/app/data/chroma_db" in compose
    assert "lexrag_uploads:/app/data/uploads" in compose
    assert "lexrag_graphs:/app/data/runtime_graphs" in compose
    assert ":/app/data\n" not in compose
    assert "./data/laws:/app/data/laws" not in compose


def test_one_shot_migration_and_bootstrap_gate_runtime_services():
    compose = _compose()

    assert "command: alembic upgrade head" in compose
    assert "command: python scripts/bootstrap_runtime.py all --json" in compose
    for service_name in ("api", "worker", "beat"):
        segment = _service_block(compose, service_name)
        assert "migrate:" in segment
        assert "bootstrap:" in segment
        assert "condition: service_completed_successfully" in segment
    assert "http://localhost:8000/health/ready" in compose


def test_docker_environment_template_has_no_secret_defaults():
    env_template = (ROOT / ".env.docker.example").read_text(encoding="utf-8")

    for variable in (
        "MYSQL_ROOT_PASSWORD=",
        "MYSQL_APP_PASSWORD=",
        "JWT_SECRET_KEY=",
        "LEXRAG_LOCAL_EMBEDDING_MODEL_PATH=",
    ):
        assert variable in env_template
    assert "MYSQL_ROOT_PASSWORD=lexrag" not in env_template
    assert "MYSQL_APP_PASSWORD=lexrag" not in env_template
    assert "JWT_SECRET_KEY=change-this" not in env_template
