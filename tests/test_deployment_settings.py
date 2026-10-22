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


def _constraint_versions() -> dict[str, str]:
    constraints = {}
    for line in (ROOT / "constraints-py313.txt").read_text(encoding="utf-8").splitlines():
        constraint = line.strip()
        if not constraint or constraint.startswith("#"):
            continue
        name, version = constraint.split("==", maxsplit=1)
        constraints[name.lower()] = version
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
    assert f"FROM python:{python_version}-slim" in dockerfile
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

    assert (ROOT / "constraints-py313.txt").is_file()
    assert "COPY requirements.txt constraints-py313.txt ./" in dockerfile
    assert "pip install --no-cache-dir -c constraints-py313.txt -r requirements.txt" in dockerfile


def test_every_direct_requirement_has_an_exact_constraint():
    requirements = set(_direct_requirement_names())
    constraints = _constraint_versions()

    assert requirements <= constraints.keys()
    assert "were not installed in that environment" not in (
        ROOT / "constraints-py313.txt"
    ).read_text(encoding="utf-8")
