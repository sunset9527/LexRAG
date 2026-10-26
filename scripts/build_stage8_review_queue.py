"""Build the pending-only Stage 8 candidate review queue as UTF-8 JSONL."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.stage8_review_queue import (
    Stage8ReviewQueueError,
    compose_stage8_review_queue,
)


class _DuplicateJsonKeyError(ValueError):
    """A JSON object has duplicate keys."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(key)
        result[key] = value
    return result


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", required=True, type=Path, help="legacy seed JSONL path")
    parser.add_argument(
        "--hard-candidates", required=True, type=Path, help="hard candidate JSONL path"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="pending review queue JSONL path"
    )
    parser.add_argument("--legacy-question-type", default="direct_lookup")
    parser.add_argument("--legacy-difficulty", default="baseline")
    parser.add_argument(
        "--legacy-should-abstain",
        action="store_true",
        help="mark every legacy seed as a proposed abstention candidate",
    )
    return parser


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise Stage8ReviewQueueError(f"无法读取 review queue 输入: {path}") from exc

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line, object_pairs_hook=_reject_duplicate_json_keys)
        except (_DuplicateJsonKeyError, json.JSONDecodeError) as exc:
            raise Stage8ReviewQueueError(f"{path} 第 {line_number} 行不是合法 JSON 对象") from exc
        if not isinstance(row, dict):
            raise Stage8ReviewQueueError(f"{path} 第 {line_number} 行必须是 JSON 对象")
        rows.append(row)
    return rows


def _write_jsonl_atomically(output: Path, rows: list[dict[str, Any]]) -> None:
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
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
        queue = compose_stage8_review_queue(
            _load_jsonl(args.legacy),
            _load_jsonl(args.hard_candidates),
            legacy_question_type=args.legacy_question_type,
            legacy_difficulty=args.legacy_difficulty,
            legacy_should_abstain=args.legacy_should_abstain,
        )
    except Stage8ReviewQueueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        _write_jsonl_atomically(args.output, queue)
    except OSError as exc:
        print(f"无法写入 review queue: {args.output}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
