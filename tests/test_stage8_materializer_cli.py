"""Safety tests for the Stage 8 materializer CLI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import materialize_stage8_frozen_dataset as cli
from src.evaluation.stage8_materializer import Stage8MaterializationError


def test_cli_rejects_output_overlap_with_inputs_or_each_other(tmp_path: Path):
    baseline = tmp_path / "baseline.jsonl"
    snapshot = tmp_path / "snapshot.json"
    dataset = tmp_path / "dataset.jsonl"
    manifest = tmp_path / "manifest.json"

    with pytest.raises(Stage8MaterializationError, match="input"):
        cli._validate_paths(baseline, snapshot, baseline, manifest)
    with pytest.raises(Stage8MaterializationError, match="distinct"):
        cli._validate_paths(baseline, snapshot, dataset, dataset)

    dataset.write_bytes(b"orphan output")
    with pytest.raises(Stage8MaterializationError, match="inconsistent"):
        cli._validate_paths(baseline, snapshot, dataset, manifest)


def test_atomic_pair_write_cleans_first_stage_when_second_stage_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    dataset = tmp_path / "dataset.jsonl"
    manifest = tmp_path / "manifest.json"
    real_stage = cli._stage
    calls = 0

    def fail_second_stage(path: Path, payload: bytes) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated staging failure")
        return real_stage(path, payload)

    monkeypatch.setattr(cli, "_stage", fail_second_stage)

    with pytest.raises(OSError, match="staging"):
        cli._write_pair_atomically(dataset, b"new dataset\n", manifest, b"new manifest\n")

    assert not dataset.exists()
    assert not manifest.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_pair_write_rolls_back_both_outputs_when_second_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    dataset = tmp_path / "dataset.jsonl"
    manifest = tmp_path / "manifest.json"
    dataset.write_bytes(b"old dataset\n")
    manifest.write_bytes(b"old manifest\n")
    real_replace = os.replace
    calls = 0

    def fail_second_replace(source: object, destination: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="simulated"):
        cli._write_pair_atomically(dataset, b"new dataset\n", manifest, b"new manifest\n")

    assert dataset.read_bytes() == b"old dataset\n"
    assert manifest.read_bytes() == b"old manifest\n"
    assert not list(tmp_path.glob("*.tmp"))
