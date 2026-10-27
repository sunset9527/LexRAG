"""Reconcile a reviewed Stage 8 JSONL queue without changing candidate records."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.stage8_review_reconciliation import (
    Stage8ReviewReconciliationError,
    reconcile_review_queue,
)


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pending", required=True, type=Path, help="untouched pending JSONL queue")
    parser.add_argument("--reviewed", required=True, type=Path, help="human-reviewed JSONL queue")
    parser.add_argument("--output", type=Path, help="optional JSON summary output path")
    return parser


def _write_json_atomically(output: Path, summary: object) -> None:
    payload = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        temporary_path.write_text(payload, encoding="utf-8")
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    args = _arguments().parse_args(argv)
    try:
        summary = reconcile_review_queue(args.pending, args.reviewed)
    except Stage8ReviewReconciliationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.output is None:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    try:
        _write_json_atomically(args.output, summary)
    except OSError as exc:
        print(f"无法写入审核对账摘要: {args.output}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
