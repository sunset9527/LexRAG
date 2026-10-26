"""Write a read-only Stage 8 legacy evaluation-dataset intake audit."""

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

from src.evaluation.stage8_intake_audit import Stage8IntakeAuditError, audit_stage8_intake


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path, help="legacy JSONL dataset path")
    parser.add_argument("--output", required=True, type=Path, help="audit report JSON path")
    return parser


def _write_report_atomically(output: Path, report: object) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
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
        report = audit_stage8_intake(args.dataset)
    except Stage8IntakeAuditError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        _write_report_atomically(args.output, report)
    except OSError as exc:
        print(f"无法写入审计报告: {args.output}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
