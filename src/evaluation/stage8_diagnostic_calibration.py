"""Pure, fail-closed calibration helpers for Stage 8 diagnostic evaluators."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any


class Stage8DiagnosticCalibrationError(ValueError):
    """A Stage 8 diagnostic artifact cannot be trusted or safely summarized."""


_SENSITIVE_CONFIGURATION_PARTS = ("api_key", "secret", "token", "password")


def load_completed_answer_reviews(
    review_path: Path,
    manifest_path: Path,
    *,
    expected_count: int = 100,
) -> list[dict[str, Any]]:
    """Load a SHA-bound completed review artifact without accepting partial rows."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in review_path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise Stage8DiagnosticCalibrationError("无法读取审核工件") from exc

    if not _manifest_binds_review(manifest, review_path):
        raise Stage8DiagnosticCalibrationError("审核工件清单哈希或格式不匹配")
    if len(rows) != expected_count:
        raise Stage8DiagnosticCalibrationError("审核工件样本数不匹配")
    _validate_completed_reviews(rows)
    return rows


def _manifest_binds_review(manifest: Any, review_path: Path) -> bool:
    """Accept only the pre-review or reviewed manifest that binds this exact file."""
    if not isinstance(manifest, dict):
        return False
    schema = manifest.get("schema")
    if schema == "lexrag.stage8-answer-review-merged":
        artifact = manifest.get("result")
    elif schema == "lexrag.stage8-answer-review-reviewed":
        artifact = manifest.get("reviewed_file")
    else:
        return False
    return (
        isinstance(artifact, dict)
        and artifact.get("path") == review_path.name
        and artifact.get("sha256") == sha256(review_path.read_bytes()).hexdigest()
    )


def build_calibration_report(
    reviews: Sequence[Mapping[str, Any]],
    judge_rows: Sequence[Mapping[str, Any]],
    *,
    evaluator: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare a diagnostic Judge decision with completed human decisions.

    Errors remain part of the total instead of becoming negative labels or being
    silently removed from the artifact.
    """
    _validate_completed_reviews(reviews)
    _validate_evaluator_configuration(evaluator)

    expected_ids = [str(row["id"]) for row in reviews]
    judge_by_id: dict[str, Mapping[str, Any]] = {}
    for row in judge_rows:
        identifier = str(row.get("id", ""))
        if identifier not in expected_ids:
            raise Stage8DiagnosticCalibrationError("评估结果包含未知样本")
        if identifier in judge_by_id:
            raise Stage8DiagnosticCalibrationError("评估结果包含重复样本")
        judge_by_id[identifier] = row
    missing = [identifier for identifier in expected_ids if identifier not in judge_by_id]
    if missing:
        raise Stage8DiagnosticCalibrationError("评估结果缺少审核样本")

    human_by_id = {str(row["id"]): bool(row["human_review"]) for row in reviews}
    confusion = {"true_positive": 0, "true_negative": 0, "false_positive": 0, "false_negative": 0}
    error_ids: list[str] = []
    item_results: list[dict[str, Any]] = []
    matching = 0

    for identifier in expected_ids:
        judge_row = judge_by_id[identifier]
        status = judge_row.get("status")
        if status == "execution_error":
            error_ids.append(identifier)
            item_results.append({"id": identifier, "status": "execution_error"})
            continue
        if status != "completed" or not isinstance(judge_row.get("decision"), bool):
            raise Stage8DiagnosticCalibrationError("评估结果状态或结论无效")

        human_decision = human_by_id[identifier]
        judge_decision = bool(judge_row["decision"])
        if human_decision and judge_decision:
            confusion["true_positive"] += 1
        elif not human_decision and not judge_decision:
            confusion["true_negative"] += 1
        elif judge_decision:
            confusion["false_positive"] += 1
        else:
            confusion["false_negative"] += 1
        matching += int(human_decision == judge_decision)
        item_results.append(
            {
                "id": identifier,
                "status": "completed",
                "human_review": human_decision,
                "judge_decision": judge_decision,
            }
        )

    evaluable = len(expected_ids) - len(error_ids)
    return {
        "schema": "lexrag.stage8-diagnostic-calibration",
        "version": 1,
        "status": "COMPLETE" if not error_ids else "INCOMPLETE",
        "evaluator": dict(evaluator),
        "counts": {"total": len(expected_ids), "evaluable": evaluable, "execution_errors": len(error_ids)},
        "agreement_rate": matching / evaluable if evaluable else None,
        "confusion_matrix": confusion,
        "error_ids": error_ids,
        "items": item_results,
    }


def _validate_completed_reviews(reviews: Sequence[Mapping[str, Any]]) -> None:
    if not reviews:
        raise Stage8DiagnosticCalibrationError("审核工件为空")
    identifiers: set[str] = set()
    for row in reviews:
        identifier = str(row.get("id", ""))
        workflow = row.get("workflow_output")
        if not identifier or identifier in identifiers:
            raise Stage8DiagnosticCalibrationError("审核工件样本 ID 无效或重复")
        if (
            not isinstance(row.get("reviewer"), str)
            or not row["reviewer"].strip()
            or not isinstance(row.get("reviewed_at"), str)
            or not row["reviewed_at"].strip()
            or not isinstance(row.get("review_note"), str)
            or not row["review_note"].strip()
            or not isinstance(row.get("human_review"), bool)
            or not isinstance(workflow, Mapping)
            or not isinstance(workflow.get("answer"), str)
        ):
            raise Stage8DiagnosticCalibrationError("审核字段不完整")
        identifiers.add(identifier)


def _validate_evaluator_configuration(evaluator: Mapping[str, Any]) -> None:
    if not isinstance(evaluator.get("kind"), str) or not evaluator["kind"].strip():
        raise Stage8DiagnosticCalibrationError("评估器配置缺少类型")
    for key in evaluator:
        normalized = str(key).lower()
        if any(part in normalized for part in _SENSITIVE_CONFIGURATION_PARTS):
            raise Stage8DiagnosticCalibrationError("评估器包含敏感配置")
