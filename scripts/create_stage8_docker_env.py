"""Create an ignored, one-time environment file for isolated Stage 8 Docker acceptance."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from typing import Sequence


class Stage8DockerEnvironmentError(ValueError):
    """The isolated Docker acceptance environment cannot be created safely."""


def create_environment(output: Path, *, model_path: Path, web_port: int) -> Path:
    """Create a new environment file with random local-only credentials.

    The caller receives only the file path. Secret values are never returned or
    printed, and an existing file is never overwritten.
    """
    if not 1 <= web_port <= 65535:
        raise Stage8DockerEnvironmentError("端口无效")
    output.parent.mkdir(parents=True, exist_ok=True)
    values = {
        "MYSQL_DATABASE": "lexrag",
        "MYSQL_APP_USER": "lexrag",
        "MYSQL_ROOT_PASSWORD": secrets.token_urlsafe(32),
        "MYSQL_APP_PASSWORD": secrets.token_urlsafe(32),
        "JWT_SECRET_KEY": secrets.token_urlsafe(48),
        "LEXRAG_LOCAL_EMBEDDING_MODEL_PATH": str(model_path),
        "LEXRAG_WEB_PORT": str(web_port),
        "RUNTIME_LLM_TRUSTED_BASE_URLS": "https://api.deepseek.com",
        "MCP_DEMO_USER_ID": "1",
        "MCP_DEMO_ORGANIZATION_ID": "1",
    }
    content = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise Stage8DockerEnvironmentError("环境文件已存在，拒绝覆盖") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return output


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".env.docker.stage8"))
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--web-port", type=int, default=18081)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if not args.model_path.is_dir():
            raise Stage8DockerEnvironmentError("本地 BGE-M3 模型路径不存在")
        output = create_environment(args.output, model_path=args.model_path, web_port=args.web_port)
    except (OSError, Stage8DockerEnvironmentError) as exc:
        print(f"stage8 docker environment failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"stage8 docker environment: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
