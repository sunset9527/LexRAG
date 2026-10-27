"""Create an immutable Stage 4 DB/Chroma provenance snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any
from urllib.parse import urlsplit

SOURCE_HASH_KEY = "lexrag_statute_source_sha256"
EMBEDDING_FINGERPRINT_KEY = "lexrag_embedding_fingerprint"
INDEX_SCHEMA_VERSION_KEY = "lexrag_index_schema_version"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DOCUMENT_PROVENANCE_FIELDS = (
    "version_id",
    "effective_from",
    "effective_to",
    "source_url",
    "content_hash",
)


class Stage4ProvenanceSnapshotError(ValueError):
    """Stage 4 state cannot be represented as one trusted immutable snapshot."""


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _nonblank(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage4ProvenanceSnapshotError(f"{label} is blank")
    return value


def _validate_https_url(value: Any) -> str:
    source_url = _nonblank(value, "source_url")
    if any(character.isspace() or ord(character) < 32 for character in source_url):
        raise Stage4ProvenanceSnapshotError("source_url is not safe HTTPS")
    try:
        parsed = urlsplit(source_url)
        _ = parsed.port
    except ValueError as exc:
        raise Stage4ProvenanceSnapshotError("source_url is not safe HTTPS") from exc
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or "@" in parsed.netloc
        or parsed.query
        or parsed.fragment
        or "\\" in source_url
    ):
        raise Stage4ProvenanceSnapshotError("source_url is not safe HTTPS")
    return source_url


def _knowledge_base_rows(service: Any) -> dict[str, Mapping[str, Any]]:
    rows = service.list_knowledge_bases()
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise Stage4ProvenanceSnapshotError("knowledge-base registry returned a non-object")
        slug = _nonblank(row.get("slug"), "knowledge-base slug")
        if slug in result:
            raise Stage4ProvenanceSnapshotError("knowledge-base registry has duplicate slug")
        result[slug] = row
    return result


def _expected_document_provenance(provenance: Mapping[str, Any]) -> dict[str, str]:
    effective_to = provenance.get("effective_to")
    return {
        "version_id": _nonblank(provenance.get("version_id"), "version_id"),
        "effective_from": _nonblank(provenance.get("effective_from"), "effective_from"),
        "effective_to": "" if effective_to in (None, "") else str(effective_to),
        "source_url": _validate_https_url(provenance.get("source_url")),
        "content_hash": _nonblank(provenance.get("content_hash"), "content_hash"),
    }


def _collection_article_ids(
    slug: str,
    collection: Mapping[str, Any],
    registry: Mapping[str, Any],
    provenance: Mapping[str, str],
) -> dict[str, Any]:
    expected_name = registry.get("collection_name")
    if collection.get("name") != expected_name:
        raise Stage4ProvenanceSnapshotError(f"{slug} collection identity disagrees with DB")
    metadata = collection.get("metadata")
    if not isinstance(metadata, Mapping):
        raise Stage4ProvenanceSnapshotError(f"{slug} collection identity metadata is missing")
    embedding_fingerprint = metadata.get(EMBEDDING_FINGERPRINT_KEY)
    if not isinstance(embedding_fingerprint, str) or not _SHA256.fullmatch(
        embedding_fingerprint
    ):
        raise Stage4ProvenanceSnapshotError(
            f"{slug} collection embedding fingerprint is invalid"
        )
    registry_fingerprint = registry.get("embedding_fingerprint")
    if registry_fingerprint is not None and registry_fingerprint != embedding_fingerprint:
        raise Stage4ProvenanceSnapshotError(f"{slug} collection identity/provenance disagrees with DB")
    index_schema_version = metadata.get(INDEX_SCHEMA_VERSION_KEY)
    if type(index_schema_version) is not int or index_schema_version <= 0:
        raise Stage4ProvenanceSnapshotError(
            f"{slug} collection index schema version is invalid"
        )
    registry_schema_version = registry.get("index_schema_version")
    if (
        registry_schema_version is not None
        and registry_schema_version != index_schema_version
    ):
        raise Stage4ProvenanceSnapshotError(f"{slug} collection identity/provenance disagrees with DB")
    collection_source_hash = metadata.get(SOURCE_HASH_KEY)
    if (
        collection_source_hash is not None
        and collection_source_hash != provenance["content_hash"]
    ):
        raise Stage4ProvenanceSnapshotError(f"{slug} collection provenance disagrees with DB")

    metadatas = collection.get("metadatas")
    if not isinstance(metadatas, list) or not metadatas:
        raise Stage4ProvenanceSnapshotError(f"{slug} collection has no article labels")
    chunk_count = len(metadatas)
    registry_chunk_count = registry.get("chunk_count")
    if registry_chunk_count is not None and registry_chunk_count != chunk_count:
        raise Stage4ProvenanceSnapshotError(f"{slug} registry chunk count disagrees with Chroma")
    article_ids: list[str] = []
    for document_metadata in metadatas:
        if not isinstance(document_metadata, Mapping):
            raise Stage4ProvenanceSnapshotError(f"{slug} collection has blank article label")
        article_id = _nonblank(document_metadata.get("article_id"), "article label")
        if any(document_metadata.get(field) != provenance[field] for field in _DOCUMENT_PROVENANCE_FIELDS):
            raise Stage4ProvenanceSnapshotError(
                f"{slug} document provenance disagrees with DB provenance"
            )
        article_ids.append(article_id)
    unique_article_ids = sorted(set(article_ids))
    registry_document_count = registry.get("document_count")
    if (
        registry_document_count is not None
        and registry_document_count != len(unique_article_ids)
    ):
        raise Stage4ProvenanceSnapshotError(
            f"{slug} registry document count disagrees with Chroma"
        )
    return {
        "article_ids": unique_article_ids,
        "embedding_fingerprint": embedding_fingerprint,
        "index_schema_version": index_schema_version,
        "chunk_count": chunk_count,
    }


def build_stage4_provenance_snapshot(
    slugs: Sequence[str],
    *,
    as_of: date,
    chain_service: Any,
    knowledge_base_service: Any,
    collection_reader: Callable[[str], Mapping[str, Any]],
) -> dict[str, Any]:
    """Read one effective verified chain and active Chroma collection per slug."""
    normalized_slugs = [_nonblank(slug, "requested slug") for slug in slugs]
    if not normalized_slugs:
        raise Stage4ProvenanceSnapshotError("at least one slug is required")
    if len(normalized_slugs) != len(set(normalized_slugs)):
        raise Stage4ProvenanceSnapshotError("requested slugs contain duplicate values")

    registry_by_slug = _knowledge_base_rows(knowledge_base_service)
    laws: list[dict[str, Any]] = []
    for slug in sorted(normalized_slugs):
        registry = registry_by_slug.get(slug)
        if registry is None:
            raise Stage4ProvenanceSnapshotError(f"{slug} is missing from the KB registry")
        if registry.get("status") != "READY":
            raise Stage4ProvenanceSnapshotError(f"{slug} active KB pointer is not READY")

        try:
            chain = chain_service.get_indexable_chain_for_law(slug, as_of=as_of)
            raw_provenance = chain_service.get_index_provenance(chain["id"], as_of=as_of)
        except (KeyError, TypeError, ValueError) as exc:
            raise Stage4ProvenanceSnapshotError(
                f"{slug} has no unique VERIFIED indexable effective chain"
            ) from exc
        if chain.get("law_slug") != slug or chain.get("is_indexable") is not True:
            raise Stage4ProvenanceSnapshotError(f"{slug} chain identity is not indexable")
        provenance = _expected_document_provenance(raw_provenance)
        if not _SHA256.fullmatch(provenance["content_hash"]):
            raise Stage4ProvenanceSnapshotError(f"{slug} content_hash is not lowercase SHA-256")
        registry_source_hash = registry.get("source_hash")
        if (
            registry_source_hash is not None
            and registry_source_hash != provenance["content_hash"]
        ):
            raise Stage4ProvenanceSnapshotError(f"{slug} registry provenance disagrees with DB")
        if chain.get("target_version_id") != provenance["version_id"]:
            raise Stage4ProvenanceSnapshotError(f"{slug} chain version disagrees with provenance")

        collection_name = _nonblank(registry.get("collection_name"), "collection_name")
        expected_collection_name = (
            f"kb_{slug.replace('-', '_')}_v_{provenance['content_hash'][:12]}"
        )
        if collection_name != expected_collection_name:
            raise Stage4ProvenanceSnapshotError(
                f"{slug} active collection name disagrees with verified chain content hash"
            )
        try:
            collection = collection_reader(collection_name)
        except Exception as exc:
            raise Stage4ProvenanceSnapshotError(f"{slug} active collection cannot be read") from exc
        if not isinstance(collection, Mapping):
            raise Stage4ProvenanceSnapshotError(f"{slug} collection reader returned a non-object")
        collection_facts = _collection_article_ids(slug, collection, registry, provenance)
        article_ids = collection_facts["article_ids"]
        laws.append(
            {
                "knowledge_base_slug": slug,
                "version_id": provenance["version_id"],
                "effective_from": provenance["effective_from"],
                "effective_to": provenance["effective_to"] or None,
                "source_url": provenance["source_url"],
                "content_hash": provenance["content_hash"],
                "collection_name": collection_name,
                "embedding_fingerprint": collection_facts["embedding_fingerprint"],
                "index_schema_version": collection_facts["index_schema_version"],
                "chunk_count": collection_facts["chunk_count"],
                "article_ids": article_ids,
                "article_ids_sha256": canonical_json_sha256(article_ids),
                "article_count": len(article_ids),
            }
        )
    return {
        "schema": "lexrag.stage4-provenance-snapshot",
        "version": 1,
        "as_of": as_of.isoformat(),
        "laws": laws,
    }
