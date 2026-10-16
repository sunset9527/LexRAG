"""Run LexRAG's reproducible engineering quality gates and write an auditable report."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = ROOT / "frontend"
RUFF_PATHS = ["api.py", "app", "src", "scripts", "tests", "alembic"]


@dataclass(frozen=True)
class CommandResult:
    name: str
    command: list[str]
    return_code: int
    duration_seconds: float
    output: str


def _output_tail(output: str, limit: int = 4000) -> str:
    return output[-limit:].strip()


def package_manager_command(platform_name: str | None = None) -> str:
    """Return the executable that `subprocess` can launch on each platform."""
    return "npm.cmd" if (platform_name or os.name) == "nt" else "npm"


def build_report(results: Sequence[CommandResult]) -> dict:
    commands = [
        {
            **asdict(result),
            "duration_seconds": round(result.duration_seconds, 3),
            "output_tail": _output_tail(result.output),
            "output": None,
        }
        for result in results
    ]
    failed_commands = sum(result.return_code != 0 for result in results)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "passed" if failed_commands == 0 else "failed",
        "summary": {
            "total_commands": len(results),
            "passed_commands": len(results) - failed_commands,
            "failed_commands": failed_commands,
            "total_duration_seconds": round(sum(result.duration_seconds for result in results), 3),
        },
        "commands": commands,
    }


def run_command(name: str, command: list[str], cwd: Path) -> CommandResult:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return CommandResult(
        name=name,
        command=command,
        return_code=completed.returncode,
        duration_seconds=time.perf_counter() - started,
        output=output,
    )


def build_quality_commands(
    *, output_dir: Path, skip_build: bool = False
) -> list[tuple[str, list[str], Path]]:
    """Return the maintained quality checks in the order they are executed."""
    coverage_path = output_dir / "coverage.json"
    commands = [
        (
            "ruff",
            [sys.executable, "-m", "ruff", "check", *RUFF_PATHS],
            ROOT,
        ),
        (
            "backend pytest",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests",
                "-q",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(output_dir / "pytest-tmp"),
                "--cov=app",
                "--cov=src",
                f"--cov-report=json:{coverage_path}",
                "--cov-report=term",
            ],
            ROOT,
        ),
        (
            "frontend node tests",
            ["node", "--test", "tests/lawPresentation.test.mjs", "tests/visualSystem.test.mjs"],
            FRONTEND_ROOT,
        ),
    ]
    if not skip_build:
        commands.append(
            (
                "frontend production build",
                [package_manager_command(), "run", "build"],
                FRONTEND_ROOT,
            )
        )
    return commands


def write_markdown(report: dict, output_path: Path) -> None:
    summary = report["summary"]
    lines = [
        "# LexRAG 工程质量报告",
        "",
        f"- 生成时间（UTC）：{report['generated_at']}",
        f"- 总体状态：**{report['status']}**",
        f"- 质量门禁：{summary['passed_commands']}/{summary['total_commands']} 通过",
        f"- 总耗时：{summary['total_duration_seconds']} 秒",
        "",
        "| 门禁 | 状态 | 耗时（秒） | 命令 |",
        "| --- | --- | ---: | --- |",
    ]
    for command in report["commands"]:
        status = "通过" if command["return_code"] == 0 else "失败"
        rendered_command = " ".join(command["command"])
        lines.append(
            f"| {command['name']} | {status} | {command['duration_seconds']} | `{rendered_command}` |"
        )
    lines.append("")
    lines.append(
        "说明：本报告只记录命令、退出码、耗时及截断输出；不会写入运行时 API Key 或法律咨询原文。"
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 LexRAG 后端、前端与构建质量门禁")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "quality")
    parser.add_argument("--skip-build", action="store_true", help="仅运行测试，不执行前端生产构建")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    commands = build_quality_commands(output_dir=args.output_dir, skip_build=args.skip_build)

    results = [run_command(name, command, cwd) for name, command, cwd in commands]
    report = build_report(results)
    (args.output_dir / "latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_markdown(report, args.output_dir / "latest.md")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
