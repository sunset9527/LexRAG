"""Provenance manifests for reproducible evaluation runs."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = ["build_run_manifest", "write_run_manifest"]

_SCHEMA_VERSION = "1.0"
_SECRET_KEY_TERMS = ("key", "token", "secret", "password", "authorization")
_RUNTIME_IDENTITY_KEYS = {"provider", "baseurl", "model"}


def build_run_manifest(
    *,
    run_name: str,
    dataset_paths: Iterable[str | Path],
    legal_source_manifest_paths: Iterable[str | Path],
    collection_names: Iterable[str],
    embedding_version: str,
    chunker_version: str,
    runtime_identity: Mapping[str, str],
    commit_provider: Callable[[], str] | None = None,
    clock_provider: Callable[[], datetime | str] | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable provenance record for one evaluation run.

    ``runtime_identity`` is deliberately limited to provider, base URL, and model
    identifiers so callers cannot accidentally capture runtime configuration or
    credentials in a formal report.
    """
    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _format_timestamp((clock_provider or _utc_now)()),
        "git_commit": (commit_provider or _current_git_commit)(),
        "run_name": run_name,
        "datasets": _artifact_entries(dataset_paths, "dataset"),
        "legal_source_manifests": _artifact_entries(
            legal_source_manifest_paths, "legal-source manifest"
        ),
        "collection_names": list(collection_names),
        "embedding_version": embedding_version,
        "chunker_version": chunker_version,
        "runtime_identity": _validated_runtime_identity(runtime_identity),
    }


def write_run_manifest(
    path: str | Path,
    **manifest_arguments: Any,
) -> dict[str, Any]:
    """Build and write a run manifest to ``path``, returning its content."""
    manifest = build_run_manifest(**manifest_arguments)
    output_path = Path(path)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _artifact_entries(paths: Iterable[str | Path], artifact_kind: str) -> list[dict[str, str]]:
    return [_artifact_entry(path, artifact_kind) for path in paths]


def _artifact_entry(path: str | Path, artifact_kind: str) -> dict[str, str]:
    artifact_path = Path(path)
    if not artifact_path.is_file():
        raise FileNotFoundError(
            f"Declared {artifact_kind} artifact does not exist or is not a file: {artifact_path}"
        )

    try:
        digest = _sha256_file(artifact_path)
    except OSError as error:
        raise OSError(
            f"Unable to read declared {artifact_kind} artifact: {artifact_path}"
        ) from error

    return {"path": str(artifact_path), "sha256": digest}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        while chunk := artifact.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_runtime_identity(runtime_identity: Mapping[str, str]) -> dict[str, str]:
    validated: dict[str, str] = {}
    for key, value in runtime_identity.items():
        normalized_key = re.sub(r"[^a-z0-9]", "", key.casefold())
        if any(term in normalized_key for term in _SECRET_KEY_TERMS):
            raise ValueError(f"Runtime identity contains a credential or secret key: {key}")
        if normalized_key not in _RUNTIME_IDENTITY_KEYS:
            raise ValueError(
                f"Runtime identity only permits provider, base_url, and model identifiers: {key}"
            )
        if not isinstance(value, str):
            raise TypeError(f"Runtime identity value for {key} must be a string")
        validated[key] = value
    return validated


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _format_timestamp(value: datetime | str) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, datetime):
        raise TypeError("clock_provider must return a datetime or ISO-8601 timestamp string")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _current_git_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("Unable to determine the current Git commit") from error
    return completed.stdout.strip()
