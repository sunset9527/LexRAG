"""Contract tests for the safe Stage 3 deployment verification runner."""

from __future__ import annotations

import json

import pytest

from scripts.verify_deployment import (
    CommandResult,
    DeploymentVerifier,
    validate_project_name,
)


class RecordingExecutor:
    def __init__(self, results: list[CommandResult] | None = None):
        self.commands: list[list[str]] = []
        self.results = iter(results or [])

    def __call__(self, command: list[str]) -> CommandResult:
        self.commands.append(command)
        return next(self.results, CommandResult(returncode=0, stdout="ok", stderr=""))


def test_project_name_must_be_explicit_and_isolated():
    assert validate_project_name("lexrag-stage3-acceptance") == "lexrag-stage3-acceptance"

    with pytest.raises(ValueError, match="explicit"):
        validate_project_name("")
    with pytest.raises(ValueError, match="lowercase"):
        validate_project_name("LexRAG")
    with pytest.raises(ValueError, match="reserved"):
        validate_project_name("lexrag")


def test_dry_run_plans_compose_checks_without_running_docker(tmp_path):
    executor = RecordingExecutor()

    report = DeploymentVerifier(
        project_name="lexrag-stage3-acceptance",
        executor=executor,
        report_directory=tmp_path,
    ).run(execute=False)

    assert executor.commands == []
    assert [check["name"] for check in report["checks"][:3]] == [
        "compose_config",
        "compose_build",
        "compose_up",
    ]
    assert all(check["status"] == "PLANNED" for check in report["checks"])
    assert report["recovery_exercises"]["idempotent_bootstrap"]["status"] == "NOT_EXECUTED"


def test_execute_collects_compose_and_runtime_evidence_without_cleanup(tmp_path):
    executor = RecordingExecutor(
        [
            CommandResult(0, "config", ""),
            CommandResult(0, "build", ""),
            CommandResult(0, "up", ""),
            CommandResult(0, '[{"Name":"migrate","State":"exited","ExitCode":0}]', ""),
            CommandResult(0, '[{"Name":"bootstrap","State":"exited","ExitCode":0}]', ""),
            CommandResult(0, '{"status":"ready"}', ""),
        ]
    )

    report = DeploymentVerifier(
        project_name="lexrag-stage3-acceptance",
        executor=executor,
        report_directory=tmp_path,
    ).run(execute=True)

    assert executor.commands[:3] == [
        ["docker", "compose", "--project-name", "lexrag-stage3-acceptance", "config"],
        ["docker", "compose", "--project-name", "lexrag-stage3-acceptance", "build"],
        ["docker", "compose", "--project-name", "lexrag-stage3-acceptance", "up", "--detach"],
    ]
    assert all("down" not in command and "rm" not in command for command in executor.commands)
    assert report["checks"][-1]["name"] == "api_readiness"
    assert report["checks"][-1]["status"] == "PASS"
    assert (tmp_path / "deployment-verification.json").is_file()
    assert (tmp_path / "deployment-verification.md").is_file()


def test_one_shot_service_must_report_an_exit_code_of_zero(tmp_path):
    executor = RecordingExecutor(
        [
            CommandResult(0, "config", ""),
            CommandResult(0, "build", ""),
            CommandResult(0, "up", ""),
            CommandResult(0, '[{"Name":"migrate","State":"exited","ExitCode":1}]', ""),
        ]
    )

    report = DeploymentVerifier(
        project_name="lexrag-stage3-acceptance",
        executor=executor,
        report_directory=tmp_path,
    ).run(execute=True)

    assert report["checks"][3]["status"] == "FAIL"
    assert report["checks"][4]["status"] == "BLOCKED"


def test_reports_redact_secrets_urls_and_host_paths(tmp_path):
    executor = RecordingExecutor(
        [
            CommandResult(
                1,
                "https://alice:pw@example.test/a",
                "MYSQL_PASSWORD=top-secret C:\\Users\\alice\\model TOKEN=abc KEY=api-key Cookie: sid=xyz",
            ),
        ]
    )

    DeploymentVerifier(
        project_name="lexrag-stage3-acceptance",
        executor=executor,
        report_directory=tmp_path,
        env_file=r"C:\Users\alice\.env.docker",
    ).run(execute=True)

    rendered = (tmp_path / "deployment-verification.json").read_text(encoding="utf-8")
    assert "top-secret" not in rendered
    assert "alice:pw" not in rendered
    assert "C:\\Users\\alice" not in " ".join(json.loads(rendered)["checks"][0]["command"])
    assert "abc" not in rendered
    assert "api-key" not in rendered
    assert "sid=xyz" not in rendered
    assert "[REDACTED_" in rendered
    assert json.loads(rendered)["project_name"] == "lexrag-stage3-acceptance"
