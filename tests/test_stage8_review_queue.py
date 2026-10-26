"""Tests for composing the pending-only Stage 8 review queue."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import build_stage8_review_queue as queue_cli
from src.evaluation.stage8_review_queue import (
    Stage8ReviewQueueError,
    compose_stage8_review_queue,
)

ROOT = Path(__file__).resolve().parents[1]


def _legacy(identifier: str) -> dict[str, object]:
    return {
        "id": identifier,
        "query": f"{identifier} 对应的法律问题是什么？",
        "knowledge_base_slug": "civil-code",
        "relevant_article_ids": ["中华人民共和国民法典第17条"],
        "source_locator": "中华人民共和国民法典第17条",
        "review_status": "approved",
        "reviewed_at": "2026-10-26T10:30:00+08:00",
        "source": "unverified legacy source content",
    }


def _hard(identifier: str) -> dict[str, object]:
    return {
        "candidate_id": identifier,
        "question": f"{identifier} 的复杂法律问题是什么？",
        "proposed_question_type": "multi_hop",
        "proposed_difficulty": "hard",
        "proposed_knowledge_base_slugs": ["civil-code"],
        "proposed_relevant_article_ids": ["中华人民共和国民法典第17条"],
        "proposed_should_abstain": False,
        "local_source_locator": "中华人民共和国民法典第17条",
    }


def _legacy_rows() -> list[dict[str, object]]:
    return [_legacy(f"legacy-{index:03d}") for index in range(100)]


def _hard_rows() -> list[dict[str, object]]:
    return [_hard(f"hard-{index:03d}") for index in range(200)]


def _compose(
    legacy_rows: list[dict[str, object]] | None = None,
    hard_rows: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    return compose_stage8_review_queue(
        _legacy_rows() if legacy_rows is None else legacy_rows,
        _hard_rows() if hard_rows is None else hard_rows,
        legacy_question_type="direct_lookup",
        legacy_difficulty="baseline",
        legacy_should_abstain=False,
    )


def test_composition_has_exact_100_plus_200_pending_queue_rows() -> None:
    queue = _compose()

    assert len(queue) == 300
    assert [item["origin"] for item in queue].count("legacy_seed") == 100
    assert [item["origin"] for item in queue].count("hard_candidate") == 200
    assert all(item["review_state"] == "pending" for item in queue)
    assert all(
        item["reviewer"] == item["reviewed_at"] == item["review_note"] == "" for item in queue
    )
    assert all(item["verified_record"] is None for item in queue)


def test_legacy_mapping_discards_historical_review_and_unverified_source_content() -> None:
    queue_item = _compose()[0]

    assert queue_item == {
        "queue_id": "legacy-000",
        "origin": "legacy_seed",
        "question": "legacy-000 对应的法律问题是什么？",
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
    assert "review_status" not in queue_item
    assert "source" not in queue_item


@pytest.mark.parametrize(
    ("legacy_rows", "hard_rows", "message"),
    [
        (_legacy_rows()[:-1], _hard_rows(), "100"),
        (_legacy_rows(), _hard_rows()[:-1], "200"),
        (_legacy_rows(), _hard_rows()[:-1] + [_hard("legacy-000")], "重复"),
    ],
)
def test_composition_rejects_wrong_counts_and_duplicate_queue_ids(
    legacy_rows: list[dict[str, object]], hard_rows: list[dict[str, object]], message: str
) -> None:
    with pytest.raises(Stage8ReviewQueueError, match=message):
        _compose(legacy_rows, hard_rows)


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("proposed_question_type", "", "proposed_question_type"),
        ("proposed_knowledge_base_slugs", [], "proposed_knowledge_base_slugs"),
        ("proposed_should_abstain", "false", "proposed_should_abstain"),
        ("proposed_relevant_article_ids", [], "proposed_relevant_article_ids"),
        ("unexpected_proposed_field", "no", "未知"),
        ("review_status", "approved", "approved"),
        ("verified_record", {"id": "already-reviewed"}, "verified"),
    ],
)
def test_hard_candidates_reject_invalid_unknown_or_preapproved_values(
    field: str, value: object, message: str
) -> None:
    hard_rows = _hard_rows()
    hard_rows[0][field] = value

    with pytest.raises(Stage8ReviewQueueError, match=message):
        _compose(hard_rows=hard_rows)


@pytest.mark.parametrize(
    "keyword, value, message",
    [
        ("legacy_question_type", "", "legacy_question_type"),
        ("legacy_difficulty", " ", "legacy_difficulty"),
        ("legacy_should_abstain", "false", "legacy_should_abstain"),
    ],
)
def test_legacy_defaults_must_be_valid(keyword: str, value: object, message: str) -> None:
    arguments: dict[str, object] = {
        "legacy_question_type": "direct_lookup",
        "legacy_difficulty": "baseline",
        "legacy_should_abstain": False,
    }
    arguments[keyword] = value

    with pytest.raises(Stage8ReviewQueueError, match=message):
        compose_stage8_review_queue(_legacy_rows(), _hard_rows(), **arguments)


@pytest.mark.parametrize("origin", ["legacy", "hard"])
def test_composition_rejects_non_object_input_rows(origin: str) -> None:
    legacy_rows: list[object] = _legacy_rows()
    hard_rows: list[object] = _hard_rows()
    if origin == "legacy":
        legacy_rows[0] = ["not", "an", "object"]
    else:
        hard_rows[0] = ["not", "an", "object"]

    with pytest.raises(Stage8ReviewQueueError, match="JSON 对象"):
        compose_stage8_review_queue(
            legacy_rows,
            hard_rows,
            legacy_question_type="direct_lookup",
            legacy_difficulty="baseline",
            legacy_should_abstain=False,
        )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_cli_creates_missing_parent_and_writes_utf8_jsonl(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.jsonl"
    hard = tmp_path / "hard.jsonl"
    output = tmp_path / "nested" / "stage8" / "review-queue.jsonl"
    _write_jsonl(legacy, _legacy_rows())
    _write_jsonl(hard, _hard_rows())

    assert (
        queue_cli.main(
            ["--legacy", str(legacy), "--hard-candidates", str(hard), "--output", str(output)]
        )
        == 0
    )

    written = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(written) == 300
    assert written[0]["review_state"] == "pending"


def test_cli_validation_error_preserves_existing_output_without_partial_write(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy.jsonl"
    hard = tmp_path / "hard.jsonl"
    output = tmp_path / "review-queue.jsonl"
    _write_jsonl(legacy, _legacy_rows()[:-1])
    _write_jsonl(hard, _hard_rows())
    output.write_text("old queue\n", encoding="utf-8")

    assert (
        queue_cli.main(
            ["--legacy", str(legacy), "--hard-candidates", str(hard), "--output", str(output)]
        )
        == 1
    )
    assert output.read_text(encoding="utf-8") == "old queue\n"
    assert not list(tmp_path.glob(".review-queue.jsonl.*.tmp"))


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_cli_rejects_nonstandard_json_constants_without_creating_output(
    tmp_path: Path, constant: str
) -> None:
    legacy = tmp_path / "legacy.jsonl"
    hard = tmp_path / "hard.jsonl"
    output = tmp_path / "review-queue.jsonl"
    legacy_lines = [json.dumps(row, ensure_ascii=False) for row in _legacy_rows()]
    legacy_lines[0] = legacy_lines[0].replace('"unverified legacy source content"', constant)
    legacy.write_text("\n".join(legacy_lines) + "\n", encoding="utf-8")
    _write_jsonl(hard, _hard_rows())

    assert (
        queue_cli.main(
            ["--legacy", str(legacy), "--hard-candidates", str(hard), "--output", str(output)]
        )
        == 1
    )
    assert not output.exists()


@pytest.mark.parametrize("failure", ["write", "replace"])
def test_cli_preserves_existing_output_when_atomic_write_or_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    legacy = tmp_path / "legacy.jsonl"
    hard = tmp_path / "hard.jsonl"
    output = tmp_path / "review-queue.jsonl"
    _write_jsonl(legacy, _legacy_rows())
    _write_jsonl(hard, _hard_rows())
    output.write_text("old queue\n", encoding="utf-8")

    if failure == "write":
        original_write = Path.write_text

        def fail_temp_write(path: Path, *args: object, **kwargs: object) -> int:
            if path != output:
                raise OSError("simulated write failure")
            return original_write(path, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", fail_temp_write)
    else:

        def fail_replace(source: object, destination: object) -> None:
            raise OSError("simulated replace failure")

        monkeypatch.setattr(os, "replace", fail_replace)

    assert (
        queue_cli.main(
            ["--legacy", str(legacy), "--hard-candidates", str(hard), "--output", str(output)]
        )
        == 1
    )
    assert output.read_text(encoding="utf-8") == "old queue\n"
    assert not list(tmp_path.glob(".review-queue.jsonl.*.tmp"))
