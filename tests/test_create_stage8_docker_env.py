from __future__ import annotations

from pathlib import Path

import pytest

from scripts.create_stage8_docker_env import Stage8DockerEnvironmentError, create_environment


def test_create_environment_writes_nonempty_secrets_without_returning_them(tmp_path: Path) -> None:
    output = tmp_path / ".env.docker.stage8"

    created = create_environment(output, model_path=Path(r"E:\huggingface\model"), web_port=18081)

    assert created == output
    values = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if line)
    assert values["MYSQL_DATABASE"] == "lexrag"
    assert values["MYSQL_APP_USER"] == "lexrag"
    assert values["LEXRAG_LOCAL_EMBEDDING_MODEL_PATH"] == r"E:\huggingface\model"
    assert values["LEXRAG_WEB_PORT"] == "18081"
    assert all(values[key] for key in ("MYSQL_ROOT_PASSWORD", "MYSQL_APP_PASSWORD", "JWT_SECRET_KEY"))


def test_create_environment_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    output = tmp_path / ".env.docker.stage8"
    output.write_text("existing=true\n", encoding="utf-8")

    with pytest.raises(Stage8DockerEnvironmentError, match="已存在"):
        create_environment(output, model_path=Path(r"E:\huggingface\model"), web_port=18081)
