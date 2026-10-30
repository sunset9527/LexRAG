"""Run the frozen Stage 8 answer-review sample against a local authenticated API."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.stage8_answer_review_runner import (  # noqa: E402
    AnswerReviewRunConfig,
    AnswerReviewRunnerError,
    QueryRequest,
    build_runtime_headers,
    run_answer_review_records,
    write_answer_review_artifacts,
)


class QueryApiRequestError(RuntimeError):
    """A query API failure represented without response content or credentials."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        type=Path,
        default=PROJECT_ROOT / "data/evaluation/stage8/stage8_answer_review_sample_100.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "reports/evaluation/stage8/answer_reviews",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="Local LexRAG API base URL; credentials stay in process environment.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--minimum-interval-seconds", type=float, default=1.1)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N frozen sample records (for a preflight smoke test).",
    )
    parser.add_argument("--timestamp", default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnswerReviewRunnerError(f"invalid sample JSONL at line {line_number}") from exc
        if not isinstance(record, dict):
            raise AnswerReviewRunnerError(f"sample row {line_number} is not an object")
        records.append(record)
    if not records:
        raise AnswerReviewRunnerError("answer-review sample is empty")
    return records


def _build_http_request(api_base_url: str) -> QueryRequest:
    endpoint = f"{api_base_url.rstrip('/')}/query"

    def request(payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = Request(
            endpoint,
            data=body,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=timeout) as response:  # noqa: S310 - explicit local CLI URL
                raw_response = response.read()
        except HTTPError as exc:
            raise QueryApiRequestError(f"HTTP_{exc.code}") from exc
        except URLError as exc:
            raise QueryApiRequestError("NETWORK_ERROR") from exc
        try:
            decoded = json.loads(raw_response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise QueryApiRequestError("INVALID_JSON_RESPONSE") from exc
        if not isinstance(decoded, dict):
            raise QueryApiRequestError("INVALID_RESPONSE_SHAPE")
        return decoded

    return request


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    request: QueryRequest | None = None,
) -> int:
    args = parse_args(argv)
    try:
        headers = build_runtime_headers(os.environ if environment is None else environment)
        records = _load_jsonl(args.sample)
        if args.limit is not None:
            if args.limit < 1:
                raise AnswerReviewRunnerError("limit must be at least one")
            records = records[: args.limit]
        config = AnswerReviewRunConfig(
            timeout_seconds=args.timeout_seconds,
            max_attempts=args.max_attempts,
            minimum_interval_seconds=args.minimum_interval_seconds,
        )
    except (OSError, AnswerReviewRunnerError) as exc:
        print(f"stage8 answer-review runner failed: {type(exc).__name__}", file=sys.stderr)
        return 2

    timestamp = args.timestamp or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results = run_answer_review_records(
        records,
        request or _build_http_request(args.api_base_url),
        headers=headers,
        config=config,
    )
    artifacts = write_answer_review_artifacts(
        output_directory=args.output_dir,
        sample_records=records,
        results=results,
        run_metadata={
            "api_base_url": args.api_base_url,
            "max_attempts": config.max_attempts,
            "minimum_interval_seconds": config.minimum_interval_seconds,
            "record_limit": args.limit,
            "sample_sha256": sha256(args.sample.read_bytes()).hexdigest(),
            "timeout_seconds": config.timeout_seconds,
        },
        timestamp=timestamp,
    )
    completed = sum(result["status"] == "completed" for result in results)
    print(
        f"stage8 answer-review run complete: completed={completed} "
        f"execution_errors={len(results) - completed} result={artifacts.result_path.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
