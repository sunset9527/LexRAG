"""Run the supported Stage 8 Ragas metrics with safe, hash-bound artifacts.

Only the process-local ``STAGE8_RAGAS_API_KEY`` is read. It is never written
to the JSONL result, the configuration record, or the summary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.stage8_diagnostic_calibration import (  # noqa: E402
    Stage8DiagnosticCalibrationError,
    load_completed_answer_reviews,
)
from src.evaluation.stage8_ragas_input import materialize_ragas_records  # noqa: E402
from src.evaluation.stage8_ragas_runner import RagasEvaluator, _validate_scores, run_ragas_diagnostics  # noqa: E402

_DEFAULT_BASE_URL = "https://api.deepseek.com"
_SUPPORTED_BASE_URLS = {_DEFAULT_BASE_URL}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--review-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Ragas JSONL result path")
    parser.add_argument("--expected-count", type=int, default=100)
    parser.add_argument("--limit", type=int, help="Run only the first N records as a non-release smoke test")
    parser.add_argument("--resume-from", type=Path, help="Retry only execution errors from a complete prior result JSONL")
    parser.add_argument("--base-url", default=_DEFAULT_BASE_URL)
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--max-retries", type=int, default=2)
    return parser.parse_args(argv)


def _artifact(path: Path) -> dict[str, str]:
    return {"path": path.name, "sha256": sha256(path.read_bytes()).hexdigest()}


def _write_json_atomically(path: Path, value: Any, *, jsonl: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            if jsonl:
                for row in value:
                    stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            else:
                json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_runtime_options(args: argparse.Namespace) -> None:
    if args.expected_count < 1 or (args.limit is not None and args.limit < 1):
        raise Stage8DiagnosticCalibrationError("样本数量必须为正数")
    if not 0 <= args.temperature <= 1 or args.timeout_seconds < 1 or not 0 <= args.max_retries <= 5:
        raise Stage8DiagnosticCalibrationError("Ragas 运行参数无效")
    if args.resume_from and args.limit:
        raise Stage8DiagnosticCalibrationError("恢复执行不能同时指定 --limit")
    parsed = urlparse(args.base_url)
    if args.base_url.rstrip("/") not in _SUPPORTED_BASE_URLS or parsed.scheme != "https" or not parsed.netloc:
        raise Stage8DiagnosticCalibrationError("Ragas 评估端点不在受信任列表")


def _build_ragas_evaluator(
    *, api_key: str, base_url: str, model: str, temperature: float, timeout_seconds: int, max_retries: int
) -> tuple[RagasEvaluator, str]:
    """Create the optional real-provider evaluator only after validation succeeds."""
    try:
        import ragas
        from langchain_openai import ChatOpenAI
        from ragas import EvaluationDataset, evaluate
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference
    except ImportError as exc:
        raise Stage8DiagnosticCalibrationError("Ragas 专用环境缺少受支持依赖") from exc

    chat_model = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        timeout=timeout_seconds,
        max_retries=max_retries,
    )
    ragas_llm = LangchainLLMWrapper(chat_model)
    metrics = [
        Faithfulness(llm=ragas_llm),
        LLMContextPrecisionWithoutReference(name="context_precision_without_reference", llm=ragas_llm),
    ]

    def evaluate_one(record: Mapping[str, Any]) -> Mapping[str, float]:
        dataset = EvaluationDataset.from_list(
            [
                {
                    "user_input": record["user_input"],
                    "response": record["response"],
                    "retrieved_contexts": record["retrieved_contexts"],
                }
            ]
        )
        result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=ragas_llm,
            raise_exceptions=True,
            show_progress=False,
            allow_nest_asyncio=False,
        )
        if len(result.scores) != 1:
            raise ValueError("Ragas 返回的样本数不匹配")
        return result.scores[0]

    return evaluate_one, str(ragas.__version__)


def _load_prior_results(path: Path, expected_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Load a complete prior run whose successes can safely be reused."""
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise Stage8DiagnosticCalibrationError("无法读取 Ragas 恢复结果") from exc
    expected = set(expected_ids)
    prior: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise Stage8DiagnosticCalibrationError("Ragas 恢复结果格式错误")
        identifier = str(row.get("id", ""))
        if not identifier or identifier in prior or identifier not in expected:
            raise Stage8DiagnosticCalibrationError("Ragas 恢复结果 ID 无效或重复")
        status = row.get("status")
        if status == "completed":
            scores = row.get("scores")
            if not isinstance(scores, Mapping):
                raise Stage8DiagnosticCalibrationError("Ragas 恢复结果缺少分数")
            prior[identifier] = {"id": identifier, "status": "completed", "scores": _validate_scores(scores)}
        elif status == "execution_error" and isinstance(row.get("error_type"), str):
            prior[identifier] = {"id": identifier, "status": "execution_error", "error_type": row["error_type"]}
        else:
            raise Stage8DiagnosticCalibrationError("Ragas 恢复结果状态无效")
    if set(prior) != expected:
        raise Stage8DiagnosticCalibrationError("Ragas 恢复结果并非完整样本集")
    return prior


def _combine_recovery_results(
    records: Sequence[Mapping[str, Any]],
    prior: Mapping[str, Mapping[str, Any]],
    retry_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    retried = {str(row["id"]): dict(row) for row in retry_rows}
    expected_retry_ids = {str(record["id"]) for record in records if prior[str(record["id"])]["status"] == "execution_error"}
    if set(retried) != expected_retry_ids:
        raise Stage8DiagnosticCalibrationError("Ragas 补跑结果不完整")
    return [
        dict(retried[identifier]) if prior[identifier]["status"] == "execution_error" else dict(prior[identifier])
        for identifier in (str(record["id"]) for record in records)
    ]


def _build_summary(
    *,
    results: Sequence[Mapping[str, Any]],
    materialized: Mapping[str, Any],
    review_path: Path,
    manifest_path: Path,
    output_path: Path,
    selected_count: int,
    total_count: int,
    recovery: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    completed = [row for row in results if row["status"] == "completed"]
    errors = [str(row["id"]) for row in results if row["status"] == "execution_error"]
    means: dict[str, float | None] = {}
    for metric in materialized["supported_metrics"]:
        values = [float(row["scores"][metric]) for row in completed if metric in row["scores"]]
        means[metric] = sum(values) / len(values) if values else None
    status = "COMPLETE" if selected_count == total_count and not errors else "INCOMPLETE"
    if selected_count != total_count:
        status = "PARTIAL"
    summary = {
        "schema": "lexrag.stage8-ragas-diagnostic",
        "version": 1,
        "status": status,
        "counts": {"total_reviewed": total_count, "selected": selected_count, "completed": len(completed), "execution_errors": len(errors)},
        "metric_means": means,
        "error_ids": errors,
        "supported_metrics": materialized["supported_metrics"],
        "unsupported_metrics": materialized["unsupported_metrics"],
        "unsupported_metric_reasons": materialized["unsupported_metric_reasons"],
        "inputs": {"review": _artifact(review_path), "review_manifest": _artifact(manifest_path), "results": _artifact(output_path)},
    }
    if recovery is not None:
        summary["recovery"] = dict(recovery)
    return summary


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    evaluator: RagasEvaluator | None = None,
    ragas_version: str | None = None,
) -> int:
    args = parse_args(argv)
    environment = os.environ if environment is None else environment
    try:
        _validate_runtime_options(args)
        output_paths = {args.output.resolve(), args.output.with_suffix(".config.json").resolve(), args.output.with_suffix(".summary.json").resolve()}
        source_paths = {args.review.resolve(), args.review_manifest.resolve()}
        if args.resume_from:
            source_paths.add(args.resume_from.resolve())
        if output_paths & source_paths:
            raise Stage8DiagnosticCalibrationError("输出路径不能覆盖输入工件")
        api_key = environment.get("STAGE8_RAGAS_API_KEY", "")
        if not api_key:
            raise Stage8DiagnosticCalibrationError("缺少 STAGE8_RAGAS_API_KEY")
        reviews = load_completed_answer_reviews(args.review, args.review_manifest, expected_count=args.expected_count)
        materialized = materialize_ragas_records(reviews)
        prior = _load_prior_results(args.resume_from, [record["id"] for record in materialized["records"]]) if args.resume_from else None
        selected_records = (
            [record for record in materialized["records"] if prior[record["id"]]["status"] == "execution_error"]
            if prior is not None
            else materialized["records"][: args.limit] if args.limit else materialized["records"]
        )
        active_evaluator = evaluator
        active_ragas_version = ragas_version
        if active_evaluator is None:
            active_evaluator, active_ragas_version = _build_ragas_evaluator(
                api_key=api_key,
                base_url=args.base_url.rstrip("/"),
                model=args.model,
                temperature=args.temperature,
                timeout_seconds=args.timeout_seconds,
                max_retries=args.max_retries,
            )
        retry_results = run_ragas_diagnostics(selected_records, active_evaluator)
        results = _combine_recovery_results(materialized["records"], prior, retry_results) if prior is not None else retry_results
        _write_json_atomically(args.output, results, jsonl=True)
        _write_json_atomically(
            args.output.with_suffix(".config.json"),
            {
                "kind": "ragas",
                "ragas_version": active_ragas_version or "injected-test-evaluator",
                "base_url": args.base_url.rstrip("/"),
                "model": args.model,
                "temperature": args.temperature,
                "timeout_seconds": args.timeout_seconds,
                "max_retries": args.max_retries,
            },
        )
        _write_json_atomically(
            args.output.with_suffix(".summary.json"),
            _build_summary(
                results=results,
                materialized=materialized,
                review_path=args.review,
                manifest_path=args.review_manifest,
                output_path=args.output,
                selected_count=len(results),
                total_count=len(materialized["records"]),
                recovery=(
                    {"reused_completed": len(materialized["records"]) - len(selected_records), "retried": len(selected_records)}
                    if prior is not None
                    else None
                ),
            ),
        )
    except (OSError, Stage8DiagnosticCalibrationError, ValueError) as exc:
        print(f"stage8 Ragas run failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"stage8 Ragas result: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
