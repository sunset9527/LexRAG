"""Create a hash-bound Stage 8 Judge diagnostic calibration report.

This command consumes already materialized evaluator rows. It deliberately does
not read credentials or contact an LLM provider, so a report can be reproduced
and inspected without exposing secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.stage8_diagnostic_calibration import (  # noqa: E402
    Stage8DiagnosticCalibrationError,
    build_calibration_report,
    load_completed_answer_reviews,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--review-manifest", type=Path, required=True)
    parser.add_argument("--evaluator-results", type=Path, required=True)
    parser.add_argument("--evaluator-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=100)
    return parser.parse_args(argv)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Stage8DiagnosticCalibrationError("无法读取评估器配置") from exc
    if not isinstance(value, dict):
        raise Stage8DiagnosticCalibrationError("评估器配置不是对象")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise Stage8DiagnosticCalibrationError("无法读取评估结果") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise Stage8DiagnosticCalibrationError("评估结果为空或格式错误")
    return rows


def _artifact(path: Path) -> dict[str, str]:
    return {"path": path.name, "sha256": sha256(path.read_bytes()).hexdigest()}


def _write_atomically(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.expected_count < 1:
            raise Stage8DiagnosticCalibrationError("审核样本数必须为正数")
        source_paths = {
            args.review.resolve(),
            args.review_manifest.resolve(),
            args.evaluator_results.resolve(),
            args.evaluator_config.resolve(),
        }
        if args.output.resolve() in source_paths:
            raise Stage8DiagnosticCalibrationError("输出路径不能覆盖输入工件")
        reviews = load_completed_answer_reviews(
            args.review,
            args.review_manifest,
            expected_count=args.expected_count,
        )
        evaluator_rows = _load_jsonl(args.evaluator_results)
        evaluator_config = _load_json(args.evaluator_config)
        report = build_calibration_report(reviews, evaluator_rows, evaluator=evaluator_config)
        report["inputs"] = {
            "review": _artifact(args.review),
            "review_manifest": _artifact(args.review_manifest),
            "evaluator_results": _artifact(args.evaluator_results),
            "evaluator_config": _artifact(args.evaluator_config),
        }
        _write_atomically(args.output, report)
    except (OSError, Stage8DiagnosticCalibrationError) as exc:
        print(f"stage8 diagnostic calibration failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"stage8 diagnostic calibration report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
