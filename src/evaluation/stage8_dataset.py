"""Validation contract for the future Stage 8 frozen evaluation dataset."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REQUIRED_STAGE8_FIELDS = frozenset(
    {
        "id",
        "question",
        "question_type",
        "difficulty",
        "expected_knowledge_base_slugs",
        "relevant_article_ids",
        "should_abstain",
        "source_evidence",
        "reviewer",
        "reviewed_at",
        "review_note",
        "review_status",
    }
)

_STRING_FIELDS = (
    "id",
    "question",
    "question_type",
    "difficulty",
    "reviewer",
    "reviewed_at",
    "review_note",
    "review_status",
)
SOURCE_EVIDENCE_FIELDS = frozenset(
    {
        "knowledge_base_slug",
        "version_id",
        "effective_from",
        "effective_to",
        "source_url",
        "content_hash",
        "article_ids",
        "source_locator",
    }
)
_EVIDENCE_STRING_FIELDS = (
    "knowledge_base_slug",
    "version_id",
    "effective_from",
    "source_url",
    "content_hash",
    "source_locator",
)
_PENDING_REVIEW_MARKER = "待人工核验"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RFC3339_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})"
)


class Stage8DatasetError(ValueError):
    """Stage 8 frozen-evaluation dataset violates its auditable contract."""


class _DuplicateJsonKeyError(ValueError):
    """A JSON object contains a duplicate key."""


def _line_error(line_number: int, message: str) -> Stage8DatasetError:
    return Stage8DatasetError(f"第 {line_number} 行{message}")


def _require_nonblank_string(item: Mapping[str, Any], field: str, line_number: int) -> str:
    value = item[field]
    if not isinstance(value, str) or not value.strip():
        raise _line_error(line_number, f"字段 {field} 必须是非空字符串")
    return value


def _validate_nonblank_string_list(
    item: Mapping[str, Any],
    field: str,
    line_number: int,
    *,
    allow_empty: bool,
) -> list[Any]:
    value = item[field]
    if not isinstance(value, list) or (not allow_empty and not value):
        empty_requirement = "可为空" if allow_empty else "必须为非空列表"
        raise _line_error(line_number, f"字段 {field} {empty_requirement}")
    if not all(isinstance(entry, str) and entry.strip() for entry in value):
        raise _line_error(line_number, f"字段 {field} 必须只包含非空字符串")
    return value


def _require_unique(values: list[Any], field: str, line_number: int) -> None:
    if len(values) != len(set(values)):
        raise _line_error(line_number, f"字段 {field} 不能包含重复值")


def _parse_date(value: Any, field: str, line_number: int) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise _line_error(line_number, f"字段 {field} 必须是 YYYY-MM-DD 日期")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise _line_error(line_number, f"字段 {field} 必须是有效日期") from exc
    if parsed.isoformat() != value:
        raise _line_error(line_number, f"字段 {field} 必须是规范 YYYY-MM-DD 日期")
    return parsed


def _validate_source_url(source_url: str, line_number: int) -> None:
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in source_url) or "\\" in source_url:
        raise _line_error(line_number, "字段 source_url 不能包含空白、控制字符或反斜杠")
    try:
        parsed = urlsplit(source_url)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise _line_error(line_number, "字段 source_url 不是有效的 HTTPS URL") from exc

    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or not hostname
        or "@" in parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        raise _line_error(
            line_number,
            "字段 source_url 必须是不含用户信息、查询参数或片段的绝对 HTTPS URL",
        )


def _validate_source_evidence(
    item: Mapping[str, Any],
    expected_slugs: list[Any],
    article_ids: list[Any],
    should_abstain: bool,
    line_number: int,
) -> None:
    evidence_list = item["source_evidence"]
    if not isinstance(evidence_list, list) or not evidence_list:
        raise _line_error(line_number, "字段 source_evidence 必须是非空列表")
    if len(evidence_list) != len(expected_slugs):
        raise _line_error(line_number, "source_evidence 必须与预期知识库 slug 一一对应")

    evidence_slugs: list[str] = []
    partition: list[str] = []
    for index, evidence in enumerate(evidence_list, start=1):
        context = f"source_evidence[{index}]"
        if not isinstance(evidence, Mapping):
            raise _line_error(line_number, f"{context} 必须是对象")
        missing = SOURCE_EVIDENCE_FIELDS - evidence.keys()
        unknown = evidence.keys() - SOURCE_EVIDENCE_FIELDS
        if missing:
            raise _line_error(line_number, f"{context} 缺少字段: {', '.join(sorted(missing))}")
        if unknown:
            raise _line_error(line_number, f"{context} 包含未知字段: {', '.join(sorted(unknown))}")
        for field in _EVIDENCE_STRING_FIELDS:
            _require_nonblank_string(evidence, field, line_number)

        effective_from = _parse_date(
            evidence["effective_from"], f"{context}.effective_from", line_number
        )
        effective_to_value = evidence["effective_to"]
        if effective_to_value is None:
            effective_to = None
        else:
            effective_to = _parse_date(
                effective_to_value, f"{context}.effective_to", line_number
            )
        if effective_to is not None and effective_from > effective_to:
            raise _line_error(line_number, f"{context}.effective_to 不能早于 effective_from")

        _validate_source_url(evidence["source_url"], line_number)
        if not _SHA256.fullmatch(evidence["content_hash"]):
            raise _line_error(line_number, f"{context}.content_hash 必须是 64 位小写十六进制")
        evidence_articles = _validate_nonblank_string_list(
            evidence,
            "article_ids",
            line_number,
            allow_empty=True,
        )
        _require_unique(evidence_articles, f"{context}.article_ids", line_number)
        if should_abstain and evidence_articles:
            raise _line_error(line_number, "弃答样本的每个 evidence.article_ids 都必须为空")
        evidence_slugs.append(evidence["knowledge_base_slug"])
        partition.extend(evidence_articles)

    _require_unique(evidence_slugs, "source_evidence slug", line_number)
    if set(evidence_slugs) != set(expected_slugs):
        raise _line_error(line_number, "source_evidence slug 集合必须与 expected slugs 完全一致")
    if len(partition) != len(set(partition)):
        raise _line_error(line_number, "source_evidence article_ids partition 包含重复法条")
    if set(partition) != set(article_ids):
        raise _line_error(
            line_number,
            "source_evidence article_ids 必须构成 relevant_article_ids 的精确 partition",
        )


def _nested_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for nested in value.values():
            yield from _nested_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _nested_strings(nested)


def _validate_approved_review(item: Mapping[str, Any], line_number: int) -> None:
    reviewed_at = item["reviewed_at"]
    if not _RFC3339_TIMESTAMP.fullmatch(reviewed_at):
        raise _line_error(line_number, "字段 reviewed_at 必须是规范的 RFC-3339 含时区时间")
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _line_error(line_number, "字段 reviewed_at 必须是含时区的 ISO-8601 时间") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _line_error(line_number, "字段 reviewed_at 必须是含时区的 ISO-8601 时间")

    review_values = (item["reviewer"], item["reviewed_at"], item["review_note"])
    evidence_values = _nested_strings(item["source_evidence"])
    if any(_PENDING_REVIEW_MARKER in value for value in (*review_values, *evidence_values)):
        raise _line_error(line_number, "approved 样本的来源或审核记录仍包含“待人工核验”")


def validate_stage8_record(
    record: Mapping[str, Any],
    *,
    line_number: int,
    require_approved: bool = False,
) -> None:
    """Validate one Stage 8 record without altering it."""
    missing = REQUIRED_STAGE8_FIELDS - record.keys()
    if missing:
        raise _line_error(line_number, f"缺少字段: {', '.join(sorted(missing))}")
    unknown = record.keys() - REQUIRED_STAGE8_FIELDS
    if unknown:
        raise _line_error(line_number, f"包含未知字段: {', '.join(sorted(unknown))}")

    for field in _STRING_FIELDS:
        _require_nonblank_string(record, field, line_number)

    expected_slugs = _validate_nonblank_string_list(
        record,
        "expected_knowledge_base_slugs",
        line_number,
        allow_empty=False,
    )
    _require_unique(expected_slugs, "expected_knowledge_base_slugs", line_number)
    should_abstain = record["should_abstain"]
    if type(should_abstain) is not bool:
        raise _line_error(line_number, "字段 should_abstain 必须是布尔值")

    article_ids = _validate_nonblank_string_list(
        record,
        "relevant_article_ids",
        line_number,
        allow_empty=True,
    )
    _require_unique(article_ids, "relevant_article_ids", line_number)
    if should_abstain and article_ids:
        raise _line_error(line_number, "弃答样本的相关法条必须为空")
    if not should_abstain and not article_ids:
        raise _line_error(line_number, "非弃答样本必须提供非空相关法条列表")

    _validate_source_evidence(
        record,
        expected_slugs,
        article_ids,
        should_abstain,
        line_number,
    )
    if record["review_status"] not in {"pending", "approved"}:
        raise _line_error(line_number, "字段 review_status 必须为 pending 或 approved")
    is_approved = record["review_status"] == "approved"
    if require_approved and not is_approved:
        raise _line_error(line_number, "正式评测样本的 review_status 必须为 approved")
    if is_approved:
        _validate_approved_review(record, line_number)


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key, value in pairs:
        if key in record:
            raise _DuplicateJsonKeyError(key)
        record[key] = value
    return record


def load_stage8_dataset(
    path: Path,
    *,
    require_approved: bool = False,
) -> list[dict[str, Any]]:
    """Load and validate a Stage 8 JSONL dataset without rewriting its records."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise Stage8DatasetError(f"无法读取 Stage 8 数据集: {path}") from exc

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line, object_pairs_hook=_reject_duplicate_json_keys)
        except _DuplicateJsonKeyError as exc:
            raise _line_error(line_number, f"包含重复 JSON 键: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise _line_error(line_number, "不是合法 JSON") from exc
        if not isinstance(record, dict):
            raise _line_error(line_number, "必须是 JSON 对象")

        validate_stage8_record(
            record,
            line_number=line_number,
            require_approved=require_approved,
        )
        identifier = record["id"].strip()
        if identifier in seen_ids:
            raise _line_error(line_number, "字段 id 为空或重复")
        seen_ids.add(identifier)
        records.append(record)

    if not records:
        raise Stage8DatasetError("Stage 8 数据集没有有效样本")
    return records
