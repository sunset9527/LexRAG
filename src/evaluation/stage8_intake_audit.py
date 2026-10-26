"""Read-only readiness audit for legacy JSONL entering Stage 8 review."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.evaluation.stage8_dataset import REQUIRED_STAGE8_FIELDS

_STRING_FIELDS = frozenset(
    {
        "id",
        "question",
        "question_type",
        "difficulty",
        "source_url",
        "source_version",
        "source_locator",
        "reviewer",
        "reviewed_at",
        "review_note",
        "review_status",
    }
)
_SIMPLE_STRING_FIELDS = _STRING_FIELDS - {"review_status", "reviewed_at", "source_url"}
_PENDING_MARKER = "待人工核验"
_RFC3339_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
)
_EVIDENCE_FIELDS = (
    "source",
    "source_url",
    "source_version",
    "source_locator",
    "reviewer",
    "reviewed_at",
    "review_note",
)


class Stage8IntakeAuditError(ValueError):
    """The requested intake audit could not read its input."""


class _DuplicateJsonKeyError(ValueError):
    """A JSON object has duplicate keys and cannot be audited reliably."""


class _NonstandardJsonConstantError(ValueError):
    """The input used a non-standard JSON numeric constant."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(key)
        result[key] = value
    return result


def _reject_nonstandard_json_constant(constant: str) -> None:
    raise _NonstandardJsonConstantError(constant)


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _nonblank_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any, *, allow_empty: bool) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(_nonblank_string(entry) for entry in value)
    )


def _looks_like_contract_url(value: Any) -> bool:
    if not _nonblank_string(value) or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value
    ) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() == "https"
        and bool(parsed.netloc)
        and bool(parsed.hostname)
        and "@" not in parsed.netloc
        and not parsed.query
        and not parsed.fragment
    )


def _looks_like_rfc3339_timestamp(value: Any) -> bool:
    if not _nonblank_string(value) or not _RFC3339_TIMESTAMP.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _record_issues(record: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return field-level readiness findings without transforming a record."""
    issues: list[dict[str, str]] = []
    for field in sorted(REQUIRED_STAGE8_FIELDS):
        if field not in record:
            issues.append(_issue(f"missing_{field}", f"缺少 Stage 8 必填字段 {field}"))

    for field in sorted(_SIMPLE_STRING_FIELDS & record.keys()):
        if not _nonblank_string(record[field]):
            issues.append(_issue(f"invalid_{field}", f"字段 {field} 尚未满足 Stage 8 要求"))

    if "expected_knowledge_base_slugs" in record and not _string_list(
        record["expected_knowledge_base_slugs"], allow_empty=False
    ):
        issues.append(
            _issue(
                "invalid_expected_knowledge_base_slugs",
                "字段 expected_knowledge_base_slugs 尚未满足 Stage 8 要求",
            )
        )
    if "relevant_article_ids" in record and not _string_list(
        record["relevant_article_ids"], allow_empty=True
    ):
        issues.append(
            _issue(
                "invalid_relevant_article_ids",
                "字段 relevant_article_ids 尚未满足 Stage 8 要求",
            )
        )
    if "should_abstain" in record and type(record["should_abstain"]) is not bool:
        issues.append(
            _issue("invalid_should_abstain", "字段 should_abstain 尚未满足 Stage 8 要求")
        )
    if "source_url" in record and not _looks_like_contract_url(record["source_url"]):
        issues.append(_issue("invalid_source_url", "字段 source_url 尚未满足 Stage 8 要求"))
    if "reviewed_at" in record and not _looks_like_rfc3339_timestamp(record["reviewed_at"]):
        issues.append(_issue("invalid_reviewed_at", "字段 reviewed_at 尚未满足 Stage 8 要求"))

    status = record.get("review_status")
    if "review_status" in record and status != "approved":
        issues.append(
            _issue(
                "invalid_review_status",
                "冻结评测候选的 review_status 必须为 approved",
            )
        )

    if (
        type(record.get("should_abstain")) is bool
        and _string_list(record.get("relevant_article_ids"), allow_empty=True)
    ):
        article_ids = record["relevant_article_ids"]
        if record["should_abstain"] and article_ids:
            issues.append(
                _issue(
                    "invalid_relevant_article_ids",
                    "弃答样本的 relevant_article_ids 必须为空",
                )
            )
        if not record["should_abstain"] and not article_ids:
            issues.append(
                _issue(
                    "invalid_relevant_article_ids",
                    "非弃答样本必须提供 relevant_article_ids",
                )
            )

    if status == "approved" and any(
        _PENDING_MARKER in value
        for field in _EVIDENCE_FIELDS
        if _nonblank_string(value := record.get(field))
    ):
        issues.append(
            _issue(
                "approved_pending_evidence",
                "approved 样本的来源或审核记录包含待人工核验标记",
            )
        )
    return issues


def _row(line_number: int, record: Mapping[str, Any], issues: list[dict[str, str]]) -> dict[str, Any]:
    row: dict[str, Any] = {"line_number": line_number}
    identifier = record.get("id")
    if _nonblank_string(identifier):
        row["id"] = identifier
    row["issues"] = issues
    return row


def audit_stage8_intake(path: Path | str) -> dict[str, Any]:
    """Audit a JSONL file without modifying records, labels, or review states.

    Blank lines are ignored.  Readable JSON objects receive field-level findings;
    malformed lines remain visible as findings so legacy-data problems are not lost.
    """
    dataset_path = Path(path)
    try:
        lines = dataset_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise Stage8IntakeAuditError(f"无法读取 Stage 8 审计输入: {dataset_path}") from exc

    rows: list[dict[str, Any]] = []
    issue_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    input_rows = readable_rows = ready_rows = malformed_rows = 0
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        input_rows += 1
        try:
            decoded = json.loads(
                line,
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=_reject_nonstandard_json_constant,
            )
        except _DuplicateJsonKeyError:
            issues = [_issue("duplicate_json_key", "JSON 对象包含重复键")]
            rows.append({"line_number": line_number, "issues": issues})
            malformed_rows += 1
        except (json.JSONDecodeError, _NonstandardJsonConstantError):
            issues = [_issue("malformed_json", "该行不是合法 JSON")]
            rows.append({"line_number": line_number, "issues": issues})
            malformed_rows += 1
        else:
            if not isinstance(decoded, dict):
                issues = [_issue("json_object_required", "该行必须是 JSON 对象")]
                rows.append({"line_number": line_number, "issues": issues})
                malformed_rows += 1
            else:
                readable_rows += 1
                issues = _record_issues(decoded)
                identifier = decoded.get("id")
                if _nonblank_string(identifier):
                    normalized_identifier = identifier.strip()
                    if normalized_identifier in seen_ids:
                        issues.append(
                            _issue(
                                "duplicate_id",
                                "字段 id 去除空白后与前序样本重复",
                            )
                        )
                    else:
                        seen_ids.add(normalized_identifier)
                rows.append(_row(line_number, decoded, issues))
                if not issues:
                    ready_rows += 1
        issue_counts.update(issue["code"] for issue in rows[-1]["issues"])

    return {
        "summary": {
            "input_rows": input_rows,
            "readable_rows": readable_rows,
            "ready_rows": ready_rows,
            "not_ready_rows": input_rows - ready_rows,
            "malformed_rows": malformed_rows,
            "issue_counts": dict(sorted(issue_counts.items())),
        },
        "rows": rows,
    }
