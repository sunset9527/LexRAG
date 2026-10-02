from scripts.quality_gate import CommandResult, build_report, package_manager_command


def test_quality_gate_uses_cmd_shim_for_npm_on_windows():
    assert package_manager_command("nt") == "npm.cmd"
    assert package_manager_command("posix") == "npm"


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
