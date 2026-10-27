"""Build the non-formal, human-reviewed Stage 8 candidate baseline read-only."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.evaluation.stage8_review_queue import QUEUE_RECORD_FIELDS

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Stage8ReviewedBaselineError(ValueError):
    """Reviewed candidate inputs do not meet the Stage 8 baseline contract."""


class _DuplicateKey(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise Stage8ReviewedBaselineError(f"无法读取 JSONL: {path}") from exc
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line, object_pairs_hook=_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except _DuplicateKey as exc:
            raise Stage8ReviewedBaselineError(f"{path} 第 {number} 行包含重复 JSON 键: {exc}") from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise Stage8ReviewedBaselineError(f"{path} 第 {number} 行不是合法 JSON") from exc
        if not isinstance(row, dict):
            raise Stage8ReviewedBaselineError(f"{path} 第 {number} 行必须是 JSON 对象")
        if set(row) != QUEUE_RECORD_FIELDS:
            raise Stage8ReviewedBaselineError(f"{path} 第 {number} 行必须且只能包含既定的 14 个 queue 字段")
        queue_id = row.get("queue_id")
        if not isinstance(queue_id, str) or not queue_id.strip() or queue_id in ids:
            raise Stage8ReviewedBaselineError(f"{path} 第 {number} 行的 queue_id 必须唯一且非空")
        ids.add(queue_id)
        rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _validate_approved(row: dict[str, Any]) -> None:
    queue_id = row["queue_id"]
    for field in ("reviewer", "reviewed_at", "review_note"):
        if not isinstance(row[field], str) or not row[field].strip():
            raise Stage8ReviewedBaselineError(f"{queue_id} 的 {field} 必须为非空字符串")
    try:
        value = datetime.fromisoformat(row["reviewed_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise Stage8ReviewedBaselineError(f"{queue_id} 的 reviewed_at 必须是含时区的 ISO-8601 时间") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise Stage8ReviewedBaselineError(f"{queue_id} 的 reviewed_at 必须是含时区的 ISO-8601 时间")
    if row["verified_record"] is not None and not isinstance(row["verified_record"], dict):
        raise Stage8ReviewedBaselineError(f"{queue_id} 的 verified_record 必须为 null 或对象")


def _different_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    review = {"review_state", "reviewer", "reviewed_at", "review_note", "verified_record"}
    return sorted(field for field in QUEUE_RECORD_FIELDS - review if before[field] != after[field])


def _corrections(reviewed: list[dict[str, Any]], pending: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending_by_id = {row["queue_id"]: row for row in pending}
    changes: list[dict[str, Any]] = []
    for row in reviewed:
        old = pending_by_id.get(row["queue_id"])
        if old is None:
            continue
        fields = _different_fields(old, row)
        if fields:
            if row["review_state"] != "approved" or not isinstance(row["review_note"], str) or not row["review_note"].strip():
                raise Stage8ReviewedBaselineError(f"{row['queue_id']} 的人工证据更正必须为 approved 且有 review_note")
            changes.append({"queue_id": row["queue_id"], "changed_non_review_fields": fields, "review_note": row["review_note"]})
    return changes


def build_reviewed_baseline(
    first_reviewed_path: Path, second_reviewed_path: Path, manifest_path: Path,
    first_pending_path: Path, second_pending_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return 109+171 approved records and its scope decision; never mutate inputs."""
    first = _load_jsonl(first_reviewed_path)
    second = _load_jsonl(second_reviewed_path)
    first_pending = _load_jsonl(first_pending_path)
    second_pending = _load_jsonl(second_pending_path)
    first_ids = {row["queue_id"] for row in first}
    second_ids = {row["queue_id"] for row in second}
    collision = first_ids & second_ids
    if collision:
        raise Stage8ReviewedBaselineError(
            f"跨轮 queue_id 不得重复: {', '.join(sorted(collision))}"
        )
    approved_first = [row for row in first if row["review_state"] == "approved"]
    approved_second = [row for row in second if row["review_state"] == "approved"]
    if len(approved_first) != 109 or len(approved_second) != 171:
        raise Stage8ReviewedBaselineError(f"approved 数量必须为 109+171，收到 {len(approved_first)}+{len(approved_second)}")
    baseline = approved_first + approved_second
    if len(baseline) != 280:
        raise Stage8ReviewedBaselineError("baseline 总数必须为 280")
    for row in baseline:
        _validate_approved(row)
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise Stage8ReviewedBaselineError(f"无法读取 remediation manifest: {manifest_path}") from exc
    lineage = manifest.get("lineage") if isinstance(manifest, dict) else None
    if not isinstance(lineage, list):
        raise Stage8ReviewedBaselineError("remediation manifest 缺少 lineage")
    blocked = [item for item in lineage if isinstance(item, dict) and item.get("status") == "blocked"]
    retired_ids = [item.get("source_queue_id") for item in blocked]
    if len(blocked) != 20 or set(retired_ids) != {f"hard-version-{n:03d}" for n in range(1, 21)}:
        raise Stage8ReviewedBaselineError("manifest 必须恰有 20 个旧 version/time blocked source ids")
    first_by_id = {row["queue_id"]: row for row in first}
    if any(first_by_id.get(source_id, {}).get("review_state") != "rejected" for source_id in retired_ids):
        raise Stage8ReviewedBaselineError("retired source ids 必须均为第一轮 rejected 旧 version/time 项")
    corrections = _corrections(first, first_pending) + _corrections(second, second_pending)
    records = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in baseline)
    def relative(path: Path) -> str:
        try:
            return Path(path).resolve().relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return Path(path).as_posix()
    scope = {
        "kind": "reviewed_candidate_baseline", "not_stage8_dataset": True,
        "target_count": 280, "retired_count": 20,
        "scope_reason": "当前语料库/版本适用规则不足；这些项目在本次评估范围内永久排除。",
        "limitations": "This is a non-formal reviewed candidate baseline, not a stage8_dataset; it makes no present-law validity claim and supplies no source_url defaults.",
        "retired_source_ids": [{"source_queue_id": source_id, "status": "retired_by_scope_decision", "reason": "当前语料库/版本适用规则不足；本次评估范围内永久排除。"} for source_id in retired_ids],
        "sources": {"first_reviewed": relative(first_reviewed_path), "second_reviewed": relative(second_reviewed_path), "remediation_manifest": relative(manifest_path), "first_pending_backup": relative(first_pending_path), "second_pending_backup": relative(second_pending_path)},
        "sha256": {"baseline_jsonl": hashlib.sha256(records.encode("utf-8")).hexdigest(), "first_reviewed": _sha256(first_reviewed_path), "first_pending": _sha256(first_pending_path), "second_reviewed": _sha256(second_reviewed_path), "second_pending": _sha256(second_pending_path), "remediation_manifest": _sha256(manifest_path)},
        "human_evidence_supported_corrections": {"count": len(corrections), "records": corrections},
    }
    return baseline, scope


def baseline_jsonl(baseline: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in baseline)
