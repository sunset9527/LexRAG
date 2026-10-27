"""Deterministically materialize the formal Stage 8 frozen dataset."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from src.evaluation.stage4_provenance_snapshot import canonical_json_sha256
from src.evaluation.stage8_dataset import validate_stage8_record
from src.evaluation.stage8_review_queue import QUEUE_RECORD_FIELDS

_SNAPSHOT_FIELDS = frozenset({"schema", "version", "as_of", "laws"})
_LAW_FIELDS = frozenset(
    {
        "knowledge_base_slug",
        "version_id",
        "effective_from",
        "effective_to",
        "source_url",
        "content_hash",
        "collection_name",
        "embedding_fingerprint",
        "index_schema_version",
        "chunk_count",
        "article_ids",
        "article_ids_sha256",
        "article_count",
    }
)
_SHA256 = re.compile(r"[0-9a-f]{64}")


class Stage8MaterializationError(ValueError):
    """Reviewed baseline and Stage 4 snapshot cannot produce a formal freeze."""


class _DuplicateKey(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(value)


def _nonblank(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage8MaterializationError(f"{label} must be a nonblank string")
    return value


def load_reviewed_baseline(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    """Load the immutable reviewed queue snapshot without transforming it."""
    try:
        payload = Path(path).read_bytes()
        lines = payload.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise Stage8MaterializationError(f"cannot read reviewed baseline: {path}") from exc
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(
                line,
                object_pairs_hook=_pairs,
                parse_constant=_reject_constant,
            )
        except (_DuplicateKey, ValueError, json.JSONDecodeError) as exc:
            raise Stage8MaterializationError(
                f"reviewed baseline line {line_number} is not strict JSON"
            ) from exc
        if not isinstance(row, dict) or set(row) != QUEUE_RECORD_FIELDS:
            raise Stage8MaterializationError(
                f"reviewed baseline line {line_number} must have the exact queue fields"
            )
        queue_id = _nonblank(row.get("queue_id"), "queue_id")
        if queue_id in seen:
            raise Stage8MaterializationError(f"duplicate queue_id: {queue_id}")
        seen.add(queue_id)
        rows.append(row)
    if not rows:
        raise Stage8MaterializationError("reviewed baseline is empty")
    return rows, payload


def load_stage4_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
    """Load a strict single-object Stage 4 snapshot."""
    try:
        payload = Path(path).read_bytes()
        snapshot = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, _DuplicateKey, ValueError, json.JSONDecodeError) as exc:
        raise Stage8MaterializationError(f"cannot read strict Stage 4 snapshot: {path}") from exc
    if not isinstance(snapshot, dict):
        raise Stage8MaterializationError("Stage 4 snapshot must be a JSON object")
    _snapshot_laws(snapshot)
    return snapshot, payload


def _snapshot_laws(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if set(snapshot) != _SNAPSHOT_FIELDS:
        raise Stage8MaterializationError("Stage 4 snapshot has an unexpected schema")
    if (
        snapshot.get("schema") != "lexrag.stage4-provenance-snapshot"
        or snapshot.get("version") != 1
    ):
        raise Stage8MaterializationError("unsupported Stage 4 snapshot schema/version")
    laws = snapshot.get("laws")
    if not isinstance(laws, list) or not laws:
        raise Stage8MaterializationError("Stage 4 snapshot laws must be nonempty")
    result: dict[str, Mapping[str, Any]] = {}
    for law in laws:
        if not isinstance(law, Mapping) or set(law) != _LAW_FIELDS:
            raise Stage8MaterializationError("Stage 4 snapshot law has unexpected fields")
        slug = _nonblank(law.get("knowledge_base_slug"), "knowledge_base_slug")
        if slug in result:
            raise Stage8MaterializationError(f"duplicate snapshot slug: {slug}")
        article_ids = law.get("article_ids")
        if (
            not isinstance(article_ids, list)
            or not article_ids
            or not all(isinstance(item, str) and item.strip() for item in article_ids)
            or len(article_ids) != len(set(article_ids))
        ):
            raise Stage8MaterializationError(f"{slug} snapshot article catalog is invalid")
        if article_ids != sorted(article_ids):
            raise Stage8MaterializationError(f"{slug} snapshot article catalog is not sorted")
        if law.get("article_count") != len(article_ids):
            raise Stage8MaterializationError(f"{slug} snapshot article count disagrees")
        if law.get("article_ids_sha256") != canonical_json_sha256(article_ids):
            raise Stage8MaterializationError(f"{slug} snapshot article hash disagrees")
        if not _SHA256.fullmatch(str(law.get("content_hash", ""))):
            raise Stage8MaterializationError(f"{slug} snapshot content hash is invalid")
        if not _SHA256.fullmatch(str(law.get("embedding_fingerprint", ""))):
            raise Stage8MaterializationError(
                f"{slug} snapshot embedding fingerprint is invalid"
            )
        if type(law.get("index_schema_version")) is not int or law["index_schema_version"] <= 0:
            raise Stage8MaterializationError(f"{slug} snapshot index schema version is invalid")
        if type(law.get("chunk_count")) is not int or law["chunk_count"] < len(article_ids):
            raise Stage8MaterializationError(f"{slug} snapshot chunk count is invalid")
        result[slug] = law
    return result


def _baseline_value(row: Mapping[str, Any], field: str, expected_type: type) -> Any:
    value = row.get(field)
    if type(value) is not expected_type:
        raise Stage8MaterializationError(f"{row.get('queue_id')} has invalid {field}")
    return value


def _validate_baseline_row(row: Mapping[str, Any]) -> None:
    queue_id = _nonblank(row.get("queue_id"), "queue_id")
    if set(row) != QUEUE_RECORD_FIELDS:
        raise Stage8MaterializationError(f"{queue_id} does not have exact queue fields")
    if row.get("review_state") != "approved":
        raise Stage8MaterializationError(f"{queue_id} review_state is not approved")
    for field in (
        "question",
        "proposed_question_type",
        "proposed_difficulty",
        "local_source_locator",
        "reviewer",
        "reviewed_at",
        "review_note",
    ):
        _nonblank(row.get(field), f"{queue_id}.{field}")
    slugs = _baseline_value(row, "proposed_knowledge_base_slugs", list)
    articles = _baseline_value(row, "proposed_relevant_article_ids", list)
    if not slugs or not all(isinstance(value, str) and value.strip() for value in slugs):
        raise Stage8MaterializationError(f"{queue_id} has invalid proposed slugs")
    if len(slugs) != len(set(slugs)):
        raise Stage8MaterializationError(f"{queue_id} has duplicate proposed slugs")
    if not all(isinstance(value, str) and value.strip() for value in articles):
        raise Stage8MaterializationError(f"{queue_id} has invalid proposed article IDs")
    should_abstain = row.get("proposed_should_abstain")
    if type(should_abstain) is not bool:
        raise Stage8MaterializationError(f"{queue_id} has invalid abstention label")
    if should_abstain == bool(articles):
        raise Stage8MaterializationError(f"{queue_id} has inconsistent abstention labels")


def materialize_stage8_records(
    baseline_rows: Sequence[Mapping[str, Any]],
    snapshot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Join reviewed labels with verified source facts without changing either."""
    laws = _snapshot_laws(snapshot)
    catalogs = {slug: set(law["article_ids"]) for slug, law in laws.items()}
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, row in enumerate(baseline_rows, 1):
        _validate_baseline_row(row)
        identifier = row["queue_id"]
        if identifier in seen_ids:
            raise Stage8MaterializationError(f"duplicate queue_id: {identifier}")
        seen_ids.add(identifier)
        slugs = list(row["proposed_knowledge_base_slugs"])
        missing_slugs = set(slugs) - laws.keys()
        if missing_slugs:
            raise Stage8MaterializationError(
                f"{identifier} snapshot is missing slugs: {', '.join(sorted(missing_slugs))}"
            )

        assigned: dict[str, list[str]] = {slug: [] for slug in slugs}
        for article_id in row["proposed_relevant_article_ids"]:
            matches = [slug for slug in slugs if article_id in catalogs[slug]]
            if not matches:
                raise Stage8MaterializationError(
                    f"{identifier} article {article_id} has zero snapshot catalog matches"
                )
            if len(matches) > 1:
                raise Stage8MaterializationError(
                    f"{identifier} article {article_id} has multiple snapshot catalog matches"
                )
            assigned[matches[0]].append(article_id)

        evidence: list[dict[str, Any]] = []
        for slug in slugs:
            law = laws[slug]
            evidence_articles = assigned[slug]
            locator = (
                "、".join(evidence_articles)
                if evidence_articles
                else f"{row['local_source_locator']} | knowledge_base_slug={slug}"
            )
            evidence.append(
                {
                    "knowledge_base_slug": slug,
                    "version_id": law["version_id"],
                    "effective_from": law["effective_from"],
                    "effective_to": law["effective_to"],
                    "source_url": law["source_url"],
                    "content_hash": law["content_hash"],
                    "article_ids": evidence_articles,
                    "source_locator": locator,
                }
            )
        record = {
            "id": identifier,
            "question": row["question"],
            "question_type": row["proposed_question_type"],
            "difficulty": row["proposed_difficulty"],
            "expected_knowledge_base_slugs": slugs,
            "relevant_article_ids": list(row["proposed_relevant_article_ids"]),
            "should_abstain": row["proposed_should_abstain"],
            "source_evidence": evidence,
            "reviewer": row["reviewer"],
            "reviewed_at": row["reviewed_at"],
            "review_note": row["review_note"],
            "review_status": "approved",
        }
        validate_stage8_record(record, line_number=line_number, require_approved=True)
        records.append(record)
    if not records:
        raise Stage8MaterializationError("reviewed baseline is empty")
    return records


def records_jsonl(records: Sequence[Mapping[str, Any]]) -> bytes:
    text = "\n".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records
    )
    return (text + "\n").encode("utf-8")


def build_stage8_manifest(
    records: Sequence[Mapping[str, Any]],
    *,
    dataset_payload: bytes,
    baseline_payload: bytes,
    snapshot_payload: bytes,
    generated_at: datetime,
) -> dict[str, Any]:
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise Stage8MaterializationError("generated_at must include a timezone")
    evidence_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    versions: dict[str, tuple[str, str]] = {}
    evidence_count = 0
    for record in records:
        for evidence in record["source_evidence"]:
            slug = evidence["knowledge_base_slug"]
            evidence_count += 1
            evidence_counts[slug] += 1
            label_counts[slug] += len(evidence["article_ids"])
            identity = (evidence["version_id"], evidence["content_hash"])
            if slug in versions and versions[slug] != identity:
                raise Stage8MaterializationError(f"{slug} uses inconsistent source versions")
            versions[slug] = identity
    return {
        "schema": "lexrag.stage8-frozen-dataset-manifest",
        "version": 1,
        "generated_at": generated_at.isoformat(),
        "dataset": {
            "row_count": len(records),
            "sha256": hashlib.sha256(dataset_payload).hexdigest(),
        },
        "inputs": {
            "reviewed_baseline_sha256": hashlib.sha256(baseline_payload).hexdigest(),
            "stage4_snapshot_sha256": hashlib.sha256(snapshot_payload).hexdigest(),
        },
        "evidence_count": evidence_count,
        "label_count": sum(len(record["relevant_article_ids"]) for record in records),
        "per_slug": {
            slug: {
                "version_id": versions[slug][0],
                "content_hash": versions[slug][1],
                "evidence_count": evidence_counts[slug],
                "label_count": label_counts[slug],
            }
            for slug in sorted(versions)
        },
        "provenance_statement": (
            "Derived from the human-reviewed baseline and Stage4 verified sources; "
            "this manifest freezes legal-label provenance only."
        ),
    }


def validate_formal_freeze_counts(records: Sequence[Mapping[str, Any]]) -> None:
    row_count = len(records)
    evidence_count = sum(len(record.get("source_evidence", [])) for record in records)
    label_count = sum(len(record.get("relevant_article_ids", [])) for record in records)
    if row_count != 280:
        raise Stage8MaterializationError(f"formal freeze requires 280 rows, got {row_count}")
    if evidence_count != 320:
        raise Stage8MaterializationError(
            f"formal freeze requires 320 evidence entries, got {evidence_count}"
        )
    if label_count != 460:
        raise Stage8MaterializationError(
            f"formal freeze requires 460 labels, got {label_count}"
        )
