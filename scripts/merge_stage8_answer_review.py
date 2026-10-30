"""Create one hash-bound, pending-human-review artifact from successful Stage 8 runs."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.stage8_answer_review_merge import (  # noqa: E402
    Stage8AnswerReviewMergeError,
    merge_answer_review_runs,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        type=Path,
        default=PROJECT_ROOT / "data/evaluation/stage8/stage8_answer_review_sample_100.jsonl",
    )
    parser.add_argument("--initial-run", type=Path, required=True)
    parser.add_argument("--resume-run", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "reports/evaluation/stage8/answer_reviews/stage8_answer_review_merged_100.jsonl",
    )
    return parser.parse_args(argv)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise Stage8AnswerReviewMergeError(f"无法读取 JSONL: {path.name}") from exc
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise Stage8AnswerReviewMergeError(f"JSONL 为空或包含非对象行: {path.name}")
    return rows


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        sample_records = _read_jsonl(args.sample)
        initial_records = _read_jsonl(args.initial_run)
        resume_records = _read_jsonl(args.resume_run)
        rows = merge_answer_review_runs(
            sample_records,
            initial_records,
            resume_records,
            source_names=(args.initial_run.name, args.resume_run.name),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        manifest_path = args.output.with_suffix(".manifest.json")
        _write_json(
            manifest_path,
            {
                "schema": "lexrag.stage8-answer-review-merged",
                "version": 1,
                "source": {
                    "sample": {"path": args.sample.name, "sha256": _sha256(args.sample)},
                    "initial_run": {"path": args.initial_run.name, "sha256": _sha256(args.initial_run)},
                    "resume_run": {"path": args.resume_run.name, "sha256": _sha256(args.resume_run)},
                },
                "result": {"path": args.output.name, "sha256": _sha256(args.output)},
                "counts": {"completed": len(rows), "total": len(sample_records)},
            },
        )
    except (OSError, Stage8AnswerReviewMergeError) as exc:
        print(f"stage8 answer-review merge failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"stage8 answer-review merge complete: completed={len(rows)} result={args.output.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
