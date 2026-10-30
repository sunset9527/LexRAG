"""Run the optional blind Stage 8 Judge and emit credential-free JSONL rows."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.stage8_diagnostic_calibration import (  # noqa: E402
    Stage8DiagnosticCalibrationError,
    load_completed_answer_reviews,
)
from src.evaluation.stage8_judge_runner import JudgeCallable, run_judge_diagnostics  # noqa: E402

_PROMPT_VERSION = "stage8-diagnostic-judge-v2"
_JSON_JUDGE_SYSTEM_PROMPT = """You are a blind diagnostic Judge for a legal RAG answer.
Assess only evidence fidelity, question coverage, abstention appropriateness, and clarity.
Do not make an independent legal ruling and do not infer any human review verdict.
Return a single valid json object and nothing else, using this shape:
{"decision": true, "dimensions": {"evidence_fidelity": "supported", "coverage": "adequate", "abstention": "appropriate", "clarity": "clear"}}
The decision field must be a boolean. The dimensions object may contain concise string findings.
"""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--review-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=100)
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout-seconds", type=int, default=45)
    return parser.parse_args(argv)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_judge_messages(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    """Build an explicit JSON-mode prompt for OpenAI-compatible providers."""
    return [
        {"role": "system", "content": _JSON_JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Evaluate the following payload and return the required json object:\n"
            + json.dumps(payload, ensure_ascii=False),
        },
    ]


def _openai_judge(*, api_key: str, base_url: str, model: str, temperature: float, timeout: int) -> JudgeCallable:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)

    def evaluate(payload: dict[str, Any]) -> Mapping[str, Any]:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=build_judge_messages(payload),
        )
        content = response.choices[0].message.content
        if not isinstance(content, str):
            raise ValueError("empty judge response")
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("judge response is not an object")
        return value

    return evaluate


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    judge: JudgeCallable | None = None,
) -> int:
    args = parse_args(argv)
    environment = os.environ if environment is None else environment
    try:
        if args.expected_count < 1 or not 0 <= args.temperature <= 1 or args.timeout_seconds < 1:
            raise Stage8DiagnosticCalibrationError("Judge 运行参数无效")
        if args.output.resolve() in {args.review.resolve(), args.review_manifest.resolve()}:
            raise Stage8DiagnosticCalibrationError("输出路径不能覆盖输入工件")
        reviews = load_completed_answer_reviews(
            args.review,
            args.review_manifest,
            expected_count=args.expected_count,
        )
        api_key = environment.get("STAGE8_JUDGE_API_KEY", "")
        if not api_key:
            raise Stage8DiagnosticCalibrationError("缺少 STAGE8_JUDGE_API_KEY")
        safe_base_url = args.base_url
        safe_timeout = args.timeout_seconds
        if judge is None:
            from app.security.runtime_llm import RuntimeLLMPolicy
            from config import settings

            runtime = RuntimeLLMPolicy(settings).validate(
                base_url=args.base_url,
                model=args.model,
                allow_custom=False,
            )
            safe_base_url = runtime.base_url
            safe_timeout = min(args.timeout_seconds, runtime.timeout_seconds)
        active_judge = judge or _openai_judge(
            api_key=api_key,
            base_url=safe_base_url,
            model=args.model,
            temperature=args.temperature,
            timeout=safe_timeout,
        )
        results = run_judge_diagnostics(reviews, active_judge)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            "".join(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n" for result in results),
            encoding="utf-8",
        )
        _write_json(
            args.output.with_suffix(".config.json"),
            {
                "kind": "judge",
                "provider": "openai-compatible",
                "base_url": safe_base_url,
                "model": args.model,
                "temperature": args.temperature,
                "timeout_seconds": safe_timeout,
                "prompt_version": _PROMPT_VERSION,
            },
        )
    except (OSError, Stage8DiagnosticCalibrationError, ValueError) as exc:
        print(f"stage8 judge run failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"stage8 judge result: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
