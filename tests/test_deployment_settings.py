"""Regression checks for the container and local runtime dependency contract."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _direct_requirement_names() -> list[str]:
    names = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        requirement = line.strip()
        if not requirement or requirement.startswith("#"):
            continue
        names.append(re.split(r"[<>=!~\[; ]", requirement, maxsplit=1)[0].lower())
    return names


def _constraint_versions(contents: str | None = None) -> dict[str, str]:
    constraints = {}
    if contents is None:
        contents = (ROOT / "constraints-py313.txt").read_text(encoding="utf-8")
    for line in contents.splitlines():
        constraint = line.strip()
        if (
            not constraint
            or constraint.startswith("#")
            or constraint.startswith("--hash=")
        ):
            continue
        name, version = constraint.split("==", maxsplit=1)
        constraints[name.lower()] = version.split("\\", maxsplit=1)[0].strip()
    return constraints


def test_requirements_use_mysql_driver_without_postgres_or_duplicates():
    names = _direct_requirement_names()

    assert "pymysql" in names
    assert "psycopg2-binary" not in names
    assert "pgvector" not in names
    assert len(names) == len(set(names))


def test_python_runtime_versions_agree():
    python_version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert python_version == "3.13"
    assert re.search(
        rf"FROM python:{re.escape(python_version)}\.\d+-slim@sha256:[a-f0-9]{{64}} AS base",
        dockerfile,
    )
    assert 'target-version = "py313"' in pyproject


def test_frontend_node_runtime_versions_agree_and_use_lockfile():
    node_version = (ROOT / ".nvmrc").read_text(encoding="utf-8").strip()
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")

    assert node_version == "22"
    assert f"FROM node:{node_version}-alpine" in dockerfile
    assert "COPY package.json package-lock.json ./" in dockerfile
    assert "npm ci" in dockerfile
    assert "npm install" not in dockerfile


def test_docker_installs_requirements_through_constraints_file():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    install_command = dockerfile.split("RUN pip install", maxsplit=1)[1].split(
        "\n\n", maxsplit=1
    )[0].replace("\\\n", " ")

    assert (ROOT / "constraints-py313.txt").is_file()
    assert "COPY requirements.txt constraints-py313.txt ./" in dockerfile
    assert "--no-cache-dir" in install_command
    assert "-c constraints-py313.txt -r requirements.txt" in install_command


def test_every_direct_requirement_has_an_exact_constraint():
    requirements = set(_direct_requirement_names())
    constraints = _constraint_versions()

    assert requirements <= constraints.keys()
    assert "were not installed in that environment" not in (
        ROOT / "constraints-py313.txt"
    ).read_text(encoding="utf-8")


def test_base_runtime_defers_zhipu_sdk_to_stage_3_task_3():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "zhipuai>=" not in requirements
    assert "Stage 3 Task 3" in requirements


def test_constraints_are_a_complete_clean_resolution_lock():
    constraints = (ROOT / "constraints-py313.txt").read_text(encoding="utf-8")

    assert "Generated from a clean Linux Python 3.13 resolution" in constraints
    assert "not a complete transitive lock" not in constraints
    assert "--hash=" in constraints
    assert len(_constraint_versions()) > len(_direct_requirement_names())


def test_constraint_parser_ignores_pip_compile_hash_continuations():
    lock = "alembic==1.18.5 " + "\\" + "\n    --hash=sha256:abc\n"

    assert _constraint_versions(lock) == {"alembic": "1.18.5"}


def test_container_images_use_immutable_patch_tags():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    frontend_dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")

    assert re.search(r"FROM python:3\.13\.\d+-slim@sha256:[a-f0-9]{64} AS base", dockerfile)
    assert re.search(r"FROM node:22(?:\.\d+\.\d+)?-alpine@sha256:[a-f0-9]{64} AS builder", frontend_dockerfile)
    assert re.search(r"FROM nginx:1\.27(?:\.\d+)?-alpine@sha256:[a-f0-9]{64}", frontend_dockerfile)


def test_cpu_only_torch_contract_uses_official_index():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    constraints = (ROOT / "constraints-py313.txt").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    # The official CPU index publishes the Linux CPython 3.13 wheel as
    # ``torch-<version>+cpu`` while resolving it from the public requirement
    # specifier ``torch==<version>``.  Pinning ``+cpu`` in requirements makes
    # pip-compile reject that wheel before it can write the verified lock.
    assert re.search(r"^torch==\d+\.\d+\.\d+$", requirements, re.MULTILINE)
    assert re.search(
        r"^torch==\d+\.\d+\.\d+\+cpu(?:\s+\\)?$", constraints, re.MULTILINE
    )
    assert "https://download.pytorch.org/whl/cpu" in dockerfile


def test_constraints_forbid_nvidia_distributions():
    constraints = (ROOT / "constraints-py313.txt").read_text(encoding="utf-8")

    assert not re.search(r"^nvidia-[^=\s]+==", constraints, re.MULTILINE)


def test_stage_3_wheel_cache_is_kept_out_of_version_control():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".stage3-wheel-cache/" in gitignore


def test_lock_regeneration_script_uses_hashes_and_cpu_wheel_index():
    script = (ROOT / "scripts" / "regenerate_constraints_lock.sh").read_text(
        encoding="utf-8"
    )
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "pip-compile --generate-hashes" in script
    assert 'PYPI_INDEX="https://pypi.org/simple"' in script
    assert "PIP_INDEX_URL=https://pypi.org/simple" in dockerfile
    assert '--find-links "$PYTORCH_CPU_INDEX"' in script
    assert "https://download.pytorch.org/whl/cpu" in script
    assert "PIP_CACHE_DIR" in script


def test_regeneration_script_marks_lock_only_after_runtime_verification():
    script = (ROOT / "scripts" / "regenerate_constraints_lock.sh").read_text(
        encoding="utf-8"
    )
    marker = "Generated from a clean Linux Python 3.13 resolution"

    assert marker in script
    assert script.index("if pip list --format=freeze") < script.index(marker)
