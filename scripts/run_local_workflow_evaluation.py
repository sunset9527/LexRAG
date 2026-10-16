"""在一个 Python 进程中启动本地 API 并执行认证后的工作流验收。

Codex Desktop 的命令沙箱会隔离后台进程的 loopback 网络。本脚本以线程运行
Uvicorn，随后从同一进程注册一次性评测用户并调用通用工作流评测器，因此既保留
真实 HTTP、认证、检索、证据校验链路，也可在该环境中复现。
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.evaluate_workflow import run_workflow_evaluation


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本地启动 LexRAG 并执行工作流验收")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--api-key-env", default="LEXRAG_EVAL_API_KEY")
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--max-attempts", default=3, type=int)
    parser.add_argument("--review", type=Path, help="人工断言复核 JSON（可选）")
    parser.add_argument("--bypass-cache", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--startup-timeout", type=float, default=600.0)
    return parser


def _start_server() -> tuple[uvicorn.Server, threading.Thread]:
    from api import app

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
    )
    thread = threading.Thread(target=server.run, name="lexrag-eval-api", daemon=True)
    thread.start()
    return server, thread


def _wait_for_server(
    server: uvicorn.Server, thread: threading.Thread, timeout_seconds: float
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not server.started:
        if not thread.is_alive() or server.should_exit:
            raise RuntimeError("本地 API 在启动过程中提前退出")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"本地 API 未在 {timeout_seconds:.0f} 秒内就绪")
        time.sleep(0.25)

def _register_evaluation_user(client: httpx.Client) -> str:
    response = client.post(
        "http://127.0.0.1:8000/auth/register",
        json={
            "username": f"lexrag-eval-{uuid.uuid4().hex[:12]}",
            "password": f"{uuid.uuid4().hex}Aa1!",
        },
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("评测账号注册未返回访问令牌")
    return token


def main() -> int:
    args = _build_parser().parse_args()
    if not os.environ.get(args.api_key_env):
        print(f"缺少运行时环境变量 {args.api_key_env}")
        return 2

    print("正在启动本地 LexRAG API…", flush=True)
    server, thread = _start_server()
    token_env = "LEXRAG_EVAL_BEARER_TOKEN"
    try:
        _wait_for_server(server, thread, args.startup_timeout)
        print("本地 API 已就绪；创建隔离评测身份并执行单条冒烟…", flush=True)
        with httpx.Client(timeout=180.0) as client:
            token = _register_evaluation_user(client)
            # 先验证需要 LLM 调用的真实入口；失败时不启动 100 条批量评测。
            from src.evaluation.retrieval_evaluation import load_labels

            first_label = load_labels(args.dataset)[0]
            smoke = client.post(
                "http://127.0.0.1:8000/query",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": os.environ[args.api_key_env],
                    "X-Base-URL": args.base_url,
                    "X-Model": args.model,
                },
                json={
                    "query": first_label["query"],
                    "knowledge_base_ids": [first_label["knowledge_base_slug"]],
                    "config": {"cache_bypass": True},
                },
            )
            smoke.raise_for_status()
            if not smoke.json().get("verification_status"):
                raise RuntimeError("单条认证冒烟未返回引用校验状态")

        print("单条认证冒烟通过；开始 100 条无缓存工作流评测…", flush=True)
        os.environ[token_env] = token
        evaluation_args = SimpleNamespace(
            dataset=args.dataset,
            api_url="http://127.0.0.1:8000/query",
            api_key_env=args.api_key_env,
            auth_token_env=token_env,
            base_url=args.base_url,
            model=args.model,
            max_attempts=args.max_attempts,
            review=args.review,
            bypass_cache=args.bypass_cache,
            output=args.output,
        )
        exit_code = run_workflow_evaluation(evaluation_args)
        if exit_code == 0:
            print("100 条工作流评测完成。", flush=True)
        return exit_code
    except (httpx.HTTPError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"本地工作流评测失败: {exc}")
        return 2
    finally:
        os.environ.pop(token_env, None)
        server.should_exit = True
        thread.join(timeout=30.0)


if __name__ == "__main__":
    raise SystemExit(main())
