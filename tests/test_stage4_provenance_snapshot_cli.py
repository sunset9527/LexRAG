"""CLI safety tests for Stage 4 provenance snapshots."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import snapshot_stage4_provenance as cli


def test_snapshot_atomic_write_preserves_existing_output_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    output = tmp_path / "snapshot.json"
    output.write_bytes(b"old snapshot\n")

    def fail_replace(source: object, destination: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated"):
        cli._write_atomically(output, b"new snapshot\n")

    assert output.read_bytes() == b"old snapshot\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_snapshot_cli_requires_explicit_as_of():
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            [
                "--chroma-directory",
                "chroma",
                "--output",
                "snapshot.json",
            ]
        )


def test_snapshot_cli_refuses_output_inside_chroma_input_directory(tmp_path: Path):
    chroma = tmp_path / "chroma"
    output = chroma / "snapshot.json"

    with pytest.raises(ValueError, match="Chroma"):
        cli._validate_output_path(chroma, output)
