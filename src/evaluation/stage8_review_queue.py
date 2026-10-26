"""Compose the pending-only Stage 8 human review queue.

This module deliberately creates candidates for human review, never a frozen or
formal evaluation dataset.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

QUEUE_RECORD_FIELDS = frozenset(
    {
        "queue_id",
        "origin",
        "question",
        "proposed_question_type",
        "proposed_difficulty",
        "proposed_knowledge_base_slugs",
        "proposed_relevant_article_ids",
        "proposed_should_abstain",
        "local_source_locator",
        "review_state",
        "reviewer",
        "reviewed_at",
        "review_note",
        "verified_record",
    }
)

_LEGACY_REQUIRED_FIELDS = frozenset(
    {
        "id",
        "query",
        "knowledge_base_slug",
        "relevant_article_ids",
        "source_locator",
    }
)
_HARD_REQUIRED_FIELDS = frozenset(
    {
        "candidate_id",
        "question",
        "proposed_question_type",
        "proposed_difficulty",
        "proposed_knowledge_base_slugs",
        "proposed_relevant_article_ids",
        "proposed_should_abstain",
        "local_source_locator",
    }
)
_APPROVAL_FIELDS = frozenset(
    {"approved", "verified", "review_status", "review_state", "verified_record"}
)


class Stage8ReviewQueueError(ValueError):
    """Stage 8 candidate-review queue input does not meet its contract."""


def _nonblank_string(value: Any, field: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage8ReviewQueueError(f"{context} 的 {field} 必须是非空字符串")
    return value.strip()


def _string_list(value: Any, field: str, context: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        required = "可为空列表" if allow_empty else "必须是非空列表"
        raise Stage8ReviewQueueError(f"{context} 的 {field} {required}")
    return [_nonblank_string(item, field, context) for item in value]


def _validate_proposed_values(
    record: Mapping[str, Any],
    *,
    context: str,
) -> dict[str, Any]:
    question = _nonblank_string(record.get("question"), "question", context)
    question_type = _nonblank_string(
        record.get("proposed_question_type"), "proposed_question_type", context
    )
    difficulty = _nonblank_string(record.get("proposed_difficulty"), "proposed_difficulty", context)
    knowledge_bases = _string_list(
        record.get("proposed_knowledge_base_slugs"),
        "proposed_knowledge_base_slugs",
        context,
        allow_empty=False,
    )
    article_ids = _string_list(
        record.get("proposed_relevant_article_ids"),
        "proposed_relevant_article_ids",
        context,
        allow_empty=True,
    )
    should_abstain = record.get("proposed_should_abstain")
    if type(should_abstain) is not bool:
        raise Stage8ReviewQueueError(f"{context} 的 proposed_should_abstain 必须是布尔值")
    if should_abstain and article_ids:
        raise Stage8ReviewQueueError(f"{context} 的弃答候选不能提供 proposed_relevant_article_ids")
    if not should_abstain and not article_ids:
        raise Stage8ReviewQueueError(
            f"{context} 的非弃答候选必须提供 proposed_relevant_article_ids"
        )
    locator = _nonblank_string(record.get("local_source_locator"), "local_source_locator", context)
    return {
        "question": question,
        "proposed_question_type": question_type,
        "proposed_difficulty": difficulty,
        "proposed_knowledge_base_slugs": knowledge_bases,
        "proposed_relevant_article_ids": article_ids,
        "proposed_should_abstain": should_abstain,
        "local_source_locator": locator,
    }


def _pending_record(queue_id: str, origin: str, proposed: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "queue_id": queue_id,
        "origin": origin,
        "question": proposed["question"],
        "proposed_question_type": proposed["proposed_question_type"],
        "proposed_difficulty": proposed["proposed_difficulty"],
        "proposed_knowledge_base_slugs": proposed["proposed_knowledge_base_slugs"],
        "proposed_relevant_article_ids": proposed["proposed_relevant_article_ids"],
        "proposed_should_abstain": proposed["proposed_should_abstain"],
        "local_source_locator": proposed["local_source_locator"],
        "review_state": "pending",
        "reviewer": "",
        "reviewed_at": "",
        "review_note": "",
        "verified_record": None,
    }


def _validate_legacy_defaults(
    *,
    legacy_question_type: object,
    legacy_difficulty: object,
    legacy_should_abstain: object,
) -> tuple[str, str, bool]:
    question_type = _nonblank_string(legacy_question_type, "legacy_question_type", "legacy 默认值")
    difficulty = _nonblank_string(legacy_difficulty, "legacy_difficulty", "legacy 默认值")
    if type(legacy_should_abstain) is not bool:
        raise Stage8ReviewQueueError("legacy 默认值的 legacy_should_abstain 必须是布尔值")
    return question_type, difficulty, legacy_should_abstain


def _legacy_queue_record(
    record: Mapping[str, Any],
    index: int,
    *,
    question_type: str,
    difficulty: str,
    should_abstain: bool,
) -> dict[str, Any]:
    context = f"第 {index} 条 legacy seed"
    if not isinstance(record, Mapping):
        raise Stage8ReviewQueueError(f"{context} 必须是 JSON 对象")
    missing = _LEGACY_REQUIRED_FIELDS - record.keys()
    if missing:
        raise Stage8ReviewQueueError(f"{context} 缺少字段: {', '.join(sorted(missing))}")
    queue_id = _nonblank_string(record["id"], "id", context)
    article_ids = _string_list(
        record["relevant_article_ids"], "relevant_article_ids", context, allow_empty=True
    )
    if should_abstain and article_ids:
        raise Stage8ReviewQueueError(f"{context} 的弃答默认值不能搭配相关法条")
    if not should_abstain and not article_ids:
        raise Stage8ReviewQueueError(f"{context} 的非弃答默认值必须搭配相关法条")
    proposed = {
        "question": _nonblank_string(record["query"], "query", context),
        "proposed_question_type": question_type,
        "proposed_difficulty": difficulty,
        "proposed_knowledge_base_slugs": [
            _nonblank_string(record["knowledge_base_slug"], "knowledge_base_slug", context)
        ],
        "proposed_relevant_article_ids": article_ids,
        "proposed_should_abstain": should_abstain,
        "local_source_locator": _nonblank_string(
            record["source_locator"], "source_locator", context
        ),
    }
    return _pending_record(queue_id, "legacy_seed", proposed)


def _approval_claimed(record: Mapping[str, Any]) -> str | None:
    for field in _APPROVAL_FIELDS & record.keys():
        value = record[field]
        if field == "verified_record" and value is not None:
            return field
        if value is True:
            return field
        if isinstance(value, str) and value.strip().lower() in {"approved", "verified"}:
            return field
    return None


def _hard_queue_record(record: Mapping[str, Any], index: int) -> dict[str, Any]:
    context = f"第 {index} 条 hard candidate"
    if not isinstance(record, Mapping):
        raise Stage8ReviewQueueError(f"{context} 必须是 JSON 对象")
    claimed_field = _approval_claimed(record)
    if claimed_field is not None:
        raise Stage8ReviewQueueError(
            f"{context} 不得标记为 approved 或 verified（{claimed_field}）"
        )
    unknown = set(record) - _HARD_REQUIRED_FIELDS
    if unknown:
        raise Stage8ReviewQueueError(f"{context} 包含未知字段: {', '.join(sorted(unknown))}")
    missing = _HARD_REQUIRED_FIELDS - record.keys()
    if missing:
        raise Stage8ReviewQueueError(f"{context} 缺少字段: {', '.join(sorted(missing))}")
    queue_id = _nonblank_string(record["candidate_id"], "candidate_id", context)
    return _pending_record(
        queue_id, "hard_candidate", _validate_proposed_values(record, context=context)
    )


def compose_stage8_review_queue(
    legacy_seed_records: Sequence[Mapping[str, Any]],
    hard_candidate_records: Sequence[Mapping[str, Any]],
    *,
    legacy_question_type: str,
    legacy_difficulty: str,
    legacy_should_abstain: bool,
) -> list[dict[str, Any]]:
    """Return the 100+200 pending candidate queue for human review.

    The returned queue is not a frozen/formal Stage 8 evaluation dataset.
    """
    if len(legacy_seed_records) != 100:
        raise Stage8ReviewQueueError(
            f"Stage 8 review queue 必须恰有 100 条 legacy seed，收到 {len(legacy_seed_records)} 条"
        )
    if len(hard_candidate_records) != 200:
        raise Stage8ReviewQueueError(
            f"Stage 8 review queue 必须恰有 200 条 hard candidate，收到 {len(hard_candidate_records)} 条"
        )
    question_type, difficulty, should_abstain = _validate_legacy_defaults(
        legacy_question_type=legacy_question_type,
        legacy_difficulty=legacy_difficulty,
        legacy_should_abstain=legacy_should_abstain,
    )
    queue = [
        _legacy_queue_record(
            record,
            index,
            question_type=question_type,
            difficulty=difficulty,
            should_abstain=should_abstain,
        )
        for index, record in enumerate(legacy_seed_records, start=1)
    ]
    queue.extend(
        _hard_queue_record(record, index)
        for index, record in enumerate(hard_candidate_records, start=1)
    )
    queue_ids = [record["queue_id"] for record in queue]
    if len(set(queue_ids)) != len(queue_ids):
        raise Stage8ReviewQueueError("Stage 8 review queue 包含重复 queue_id")
    return queue
