"""Run frozen Stage 8 answer-review samples through the authenticated query API."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, sleep as sleep_for
from typing import Any


class AnswerReviewRunnerError(ValueError):
    """Required local-only runtime credentials or runner options are invalid."""


@dataclass(frozen=True)
class AnswerReviewRunConfig:
    timeout_seconds: float = 90.0
    max_attempts: int = 2
    minimum_interval_seconds: float = 1.1

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise AnswerReviewRunnerError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise AnswerReviewRunnerError("max_attempts must be at least one")
        if self.minimum_interval_seconds < 0:
            raise AnswerReviewRunnerError("minimum_interval_seconds must not be negative")


QueryRequest = Callable[[dict[str, Any], dict[str, str], float], dict[str, Any]]


@dataclass(frozen=True)
class AnswerReviewArtifacts:
    result_path: Path
    manifest_path: Path


def _is_retryable_request_error(exc: Exception) -> bool:
    """Retry only transport faults and explicit rate limits, never malformed requests."""
    error_code = getattr(exc, "error_code", None)
    if isinstance(error_code, str):
        return error_code in {"HTTP_429", "NETWORK_ERROR", "INVALID_JSON_RESPONSE"}
    return isinstance(exc, (TimeoutError, ConnectionError, ConnectionAbortedError))


def build_runtime_headers(environment: Mapping[str, str]) -> dict[str, str]:
    """Build authenticated API headers from process-local environment values only."""

    api_key = environment.get("STAGE8_LLM_API_KEY", "").strip()
    token = environment.get("STAGE8_AUTH_TOKEN", "").strip()
    missing = [
        name
        for name, value in (("STAGE8_LLM_API_KEY", api_key), ("STAGE8_AUTH_TOKEN", token))
        if not value
    ]
    if missing:
        raise AnswerReviewRunnerError(f"missing required environment variable: {', '.join(missing)}")
    authorization = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    return {"Authorization": authorization, "X-API-Key": api_key}


def run_answer_review_records(
    records: Sequence[Mapping[str, Any]],
    request: QueryRequest,
    *,
    headers: Mapping[str, str],
    config: AnswerReviewRunConfig,
    sleep: Callable[[float], None] = sleep_for,
) -> list[dict[str, Any]]:
    """Return one completed or explicit execution-error record for every sample."""

    results: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if index and config.minimum_interval_seconds:
            sleep(config.minimum_interval_seconds)
        sample_id = str(record["id"])
        payload = {
            "query": str(record["question"]),
            "knowledge_base_ids": list(record["expected_knowledge_base_slugs"]),
            "config": {"cache_bypass": True},
        }
        started = perf_counter()
        for attempt in range(1, config.max_attempts + 1):
            try:
                response = request(payload, dict(headers), config.timeout_seconds)
            except Exception as exc:
                if attempt == config.max_attempts or not _is_retryable_request_error(exc):
                    results.append(
                        {
                            "sample_id": sample_id,
                            "status": "execution_error",
                            "attempts": attempt,
                            "error_type": str(
                                getattr(exc, "error_code", type(exc).__name__)
                            ),
                            "latency_ms": round((perf_counter() - started) * 1000, 3),
                        }
                    )
                    break
                continue
            results.append(
                {
                    "sample_id": sample_id,
                    "status": "completed",
                    "attempts": attempt,
                    "latency_ms": round((perf_counter() - started) * 1000, 3),
                    "answer": str(response.get("answer", "")),
                    "citations": list(response.get("citations", [])),
                    "verification_status": str(response.get("verification_status", "")),
                    "verification_issues": list(response.get("verification_issues", [])),
                    "workflow_trace": list(response.get("metadata", {}).get("workflow_trace", [])),
                }
            )
            break
    return results


def write_answer_review_artifacts(
    *,
    output_directory: Path,
    sample_records: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    run_metadata: Mapping[str, Any],
    timestamp: str,
) -> AnswerReviewArtifacts:
    """Write a credential-free JSONL review artifact and its integrity manifest."""

    result_by_id = {str(item["sample_id"]): item for item in results}
    if len(result_by_id) != len(sample_records):
        raise AnswerReviewRunnerError("result count does not match the review sample")
    output_directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for sample in sample_records:
        sample_id = str(sample["id"])
        result = result_by_id.get(sample_id)
        if result is None:
            raise AnswerReviewRunnerError(f"missing result for sample: {sample_id}")
        rows.append(
            {
                "sample_id": sample_id,
                "question": str(sample["question"]),
                "question_type": str(sample.get("question_type", "")),
                "difficulty": str(sample.get("difficulty", "")),
                "expected_knowledge_base_slugs": list(
                    sample.get("expected_knowledge_base_slugs", [])
                ),
                "relevant_article_ids": list(sample.get("relevant_article_ids", [])),
                "should_abstain": bool(sample.get("should_abstain", False)),
                **dict(result),
            }
        )
    result_path = output_directory / f"stage8_answer_review_run_{timestamp}.jsonl"
    with result_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    result_bytes = result_path.read_bytes()
    safe_metadata = {
        str(key): value
        for key, value in run_metadata.items()
        if "key" not in str(key).lower()
        and "token" not in str(key).lower()
        and "authorization" not in str(key).lower()
        and "secret" not in str(key).lower()
    }
    counts = {
        "completed": sum(row.get("status") == "completed" for row in rows),
        "execution_error": sum(row.get("status") == "execution_error" for row in rows),
        "total": len(rows),
    }
    manifest = {
        "schema": "lexrag.stage8-answer-review-run",
        "version": 1,
        "run": safe_metadata,
        "result": {"path": result_path.name, "sha256": sha256(result_bytes).hexdigest()},
        "counts": counts,
    }
    manifest_path = output_directory / f"stage8_answer_review_run_{timestamp}.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return AnswerReviewArtifacts(result_path=result_path, manifest_path=manifest_path)
