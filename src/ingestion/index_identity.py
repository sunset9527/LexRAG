"""Stable identity metadata for embedding-backed Chroma collections."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


FINGERPRINT_METADATA_KEY = "lexrag_embedding_fingerprint"
PROVIDER_METADATA_KEY = "lexrag_embedding_provider"
MODEL_METADATA_KEY = "lexrag_embedding_model"
DIMENSIONS_METADATA_KEY = "lexrag_embedding_dimensions"
NORMALIZE_METADATA_KEY = "lexrag_embedding_normalize"
SCHEMA_VERSION_METADATA_KEY = "lexrag_index_schema_version"


class IndexIdentityError(RuntimeError):
    """A Chroma collection cannot safely be used with this embedding identity."""


class LegacyCollectionIdentityError(IndexIdentityError):
    """An unmarked legacy collection must be rebuilt explicitly."""

    code = "INDEX_IDENTITY_LEGACY_REBUILD_REQUIRED"

    def __init__(self) -> None:
        super().__init__(self.code)


class IndexIdentityMismatchError(IndexIdentityError):
    """The collection was built by a different embedding/index identity."""

    code = "INDEX_IDENTITY_MISMATCH"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class EmbeddingIndexIdentity:
    """Fields that define whether two vector collections are compatible."""

    provider: str
    model: str
    dimensions: int
    normalize: bool
    schema_version: int

    @property
    def fingerprint(self) -> str:
        payload = {
            "dimensions": self.dimensions,
            "model": self.model,
            "normalize": self.normalize,
            "provider": self.provider,
            "schema_version": self.schema_version,
        }
        canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def collection_metadata(self) -> dict[str, str | int | bool]:
        """Chroma-compatible scalar metadata persisted alongside each collection."""
        return {
            FINGERPRINT_METADATA_KEY: self.fingerprint,
            PROVIDER_METADATA_KEY: self.provider,
            MODEL_METADATA_KEY: self.model,
            DIMENSIONS_METADATA_KEY: self.dimensions,
            NORMALIZE_METADATA_KEY: self.normalize,
            SCHEMA_VERSION_METADATA_KEY: self.schema_version,
        }


def assert_collection_identity(collection: Any, expected: EmbeddingIndexIdentity) -> None:
    """Reject legacy or incompatible collection metadata before any read/write."""
    metadata: Mapping[str, Any] = getattr(collection, "metadata", None) or {}
    actual_fingerprint = metadata.get(FINGERPRINT_METADATA_KEY)
    if not actual_fingerprint:
        raise LegacyCollectionIdentityError()
    if actual_fingerprint != expected.fingerprint:
        raise IndexIdentityMismatchError()

    # Fingerprint is the compatibility decision.  The explicit fields make corruption
    # and manual metadata edits visible too, rather than accepting a partial marker.
    for key, expected_value in expected.collection_metadata().items():
        if metadata.get(key) != expected_value:
            raise IndexIdentityMismatchError()


def get_or_create_identity_collection(
    client: Any,
    collection_name: str,
    identity: EmbeddingIndexIdentity,
    *,
    additional_metadata: Mapping[str, str | int | bool] | None = None,
) -> Any:
    """Create collection metadata once, then validate it before every use.

    Chroma's ``get_or_create_collection`` preserves metadata for existing
    collections.  Therefore an old collection without the marker is detected as
    legacy instead of being silently adopted.
    """
    expected_metadata = identity.collection_metadata()
    if additional_metadata:
        expected_metadata.update(additional_metadata)
    # Opening an existing persistent collection through Chroma's
    # ``get_or_create_collection`` can trigger a write/backfill path.  That is
    # unnecessary for immutable verified indexes and has proven incompatible
    # with some legacy HNSW segments.  Read and validate first; create only
    # when the collection is genuinely absent.
    try:
        collection = client.get_collection(name=collection_name)
    except (AttributeError, ValueError, _collection_not_found_error()):
        collection = client.get_or_create_collection(name=collection_name, metadata=expected_metadata)
    assert_collection_identity(collection, identity)
    metadata: Mapping[str, Any] = getattr(collection, "metadata", None) or {}
    if any(metadata.get(key) != value for key, value in (additional_metadata or {}).items()):
        raise IndexIdentityMismatchError()
    return collection


def _collection_not_found_error() -> type[Exception]:
    """Keep identity helpers importable in test-only environments without Chroma."""
    try:
        from chromadb.errors import NotFoundError

        return NotFoundError
    except ImportError:
        return ValueError


def collection_identity_from_settings(settings: Any, *, zhipu_model: str | None = None) -> EmbeddingIndexIdentity:
    """Create an identity without exposing local paths or provider credentials."""
    provider = settings.embedding_provider
    model = settings.local_embedding_model_id if provider == "local" else (zhipu_model or settings.embedding_model)
    return EmbeddingIndexIdentity(
        provider=provider,
        model=model,
        dimensions=settings.embedding_dimensions,
        normalize=settings.embedding_normalize,
        schema_version=settings.index_schema_version,
    )
