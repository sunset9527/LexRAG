"""Tests for the read-only Stage 8 legacy-dataset intake audit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.evaluation.stage8_intake_audit import audit_stage8_intake

ROOT = Path(__file__).resolve().parents[1]


def _ready_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": "stage8-civil-001",
        "question": "成年人年龄如何规定？",
        "question_type": "direct_lookup",
        "difficulty": "easy",
        "expected_knowledge_base_slugs": ["civil-code"],
        "relevant_article_ids": ["中华人民共和国民法典第17条"],
        "should_abstain": False,
        "source_url": "https://flk.npc.gov.cn/detail2.html",
        "source_version": "2026-10-01",
        "source_locator": "中华人民共和国民法典第17条",
        "reviewer": "reviewer-a",
        "reviewed_at": "2026-10-26T10:30:00+08:00",
        "review_note": "逐条核对问题、来源和相关法条。",
        "review_status": "approved",
    }
    record.update(overrides)
    return record


def _write_jsonl(tmp_path: Path, *lines: str) -> Path:
    dataset = tmp_path / "legacy.jsonl"
    dataset.write_text("\n".join(lines), encoding="utf-8")
    return dataset


def _json_line(item: object) -> str:
    return json.dumps(item, ensure_ascii=False)


def test_audit_accepts_a_ready_stage8_shaped_record(tmp_path: Path) -> None:
    report = audit_stage8_intake(_write_jsonl(tmp_path, _json_line(_ready_record())))

    assert report["summary"] == {
        "input_rows": 1,
        "readable_rows": 1,
        "ready_rows": 1,
        "not_ready_rows": 0,
        "malformed_rows": 0,
        "issue_counts": {},
    }
    assert report["rows"] == [{"line_number": 1, "id": "stage8-civil-001", "issues": []}]


def test_audit_reports_approved_pending_evidence_in_legacy_row(tmp_path: Path) -> None:
    record = _ready_record(source_locator="待人工核验")

    report = audit_stage8_intake(_write_jsonl(tmp_path, _json_line(record)))

    assert report["summary"]["ready_rows"] == 0
    assert report["rows"][0]["issues"] == [
        {
            "code": "approved_pending_evidence",
            "message": "approved 样本的来源或审核记录包含待人工核验标记",
        }
    ]


def test_audit_marks_invalid_contract_fields_as_not_ready(tmp_path: Path) -> None:
    record = _ready_record(
        source_url="http://example.test/not-https",
        reviewed_at="not-a-rfc3339-timestamp",
    )

    report = audit_stage8_intake(_write_jsonl(tmp_path, _json_line(record)))

    assert report["summary"]["ready_rows"] == 0
    assert {issue["code"] for issue in report["rows"][0]["issues"]} == {
        "invalid_source_url",
        "invalid_reviewed_at",
    }


def test_audit_reports_every_missing_contract_field_without_question_content(tmp_path: Path) -> None:
    secret_question = "不得出现在审计报告中的问题内容"
    report = audit_stage8_intake(
        _write_jsonl(tmp_path, _json_line({"id": "legacy-001", "question": secret_question}))
    )

    issue_codes = {issue["code"] for issue in report["rows"][0]["issues"]}
    assert issue_codes == {
        "missing_question_type",
        "missing_difficulty",
        "missing_expected_knowledge_base_slugs",
        "missing_relevant_article_ids",
        "missing_should_abstain",
        "missing_source_url",
        "missing_source_version",
        "missing_source_locator",
        "missing_reviewer",
        "missing_reviewed_at",
        "missing_review_note",
        "missing_review_status",
    }
    assert secret_question not in json.dumps(report, ensure_ascii=False)


def test_audit_reports_malformed_json_and_duplicate_keys_per_line(tmp_path: Path) -> None:
    duplicate = '{"id": "one", "id": "two"}'
    report = audit_stage8_intake(_write_jsonl(tmp_path, "{not-json}", duplicate))

    assert report["summary"]["input_rows"] == 2
    assert report["summary"]["readable_rows"] == 0
    assert report["summary"]["not_ready_rows"] == 2
    assert report["summary"]["malformed_rows"] == 2
    assert [row["issues"][0]["code"] for row in report["rows"]] == [
        "malformed_json",
        "duplicate_json_key",
    ]


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_audit_reports_nonstandard_json_constants_as_malformed_rows(
    tmp_path: Path, constant: str
) -> None:
    report = audit_stage8_intake(_write_jsonl(tmp_path, f'{{"id": {constant}}}'))

    assert report["summary"]["readable_rows"] == 0
    assert report["summary"]["malformed_rows"] == 1
    assert report["rows"] == [
        {
            "line_number": 1,
            "issues": [{"code": "malformed_json", "message": "该行不是合法 JSON"}],
        }
    ]


def test_audit_ignores_blank_lines_and_never_emits_source_text(tmp_path: Path) -> None:
    source_text = "https://example.test/private-source-token"
    record = _ready_record(source_url=source_text)
    report = audit_stage8_intake(_write_jsonl(tmp_path, "", "  ", _json_line(record), "\t"))

    assert report["summary"]["input_rows"] == 1
    assert source_text not in json.dumps(report, ensure_ascii=False)


def test_audit_cli_writes_report_and_returns_zero_for_not_ready_rows(tmp_path: Path) -> None:
    dataset = _write_jsonl(tmp_path, _json_line({"id": "legacy-001"}))
    output = tmp_path / "audit.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_stage8_evaluation_intake.py",
            "--dataset",
            str(dataset),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["not_ready_rows"] == 1


def test_audit_cli_returns_nonzero_and_does_not_create_output_for_unreadable_input(
    tmp_path: Path,
) -> None:
    output = tmp_path / "audit.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audit_stage8_evaluation_intake.py",
            "--dataset",
            str(tmp_path / "missing.jsonl"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert not output.exists()
