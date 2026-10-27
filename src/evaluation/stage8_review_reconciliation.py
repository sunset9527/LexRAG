"""Read-only reconciliation for a Stage 8 human review queue."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

REVIEW_FIELDS = frozenset(
    {"review_state", "reviewer", "reviewed_at", "review_note", "verified_record"}
)
_REVIEW_STATES = ("approved", "revised", "rejected")


class Stage8ReviewReconciliationError(ValueError):
    """The reviewed queue cannot be reconciled with its pending input."""


class _DuplicateJsonKeyError(ValueError):
    """A JSON object contains a duplicate key."""


class _NonstandardJsonConstantError(ValueError):
    """A JSON value uses a non-standard constant such as NaN."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in pairs:
        if key in row:
            raise _DuplicateJsonKeyError(key)
        row[key] = value
    return row


def _reject_nonstandard_json_constant(constant: str) -> None:
    raise _NonstandardJsonConstantError(constant)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise Stage8ReviewReconciliationError(f"无法读取审核队列文件: {path}") from exc

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(
                line,
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=_reject_nonstandard_json_constant,
            )
        except _DuplicateJsonKeyError as exc:
            raise Stage8ReviewReconciliationError(
                f"{path} 第 {line_number} 行包含重复 JSON 键: {exc}"
            ) from exc
        except (_NonstandardJsonConstantError, json.JSONDecodeError) as exc:
            raise Stage8ReviewReconciliationError(
                f"{path} 第 {line_number} 行不是合法 JSON"
            ) from exc
        if not isinstance(row, dict):
            raise Stage8ReviewReconciliationError(f"{path} 第 {line_number} 行必须是 JSON 对象")
        rows.append(row)
    return rows


def _queue_rows_by_id(rows: list[dict[str, Any]], *, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for line_number, row in enumerate(rows, start=1):
        queue_id = row.get("queue_id")
        if not isinstance(queue_id, str) or not queue_id.strip():
            raise Stage8ReviewReconciliationError(
                f"{label} 第 {line_number} 行的 queue_id 必须是非空字符串"
            )
        normalized_queue_id = queue_id.strip()
        if normalized_queue_id in result:
            raise Stage8ReviewReconciliationError(
                f"{label} 的 queue_id 重复: {normalized_queue_id}"
            )
        result[normalized_queue_id] = row
    return result


def _json_values_equal(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's bool/int coercion."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_values_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_values_equal(left_item, right_item) for left_item, right_item in zip(left, right)
        )
    return left == right


def _validate_unchanged_fields(
    queue_id: str,
    pending: dict[str, Any],
    reviewed: dict[str, Any],
) -> None:
    fields = (set(pending) | set(reviewed)) - REVIEW_FIELDS
    for field in sorted(fields):
        if field not in pending or field not in reviewed or not _json_values_equal(
            pending[field], reviewed[field]
        ):
            raise Stage8ReviewReconciliationError(
                f"queue_id {queue_id} 的非审核字段 {field} 被修改"
            )


def _require_nonblank_review_string(row: dict[str, Any], queue_id: str, field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise Stage8ReviewReconciliationError(
            f"queue_id {queue_id} 的 {field} 必须是非空字符串"
        )
    return value


def _validate_reviewed_row(queue_id: str, row: dict[str, Any]) -> str:
    state = row.get("review_state")
    if state not in _REVIEW_STATES:
        raise Stage8ReviewReconciliationError(
            f"queue_id {queue_id} 的 review_state 必须为 approved、revised 或 rejected"
        )

    _require_nonblank_review_string(row, queue_id, "reviewer")
    reviewed_at = _require_nonblank_review_string(row, queue_id, "reviewed_at")
    _require_nonblank_review_string(row, queue_id, "review_note")
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Stage8ReviewReconciliationError(
            f"queue_id {queue_id} 的 reviewed_at 必须是含时区的 ISO-8601 时间"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Stage8ReviewReconciliationError(
            f"queue_id {queue_id} 的 reviewed_at 必须是含时区的 ISO-8601 时间"
        )

    if "verified_record" not in row or (
        row["verified_record"] is not None and not isinstance(row["verified_record"], dict)
    ):
        raise Stage8ReviewReconciliationError(
            f"queue_id {queue_id} 的 verified_record 必须是 null 或 JSON 对象"
        )
    return state


def _origin_question_type_state_counts(
    rows: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, int]]]:
    counts: dict[str, dict[str, Counter[str]]] = {}
    for row in rows.values():
        origin = row.get("origin")
        question_type = row.get("proposed_question_type")
        if not isinstance(origin, str) or not isinstance(question_type, str):
            # The immutable-field comparison is intentionally the only contract
            # enforced for candidate content.  Keep unusual values JSON-safe.
            origin = str(origin)
            question_type = str(question_type)
        by_question_type = counts.setdefault(origin, {})
        by_question_type.setdefault(question_type, Counter())[row["review_state"]] += 1
    return {
        origin: {
            question_type: {state: state_counts[state] for state in _REVIEW_STATES}
            for question_type, state_counts in sorted(by_question_type.items())
        }
        for origin, by_question_type in sorted(counts.items())
    }


def reconcile_review_queue(pending_path: Path, reviewed_path: Path) -> dict[str, Any]:
    """Reconcile reviewed Stage 8 candidates without editing or freezing records.

    A non-null ``verified_record`` only passes this queue-level gate.  It is not
    converted to, or asserted to be, a valid formal Stage 8 record.
    """
    pending_rows = _queue_rows_by_id(_load_jsonl(Path(pending_path)), label="待审核队列")
    reviewed_rows = _queue_rows_by_id(_load_jsonl(Path(reviewed_path)), label="已审核队列")
    if pending_rows.keys() != reviewed_rows.keys():
        raise Stage8ReviewReconciliationError("待审核队列与已审核队列的 queue_id 集合不一致")

    state_counts: Counter[str] = Counter()
    formal_record_ready_count = 0
    for queue_id in pending_rows:
        pending = pending_rows[queue_id]
        reviewed = reviewed_rows[queue_id]
        _validate_unchanged_fields(queue_id, pending, reviewed)
        state = _validate_reviewed_row(queue_id, reviewed)
        state_counts[state] += 1
        if state == "approved" and isinstance(reviewed["verified_record"], dict):
            formal_record_ready_count += 1

    missing_verified_records = state_counts["approved"] - formal_record_ready_count
    blocking_reasons: list[str] = []
    if missing_verified_records:
        blocking_reasons.append(
            "有 "
            f"{missing_verified_records} 条 approved 记录缺少 verified_record，"
            "不能进入正式冻结数据集；本工具不验证其 Schema。"
        )

    return {
        "total": len(reviewed_rows),
        "state_counts": {state: state_counts[state] for state in _REVIEW_STATES},
        "origin_question_type_state_counts": _origin_question_type_state_counts(reviewed_rows),
        "formal_record_ready_count": formal_record_ready_count,
        "blocking_reasons": blocking_reasons,
    }
