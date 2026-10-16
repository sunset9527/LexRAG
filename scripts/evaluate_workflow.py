"""调用真实 /query 并生成 v2.1 工作流验收报告。

API Key 仅由运行时环境变量读取，绝不写入输出报告。
可选人工复核 JSON 为 {"sample-id": true|false}，用于断言支持率；缺复核时报告明确留空。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.retrieval_evaluation import load_labels  # noqa: E402
from src.evaluation.workflow_evaluation import evaluate_workflow_responses  # noqa: E402

T = TypeVar("T")


def build_request_headers(
    *, api_key: str, bearer_token: str, base_url: str, model: str
) -> dict[str, str]:
    """Build the headers required by the authenticated ``/query`` endpoint.

    ``X-API-Key`` is the runtime LLM credential consumed by the application;
    the bearer token authenticates the temporary evaluation user.  Keeping the
    two credentials separate avoids accidentally treating one as the other.
    """
    return {
        "X-API-Key": api_key,
        "X-Base-URL": base_url,
        "X-Model": model,
        "Authorization": f"Bearer {bearer_token}",
    }


def request_with_retries(
    request: Callable[[], T], *, max_attempts: int, sleep_seconds: float = 1.0
) -> tuple[T, int]:
    """Retry only transient transport and 5xx errors from the workflow API."""
    for attempt in range(1, max_attempts + 1):
        try:
            return request(), attempt
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code >= 500
            if not retryable or attempt == max_attempts:
                raise
        except httpx.TransportError:
            if attempt == max_attempts:
                raise
        time.sleep(sleep_seconds)
    raise RuntimeError("重试循环异常结束")


def _load_reviews(path: Path | None) -> dict[str, bool]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(value, bool) for value in data.values()):
        raise ValueError("人工复核文件必须是 {样本ID: true|false} JSON 对象")
    return data


def build_argument_parser() -> argparse.ArgumentParser:
    """Return the shared CLI parser for remote and local workflow evaluation."""
    parser = argparse.ArgumentParser(description="执行真实 LexRAG v2.1 工作流验收")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--api-url", default="http://127.0.0.1:8001/query")
    parser.add_argument("--api-key-env", default="LEXRAG_EVAL_API_KEY")
    parser.add_argument(
        "--auth-token-env",
        default="LEXRAG_EVAL_BEARER_TOKEN",
        help="存放评测用户 JWT 的运行时环境变量",
    )
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--max-attempts", default=3, type=int, help="单条请求最大尝试次数")
    parser.add_argument("--review", type=Path, help="人工断言复核 JSON（可选）")
    parser.add_argument("--bypass-cache", action="store_true", help="评测时绕过 Redis 缓存")
    parser.add_argument("--output", required=True, type=Path)
    return parser


def run_workflow_evaluation(args: argparse.Namespace) -> int:
    """Execute the authenticated requests and persist only non-secret metrics."""

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"缺少运行时环境变量 {args.api_key_env}", file=sys.stderr)
        return 2
    bearer_token = os.environ.get(args.auth_token_env)
    if not bearer_token:
        print(f"缺少运行时环境变量 {args.auth_token_env}", file=sys.stderr)
        return 2
    try:
        labels = load_labels(args.dataset)
        if args.max_attempts < 1:
            raise ValueError("--max-attempts 必须大于等于 1")
        reviews = _load_reviews(args.review)
        responses: dict[str, dict[str, Any]] = {}
        headers = build_request_headers(
            api_key=api_key,
            bearer_token=bearer_token,
            base_url=args.base_url,
            model=args.model,
        )
        with httpx.Client(timeout=120.0) as client:
            for label in labels:
                started = time.perf_counter()
                query = label["query"]
                knowledge_base_slug = label["knowledge_base_slug"]

                def issue_request(
                    query: str = query, knowledge_base_slug: str = knowledge_base_slug
                ) -> httpx.Response:
                    response = client.post(
                        args.api_url,
                        headers=headers,
                        json={
                            "query": query,
                            "knowledge_base_ids": [knowledge_base_slug],
                            "config": {"cache_bypass": args.bypass_cache},
                        },
                    )
                    response.raise_for_status()
                    return response

                response, request_attempts = request_with_retries(
                    issue_request,
                    max_attempts=args.max_attempts,
                )
                payload = response.json()
                payload["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
                payload.setdefault("metadata", {})["evaluation_request_attempts"] = request_attempts
                if label["id"] in reviews:
                    payload["human_assertion_review"] = reviews[label["id"]]
                responses[label["id"]] = payload
        report = evaluate_workflow_responses(labels, responses)
        report["dataset"] = str(args.dataset)
        report["api_url"] = args.api_url
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except (OSError, ValueError, json.JSONDecodeError, httpx.HTTPError) as exc:
        print(f"工作流评测失败: {exc}", file=sys.stderr)
        return 2


def main() -> int:
    return run_workflow_evaluation(build_argument_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
