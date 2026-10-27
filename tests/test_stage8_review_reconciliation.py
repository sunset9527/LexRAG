"""Tests for the read-only Stage 8 review-queue reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import reconcile_stage8_review_queue as reconciliation_cli
from src.evaluation.stage8_review_reconciliation import (
    Stage8ReviewReconciliationError,
    reconcile_review_queue,
)


def _pending_row(queue_id: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "queue_id": queue_id,
        "origin": "legacy_seed",
        "question": "成年人年龄如何规定？",
        "proposed_question_type": "direct_lookup",
        "proposed_difficulty": "baseline",
        "proposed_knowledge_base_slugs": ["civil-code"],
        "proposed_relevant_article_ids": ["中华人民共和国民法典第17条"],
        "proposed_should_abstain": False,
        "local_source_locator": "中华人民共和国民法典第17条",
        "review_state": "pending",
        "reviewer": "",
        "reviewed_at": "",
        "review_note": "",
        "verified_record": None,
    }
    row.update(overrides)
    return row


def _reviewed_row(queue_id: str, **overrides: object) -> dict[str, object]:
    row = _pending_row(
        queue_id,
        review_state="approved",
        reviewer="reviewer-a",
        reviewed_at="2026-10-27T09:30:00+08:00",
        review_note="已逐项复核候选内容，待补充正式来源证据。",
    )
    row.update(overrides)
    return row


def _write_jsonl(path: Path, *rows: object) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_reconcile_returns_review_summary_without_materializing_verified_record(tmp_path: Path) -> None:
    pending = tmp_path / "pending.jsonl"
    reviewed = tmp_path / "reviewed.jsonl"
    _write_jsonl(pending, _pending_row("q-1"), _pending_row("q-2", origin="hard_candidate"))
    verified_record = {"id": "future-formal-id", "source_url": "unvalidated"}
    _write_jsonl(
        reviewed,
        _reviewed_row("q-1", verified_record=verified_record),
        _reviewed_row(
            "q-2",
            origin="hard_candidate",
            review_state="revised",
            verified_record=None,
        ),
    )

    summary = reconcile_review_queue(pending, reviewed)

    assert summary == {
        "total": 2,
        "state_counts": {"approved": 1, "revised": 1, "rejected": 0},
        "origin_question_type_state_counts": {
            "hard_candidate": {"direct_lookup": {"approved": 0, "revised": 1, "rejected": 0}},
            "legacy_seed": {"direct_lookup": {"approved": 1, "revised": 0, "rejected": 0}},
        },
        "formal_record_ready_count": 1,
        "blocking_reasons": [],
    }


@pytest.mark.parametrize(
    ("pending_line", "message"),
    [
        ('{"queue_id":"q-1","queue_id":"q-2"}', "重复 JSON 键"),
        ("[]", "必须是 JSON 对象"),
    ],
)
def test_reconcile_strictly_rejects_duplicate_keys_and_non_object_rows(
    tmp_path: Path, pending_line: str, message: str
) -> None:
    pending = tmp_path / "pending.jsonl"
    reviewed = tmp_path / "reviewed.jsonl"
    pending.write_text(pending_line + "\n", encoding="utf-8")
    _write_jsonl(reviewed, _reviewed_row("q-1"))

    with pytest.raises(Stage8ReviewReconciliationError, match=message):
        reconcile_review_queue(pending, reviewed)


def test_reconcile_requires_unique_nonblank_and_matching_queue_ids(tmp_path: Path) -> None:
    pending = tmp_path / "pending.jsonl"
    reviewed = tmp_path / "reviewed.jsonl"
    _write_jsonl(pending, _pending_row("q-1"), _pending_row("q-1"))
    _write_jsonl(reviewed, _reviewed_row("q-1"), _reviewed_row("q-2"))

    with pytest.raises(Stage8ReviewReconciliationError, match="重复"):
        reconcile_review_queue(pending, reviewed)

    _write_jsonl(pending, _pending_row("q-1"))
    with pytest.raises(Stage8ReviewReconciliationError, match="queue_id 集合不一致"):
        reconcile_review_queue(pending, reviewed)


def test_reconcile_rejects_any_non_review_field_change_with_queue_id_and_field(
    tmp_path: Path,
) -> None:
    pending = tmp_path / "pending.jsonl"
    reviewed = tmp_path / "reviewed.jsonl"
    _write_jsonl(pending, _pending_row("q-1", proposed_should_abstain=False))
    _write_jsonl(
        reviewed,
        _reviewed_row("q-1", proposed_should_abstain=True),
    )

    with pytest.raises(
        Stage8ReviewReconciliationError,
        match=r"q-1.*proposed_should_abstain",
    ):
        reconcile_review_queue(pending, reviewed)


def test_reconcile_uses_type_sensitive_value_comparison_for_non_review_fields(tmp_path: Path) -> None:
    pending = tmp_path / "pending.jsonl"
    reviewed = tmp_path / "reviewed.jsonl"
    _write_jsonl(pending, _pending_row("q-1", proposed_should_abstain=False))
    _write_jsonl(reviewed, _reviewed_row("q-1", proposed_should_abstain=0))

    with pytest.raises(Stage8ReviewReconciliationError, match="proposed_should_abstain"):
        reconcile_review_queue(pending, reviewed)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("review_state", "pending", "review_state"),
        ("reviewer", " ", "reviewer"),
        ("reviewed_at", "2026-10-27T09:30:00", "reviewed_at"),
        ("reviewed_at", "not-a-date", "reviewed_at"),
        ("review_note", "", "review_note"),
        ("verified_record", [], "verified_record"),
    ],
)
def test_reconcile_validates_review_values(tmp_path: Path, field: str, value: object, message: str) -> None:
    pending = tmp_path / "pending.jsonl"
    reviewed = tmp_path / "reviewed.jsonl"
    _write_jsonl(pending, _pending_row("q-1"))
    _write_jsonl(reviewed, _reviewed_row("q-1", **{field: value}))

    with pytest.raises(Stage8ReviewReconciliationError, match=message):
        reconcile_review_queue(pending, reviewed)


def test_reconcile_reports_verified_record_gate_without_claiming_schema_validity(tmp_path: Path) -> None:
    pending = tmp_path / "pending.jsonl"
    reviewed = tmp_path / "reviewed.jsonl"
    _write_jsonl(pending, _pending_row("q-1"), _pending_row("q-2"))
    _write_jsonl(
        reviewed,
        _reviewed_row("q-1", verified_record=None),
        _reviewed_row("q-2", verified_record={"id": "not-validated"}),
    )

    summary = reconcile_review_queue(pending, reviewed)

    assert summary["formal_record_ready_count"] == 1
    assert summary["blocking_reasons"] == [
        "有 1 条 approved 记录缺少 verified_record，不能进入正式冻结数据集；本工具不验证其 Schema。"
    ]


def test_cli_prints_json_or_atomically_writes_nested_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pending = tmp_path / "pending.jsonl"
    reviewed = tmp_path / "reviewed.jsonl"
    output = tmp_path / "nested" / "summary.json"
    _write_jsonl(pending, _pending_row("q-1"))
    _write_jsonl(reviewed, _reviewed_row("q-1"))

    assert reconciliation_cli.main(["--pending", str(pending), "--reviewed", str(reviewed)]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 1

    assert (
        reconciliation_cli.main(
            ["--pending", str(pending), "--reviewed", str(reviewed), "--output", str(output)]
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8"))["total"] == 1
    assert not list(output.parent.glob(".summary.json.*.tmp"))


def test_cli_preserves_output_when_reconciliation_fails(tmp_path: Path) -> None:
    pending = tmp_path / "pending.jsonl"
    reviewed = tmp_path / "reviewed.jsonl"
    output = tmp_path / "summary.json"
    _write_jsonl(pending, _pending_row("q-1"))
    _write_jsonl(reviewed, _reviewed_row("q-1", question="被非法修改的问题"))
    output.write_text("old report\n", encoding="utf-8")

    assert (
        reconciliation_cli.main(
            ["--pending", str(pending), "--reviewed", str(reviewed), "--output", str(output)]
        )
        == 1
    )
    assert output.read_text(encoding="utf-8") == "old report\n"
