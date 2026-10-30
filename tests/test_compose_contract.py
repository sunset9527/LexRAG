"""Static contract for the Stage 3 authoritative Compose topology.

These checks parse the actual Compose YAML rather than matching indentation.
Runtime acceptance uses a separately named, empty Docker project and must
never operate on a developer's existing MySQL or Chroma data.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict:
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def test_root_compose_is_the_authoritative_runtime_topology():
    services = _compose()["services"]

    assert {"mysql", "redis", "migrate", "bootstrap", "api", "worker", "beat", "web", "mcp"} <= set(services)
    assert not (ROOT / "docker-compose.yml").exists()
    assert not (ROOT / "docker-compose.v3.yml").exists()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "compose.yaml" in readme
    assert "docker-compose.v3.yml" not in readme


def test_mysql_creates_an_application_user_and_runtime_never_uses_root():
    compose = _compose()
    mysql_environment = compose["services"]["mysql"]["environment"]
    runtime_environment = compose["x-runtime-environment"]

    assert mysql_environment["MYSQL_USER"] == "${MYSQL_APP_USER:?set MYSQL_APP_USER}"
    assert mysql_environment["MYSQL_PASSWORD"] == "${MYSQL_APP_PASSWORD:?set MYSQL_APP_PASSWORD}"
    assert mysql_environment["MYSQL_ROOT_PASSWORD"] == "${MYSQL_ROOT_PASSWORD:?set MYSQL_ROOT_PASSWORD}"
    assert runtime_environment["DATABASE_URL"].startswith(
        "mysql+pymysql://${MYSQL_APP_USER:?set MYSQL_APP_USER}:"
    )
    assert "mysql+pymysql://root:" not in runtime_environment["DATABASE_URL"]


def test_mysql_healthcheck_waits_for_the_tcp_listener_not_the_init_socket():
    """MySQL's init-time Unix socket must not release one-shot migrations early."""
    healthcheck = _compose()["services"]["mysql"]["healthcheck"]

    assert "--protocol=tcp" in healthcheck["test"][-1]
    assert "127.0.0.1" in healthcheck["test"][-1]


def test_api_and_redis_are_private_by_default_and_web_is_the_only_default_port():
    services = _compose()["services"]

    assert services["web"]["ports"] == ["${LEXRAG_WEB_PORT:?set LEXRAG_WEB_PORT}:3000"]
    for service_name in ("mysql", "redis", "api"):
        assert "ports" not in services[service_name]


def test_model_seed_and_runtime_data_mounts_are_isolated():
    runtime_volumes = _compose()["x-runtime-volumes"]

    assert "${LEXRAG_LOCAL_EMBEDDING_MODEL_PATH:?set LEXRAG_LOCAL_EMBEDDING_MODEL_PATH}:/models/bge-m3:ro" in runtime_volumes
    assert "lexrag_chroma:/app/data/chroma_db" in runtime_volumes
    assert "lexrag_uploads:/app/data/uploads" in runtime_volumes
    assert all("graph" not in volume for volume in runtime_volumes)
    assert ":/app/data" not in runtime_volumes
    assert "./data/laws:/app/data/laws" not in runtime_volumes


def test_one_shot_migration_and_bootstrap_gate_runtime_services():
    services = _compose()["services"]

    assert services["migrate"]["command"] == "alembic upgrade head"
    assert services["bootstrap"]["command"] == "python scripts/bootstrap_runtime.py all --json"
    for service_name in ("api", "worker", "beat"):
        depends_on = services[service_name]["depends_on"]
        assert depends_on["migrate"]["condition"] == "service_completed_successfully"
        assert depends_on["bootstrap"]["condition"] == "service_completed_successfully"
    assert services["api"]["healthcheck"]["test"][-1] == "http://localhost:8000/health/ready"


def test_volume_permissions_are_initialized_before_non_root_bootstrap():
    services = _compose()["services"]
    volume_init = services["volume-init"]

    assert volume_init["user"] == "0:0"
    assert volume_init["restart"] == "no"
    assert "chown -R appuser:appuser" in volume_init["command"]
    assert set(volume_init["volumes"]) == {
        "lexrag_chroma:/app/data/chroma_db",
        "lexrag_uploads:/app/data/uploads",
        "lexrag_law_snapshots:/app/data/law_snapshots",
    }
    assert services["bootstrap"]["depends_on"]["volume-init"]["condition"] == (
        "service_completed_successfully"
    )


def test_api_image_contains_the_bootstrap_command_source():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY scripts/bootstrap_runtime.py ./scripts/bootstrap_runtime.py" in dockerfile


def test_api_dockerfile_has_no_unused_streamlit_frontend_target():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "AS frontend" not in dockerfile
    assert "streamlit" not in dockerfile.lower()


def test_mcp_is_opt_in_and_never_exposes_a_default_port():
    mcp = _compose()["services"]["mcp"]

    assert mcp["profiles"] == ["mcp"]
    assert "ports" not in mcp
    assert mcp["command"] == "python -m app.mcp_server"
    assert mcp["depends_on"]["bootstrap"]["condition"] == "service_completed_successfully"


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
