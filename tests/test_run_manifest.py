"""Run-manifest provenance and secret-safety contract tests."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

from src.evaluation.run_manifest import build_run_manifest, write_run_manifest


def test_write_run_manifest_captures_declared_artifacts_and_injected_identity(tmp_path):
    dataset = tmp_path / "evaluation.jsonl"
    dataset.write_text('{"id": "case-001"}\n', encoding="utf-8")
    legal_sources = tmp_path / "legal-sources.json"
    legal_sources.write_text('{"sources": []}\n', encoding="utf-8")
    output = tmp_path / "run-manifest.json"

    manifest = write_run_manifest(
        output,
        run_name="retrieval-baseline",
        dataset_paths=[dataset],
        legal_source_manifest_paths=[legal_sources],
        collection_names=["civil-code", "criminal-law"],
        embedding_version="bge-m3@local-2026-10",
        chunker_version="statute-v2",
        runtime_identity={
            "provider": "openai-compatible",
            "base_url": "http://localhost:8001/v1",
            "model": "qwen-local",
        },
        commit_provider=lambda: "abc123",
        clock_provider=lambda: datetime(2026, 10, 26, 8, 30, tzinfo=UTC),
    )

    assert manifest == json.loads(output.read_text(encoding="utf-8"))
    assert manifest == {
        "schema_version": "1.0",
        "generated_at": "2026-10-26T08:30:00Z",
        "git_commit": "abc123",
        "run_name": "retrieval-baseline",
        "datasets": [
            {
                "path": str(dataset),
                "sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
            }
        ],
        "legal_source_manifests": [
            {
                "path": str(legal_sources),
                "sha256": hashlib.sha256(legal_sources.read_bytes()).hexdigest(),
            }
        ],
        "collection_names": ["civil-code", "criminal-law"],
        "embedding_version": "bge-m3@local-2026-10",
        "chunker_version": "statute-v2",
        "runtime_identity": {
            "provider": "openai-compatible",
            "base_url": "http://localhost:8001/v1",
            "model": "qwen-local",
        },
    }


@pytest.mark.parametrize(
    "secret_key", ["api_key", "accessToken", "client-secret", "password", "Authorization"]
)
def test_build_run_manifest_rejects_runtime_identity_with_secret_key(tmp_path, secret_key):
    dataset = tmp_path / "evaluation.jsonl"
    dataset.write_text("[]", encoding="utf-8")
    output = tmp_path / "unsafe-manifest.json"

    with pytest.raises(ValueError, match="credential|secret"):
        write_run_manifest(
            output,
            run_name="unsafe-run",
            dataset_paths=[dataset],
            legal_source_manifest_paths=[],
            collection_names=[],
            embedding_version="embedding-v1",
            chunker_version="chunker-v1",
            runtime_identity={"provider": "local", secret_key: "do-not-persist"},
            commit_provider=lambda: "abc123",
            clock_provider=lambda: "2026-10-26T08:30:00Z",
        )

    assert not output.exists()


def test_build_run_manifest_rejects_missing_declared_artifact(tmp_path):
    missing_dataset = tmp_path / "missing.jsonl"

    with pytest.raises(FileNotFoundError, match="Declared dataset artifact"):
        build_run_manifest(
            run_name="missing-input",
            dataset_paths=[missing_dataset],
            legal_source_manifest_paths=[],
            collection_names=[],
            embedding_version="embedding-v1",
            chunker_version="chunker-v1",
            runtime_identity={"provider": "local"},
            commit_provider=lambda: "abc123",
            clock_provider=lambda: "2026-10-26T08:30:00Z",
        )


def test_write_run_manifest_rejects_credential_bearing_base_url_without_writing(tmp_path):
    dataset = tmp_path / "evaluation.jsonl"
    dataset.write_text("[]", encoding="utf-8")
    output = tmp_path / "unsafe-url-manifest.json"

    with pytest.raises(ValueError, match="base URL"):
        write_run_manifest(
            output,
            run_name="unsafe-url",
            dataset_paths=[dataset],
            legal_source_manifest_paths=[],
            collection_names=[],
            embedding_version="embedding-v1",
            chunker_version="chunker-v1",
            runtime_identity={
                "provider": "remote",
                "base_url": "https://user:super-secret@api.example/v1?api_key=still-secret",
            },
            commit_provider=lambda: "abc123",
            clock_provider=lambda: "2026-10-26T08:30:00Z",
        )

    assert not output.exists()


def test_build_run_manifest_normalizes_injected_offset_timestamp_to_utc(tmp_path):
    dataset = tmp_path / "evaluation.jsonl"
    dataset.write_text("[]", encoding="utf-8")

    manifest = build_run_manifest(
        run_name="offset-clock",
        dataset_paths=[dataset],
        legal_source_manifest_paths=[],
        collection_names=[],
        embedding_version="embedding-v1",
        chunker_version="chunker-v1",
        runtime_identity={"provider": "local"},
        commit_provider=lambda: "abc123",
        clock_provider=lambda: "2026-10-26T16:30:00+08:00",
    )

    assert manifest["generated_at"] == "2026-10-26T08:30:00Z"


@pytest.mark.parametrize("timestamp", ["not-a-timestamp", "2026-10-26T08:30:00"])
def test_build_run_manifest_rejects_invalid_or_naive_injected_timestamp(tmp_path, timestamp):
    dataset = tmp_path / "evaluation.jsonl"
    dataset.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="aware ISO-8601"):
        build_run_manifest(
            run_name="invalid-clock",
            dataset_paths=[dataset],
            legal_source_manifest_paths=[],
            collection_names=[],
            embedding_version="embedding-v1",
            chunker_version="chunker-v1",
            runtime_identity={"provider": "local"},
            commit_provider=lambda: "abc123",
            clock_provider=lambda: timestamp,
        )
