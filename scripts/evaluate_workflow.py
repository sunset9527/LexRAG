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
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.retrieval_evaluation import load_labels  # noqa: E402
from src.evaluation.workflow_evaluation import evaluate_workflow_responses  # noqa: E402


def _load_reviews(path: Path | None) -> dict[str, bool]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(value, bool) for value in data.values()):
        raise ValueError("人工复核文件必须是 {样本ID: true|false} JSON 对象")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="执行真实 LexRAG v2.1 工作流验收")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--api-url", default="http://127.0.0.1:8001/query")
    parser.add_argument("--api-key-env", default="LEXRAG_EVAL_API_KEY")
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--review", type=Path, help="人工断言复核 JSON（可选）")
    parser.add_argument("--bypass-cache", action="store_true", help="评测时绕过 Redis 缓存")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"缺少运行时环境变量 {args.api_key_env}", file=sys.stderr)
        return 2
    try:
        labels = load_labels(args.dataset)
        reviews = _load_reviews(args.review)
        responses: dict[str, dict[str, Any]] = {}
        headers = {
            "X-API-Key": api_key,
            "X-Base-URL": args.base_url,
            "X-Model": args.model,
        }
        with httpx.Client(timeout=120.0) as client:
            for label in labels:
                started = time.perf_counter()
                response = client.post(
                    args.api_url,
                    headers=headers,
                    json={
                        "query": label["query"],
                        "knowledge_base_ids": [label["knowledge_base_slug"]],
                        "config": {"cache_bypass": args.bypass_cache},
                    },
                )
                response.raise_for_status()
                payload = response.json()
                payload["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
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


if __name__ == "__main__":
    raise SystemExit(main())
