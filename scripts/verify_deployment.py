"""Generate safe evidence for an isolated Stage 3 Compose acceptance run.

The default is a dry run.  Docker is called only after an operator supplies an
explicit project name and the ``--execute`` flag.  This tool never calls
``docker compose down``, deletes volumes, or injects a fault automatically.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PROJECT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")
URL_PATTERN = re.compile(r"(?:https?|redis|mysql\+pymysql)://[^\s\"'<>]+", re.I)
WINDOWS_PATH_PATTERN = re.compile(r"(?<![\w:])[A-Za-z]:[\\/][^\s\"'<>]+")
UNIX_PATH_PATTERN = re.compile(r"(?<![\w:])/(?:[^\s\"'<>]+)")
ASSIGNMENT_PATTERN = re.compile(
    r"(?i)((?:[A-Za-z_][A-Za-z0-9_]*_)?(?:password|token|secret|api[_-]?key|key|jwt|cookie)(?:_[A-Za-z0-9_]+)?)"
    r"\s*([:=])\s*[^\s,;]+"
)
BEARER_PATTERN = re.compile(r"(?i)\b(authorization\s*:\s*bearer)\s+[^\s,;]+")


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


CommandExecutor = Callable[[list[str]], CommandResult]


def validate_project_name(project_name: str) -> str:
    """Require a non-default, Compose-safe name so local data stay isolated."""
    if not project_name:
        raise ValueError("an explicit isolated Docker Compose project name is required")
    if project_name == "lexrag":
        raise ValueError("the reserved project name 'lexrag' cannot be used for acceptance")
    if not PROJECT_NAME_PATTERN.fullmatch(project_name):
        raise ValueError("project name must be lowercase, 3-63 characters, and Compose-safe")
    return project_name


def redact_text(value: str) -> str:
    """Remove credential, endpoint, and host-path material from evidence."""
    redacted = URL_PATTERN.sub("[REDACTED_URL]", value)
    redacted = ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED_SECRET]", redacted)
    redacted = BEARER_PATTERN.sub(r"\1 [REDACTED_SECRET]", redacted)
    redacted = WINDOWS_PATH_PATTERN.sub("[REDACTED_HOST_PATH]", redacted)
    return UNIX_PATH_PATTERN.sub("[REDACTED_HOST_PATH]", redacted)


def _default_executor(command: list[str]) -> CommandResult:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class DeploymentVerifier:
    """Run non-destructive Compose checks and persist redacted evidence."""

    def __init__(
        self,
        *,
        project_name: str,
        executor: CommandExecutor = _default_executor,
        report_directory: Path | str = Path("reports/deployment"),
        env_file: Path | str | None = None,
    ) -> None:
        self.project_name = validate_project_name(project_name)
        self.executor = executor
        self.report_directory = Path(report_directory)
        self.env_file = Path(env_file) if env_file else None

    def _compose(self, *arguments: str) -> list[str]:
        command = ["docker", "compose"]
        if self.env_file:
            command.extend(["--env-file", str(self.env_file)])
        command.extend(["--project-name", self.project_name, *arguments])
        return command

    def _check_specs(self) -> list[tuple[str, list[str], str]]:
        return [
            ("compose_config", self._compose("config"), "validate rendered Compose topology"),
            ("compose_build", self._compose("build"), "build the isolated runtime images"),
            ("compose_up", self._compose("up", "--detach"), "start the declared services"),
            (
                "migration_completed",
                self._compose("ps", "--all", "migrate", "--format", "json"),
                "capture the one-shot migration service state",
            ),
            (
                "bootstrap_completed",
                self._compose("ps", "--all", "bootstrap", "--format", "json"),
                "capture the one-shot bootstrap service state",
            ),
            (
                "api_readiness",
                self._compose(
                    "exec", "-T", "api", "curl", "--fail", "--silent", "--show-error",
                    "http://localhost:8000/health/ready",
                ),
                "capture the API readiness response from the private network",
            ),
        ]

    @staticmethod
    def _one_shot_service_succeeded(output: str | None) -> bool:
        """Fail closed when Compose did not report a completed successful job."""
        if not isinstance(output, str):
            return False
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return False
        services = payload if isinstance(payload, list) else [payload]
        return any(
            isinstance(service, dict)
            and str(service.get("State", service.get("state", ""))).lower() == "exited"
            and str(service.get("ExitCode", service.get("exitCode", ""))) == "0"
            for service in services
        )

    def run(self, *, execute: bool = False) -> dict[str, object]:
        checks: list[dict[str, object]] = []
        specs = self._check_specs()
        if not execute:
            checks = [
                {
                    "name": name,
                    "status": "PLANNED",
                    "purpose": purpose,
                    "command": [redact_text(argument) for argument in command],
                }
                for name, command, purpose in specs
            ]
        else:
            blocked = False
            for name, command, purpose in specs:
                if blocked:
                    checks.append(
                        {
                            "name": name,
                            "status": "BLOCKED",
                            "purpose": purpose,
                            "command": [redact_text(argument) for argument in command],
                        }
                    )
                    continue
                result = self.executor(command)
                evidence_succeeded = (
                    self._one_shot_service_succeeded(result.stdout)
                    if name in {"migration_completed", "bootstrap_completed"}
                    else True
                )
                check = {
                    "name": name,
                    "status": "PASS" if result.returncode == 0 and evidence_succeeded else "FAIL",
                    "purpose": purpose,
                    "command": [redact_text(argument) for argument in command],
                    "returncode": result.returncode,
                    "stdout": redact_text(result.stdout),
                    "stderr": redact_text(result.stderr),
                }
                if not evidence_succeeded:
                    check["evidence_error"] = "Compose did not report an exited service with exit code 0."
                checks.append(check)
                blocked = check["status"] == "FAIL"

        report: dict[str, object] = {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "project_name": self.project_name,
            "mode": "EXECUTE" if execute else "DRY_RUN",
            "checks": checks,
            "recovery_exercises": {
                "idempotent_bootstrap": {
                    "status": "NOT_EXECUTED",
                    "reason": "Requires a separately approved acceptance action; this verifier never repeats writes by default.",
                },
                "restart_recovery": {
                    "status": "NOT_EXECUTED",
                    "reason": "Requires a separately approved acceptance action; this verifier never restarts services by default.",
                },
                "fault_injection": {
                    "status": "NOT_EXECUTED",
                    "reason": "Requires an explicit, scoped fault plan; this verifier never stops or deletes services.",
                },
            },
            "cleanup": {"status": "NOT_EXECUTED", "reason": "No docker compose down or volume deletion is performed."},
        }
        self._write_reports(report)
        return report

    def _write_reports(self, report: dict[str, object]) -> None:
        self.report_directory.mkdir(parents=True, exist_ok=True)
        json_path = self.report_directory / "deployment-verification.json"
        markdown_path = self.report_directory / "deployment-verification.md"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        rows = [
            "# Stage 3 deployment verification",
            "",
            f"- Project: `{report['project_name']}`",
            f"- Mode: `{report['mode']}`",
            f"- Generated: `{report['generated_at']}`",
            "",
            "| Check | Status | Purpose |",
            "| --- | --- | --- |",
        ]
        rows.extend(
            f"| {check['name']} | {check['status']} | {check['purpose']} |"
            for check in report["checks"]  # type: ignore[index]
        )
        rows.extend(["", "## Recovery exercises", "", "All recovery and fault exercises are intentionally not executed by this runner.", ""])
        markdown_path.write_text("\n".join(rows), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", required=True, help="new, isolated Docker Compose project name")
    parser.add_argument("--env-file", default=".env.docker", help="Compose environment file")
    parser.add_argument("--report-directory", default="reports/deployment")
    parser.add_argument("--execute", action="store_true", help="run Docker Compose checks (default: print a dry-run report)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    verifier = DeploymentVerifier(
        project_name=args.project_name,
        report_directory=args.report_directory,
        env_file=args.env_file,
    )
    report = verifier.run(execute=args.execute)
    print(json.dumps({"mode": report["mode"], "report_directory": str(args.report_directory)}, ensure_ascii=False))
    return 0 if all(check["status"] in {"PASS", "PLANNED"} for check in report["checks"]) else 1  # type: ignore[index]


if __name__ == "__main__":
    raise SystemExit(main())
