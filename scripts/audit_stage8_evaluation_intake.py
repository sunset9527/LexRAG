"""Write a read-only Stage 8 legacy evaluation-dataset intake audit."""

from __future__ import annotations

import argparse
import json
import sys
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


def main(argv: list[str] | None = None) -> int:
    args = _arguments().parse_args(argv)
    try:
        report = audit_stage8_intake(args.dataset)
    except Stage8IntakeAuditError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"无法写入审计报告: {args.output}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
