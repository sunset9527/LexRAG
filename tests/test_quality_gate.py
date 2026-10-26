from pathlib import Path

from scripts.quality_gate import (
    CommandResult,
    build_quality_commands,
    build_report,
    package_manager_command,
)


def test_quality_gate_uses_cmd_shim_for_npm_on_windows():
    assert package_manager_command("nt") == "npm.cmd"
    assert package_manager_command("posix") == "npm"


def test_quality_gate_includes_ruff_for_maintained_python_code(tmp_path):
    """静态检查必须覆盖当前运行代码、脚本、测试与迁移，而非仅依赖 pytest。"""
    commands = build_quality_commands(output_dir=tmp_path, skip_build=True)

    ruff_command = next(command for name, command, _ in commands if name == "ruff")
    assert ruff_command[1:4] == ["-m", "ruff", "check"]
    assert ruff_command[4:] == ["api.py", "app", "src", "scripts", "tests", "alembic"]

    pytest_command = next(command for name, command, _ in commands if name == "backend pytest")
    assert pytest_command[pytest_command.index("--basetemp") + 1] == str(tmp_path / "pytest-tmp")


def test_quality_gate_runs_every_tracked_frontend_contract(tmp_path):
    commands = build_quality_commands(output_dir=tmp_path, skip_build=True)

    frontend_command = next(
        command for name, command, _ in commands if name == "frontend node tests"
    )

    assert frontend_command == [
        "node",
        "--test",
        "tests/credentialStorage.test.mjs",
        "tests/lawPresentation.test.mjs",
        "tests/visualSystem.test.mjs",
        "test/sseProtocol.test.mjs",
    ]


def test_quality_gate_runs_vitest_unit_suite(tmp_path):
    commands = build_quality_commands(output_dir=tmp_path, skip_build=True)

    unit_command = next(command for name, command, _ in commands if name == "frontend unit tests")

    assert unit_command == [package_manager_command(), "run", "test:unit"]


def test_quality_report_counts_commands_and_keeps_real_execution_metadata():
    report = build_report(
        [
            CommandResult(
                name="backend pytest",
                command=["python", "-m", "pytest", "tests", "-q"],
                return_code=0,
                duration_seconds=12.345,
                output="217 passed in 12.34s",
            ),
            CommandResult(
                name="frontend build",
                command=["npm", "run", "build"],
                return_code=0,
                duration_seconds=8.2,
                output="built in 8.20s",
            ),
        ]
    )

    assert report["status"] == "passed"
    assert report["summary"] == {
        "total_commands": 2,
        "passed_commands": 2,
        "failed_commands": 0,
        "total_duration_seconds": 20.545,
    }
    assert report["commands"][0]["name"] == "backend pytest"
    assert report["commands"][0]["return_code"] == 0
    assert report["commands"][0]["output_tail"] == "217 passed in 12.34s"


def test_quality_report_fails_when_any_gate_fails():
    report = build_report(
        [
            CommandResult("backend pytest", ["python", "-m", "pytest"], 0, 1.0, "ok"),
            CommandResult("frontend build", ["npm", "run", "build"], 1, 2.0, "failure"),
        ]
    )

    assert report["status"] == "failed"
    assert report["summary"]["failed_commands"] == 1


def test_ci_has_one_python_313_node_22_quality_entrypoint():
    root = Path(__file__).parent.parent
    workflow = (root / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")

    assert not (root / ".github" / "workflows" / "ci.yml").exists()
    assert "python-version: '3.13'" in workflow
    assert "node-version: '22'" in workflow
    assert "-c constraints-py313.txt -r requirements.txt" in workflow
    assert "npm ci --prefix frontend" in workflow
