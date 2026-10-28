"""Build a queryable Stage 8 evaluation-only Chroma copy from stored vectors."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.stage8_materializer import load_stage4_snapshot
from src.evaluation.stage8_vector_index_repair import repair_isolated_copy


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-directory", type=Path, required=True)
    parser.add_argument("--target-directory", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _new_client(path: str):
    from chromadb import PersistentClient

    return PersistentClient(path=path)


def _write_atomically(output: Path, report: dict) -> None:
    payload = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_paths(args: argparse.Namespace) -> None:
    source = args.source_directory.resolve()
    target = args.target_directory.resolve()
    output = args.output.resolve()
    if not source.is_dir():
        raise ValueError("source directory must exist")
    if target.exists():
        raise ValueError("target directory must not exist")
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("source and target directories must be disjoint")
    if output == args.snapshot.resolve() or output == source or output.is_relative_to(source):
        raise ValueError("output must be outside source artifacts")
    if output == target or output.is_relative_to(target):
        raise ValueError("output must be outside target directory")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _validate_paths(args)
        snapshot, _ = load_stage4_snapshot(args.snapshot)
        laws = {law["knowledge_base_slug"]: law for law in snapshot["laws"]}
        report = repair_isolated_copy(
            args.source_directory,
            args.target_directory,
            laws,
            client_factory=_new_client,
        )
        _write_atomically(
            args.output,
            {
                "schema": "lexrag.stage8-vector-index-repair",
                "version": 1,
                "generated_at": datetime.now(UTC).isoformat(),
                "source_directory": str(args.source_directory.resolve()),
                "target_directory": str(args.target_directory.resolve()),
                "snapshot": {
                    "path": str(args.snapshot.resolve()),
                    "sha256": hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),
                    "as_of": snapshot["as_of"],
                },
                **report,
            },
        )
    except Exception as exc:
        print(f"stage8 vector repair failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
