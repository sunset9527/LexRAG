"""Rebuild physical Chroma HNSW segments in an isolated Stage 8 copy only."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from typing import Any


class Stage8VectorRepairError(RuntimeError):
    """A copied collection cannot safely become a Stage 8 evaluation candidate."""


_PAYLOAD_FIELDS = ("ids", "documents", "metadatas", "embeddings")
_IDENTITY_FIELDS = (
    "lexrag_embedding_fingerprint",
    "lexrag_index_schema_version",
)
_CHUNK_PROVENANCE_FIELDS = (
    "version_id",
    "effective_from",
    "effective_to",
    "source_url",
    "content_hash",
)


def _payload_sha256(payload: Mapping[str, Sequence[Any]]) -> str:
    try:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise Stage8VectorRepairError("collection payload is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _read_payload(collection: Any, law: Mapping[str, Any]) -> dict[str, list[Any]]:
    name = law["collection_name"]
    if getattr(collection, "name", None) != name:
        raise Stage8VectorRepairError("collection name differs from snapshot")
    metadata = getattr(collection, "metadata", None) or {}
    expected_identity = {
        "lexrag_embedding_fingerprint": law["embedding_fingerprint"],
        "lexrag_index_schema_version": law["index_schema_version"],
    }
    if not isinstance(metadata, Mapping) or any(
        metadata.get(field) != value for field, value in expected_identity.items()
    ):
        raise Stage8VectorRepairError("collection identity differs from snapshot")
    if collection.count() != law["chunk_count"]:
        raise Stage8VectorRepairError("collection chunk count differs from snapshot")

    result = collection.get(include=["documents", "metadatas", "embeddings"])
    if not isinstance(result, Mapping):
        raise Stage8VectorRepairError("collection payload is malformed")
    embeddings = result.get("embeddings")
    # Chroma returns NumPy arrays for persisted embeddings, while ``add`` and
    # canonical JSON reports require ordinary Python sequences.
    if hasattr(embeddings, "tolist"):
        embeddings = embeddings.tolist()
    payload = {
        "ids": result.get("ids"),
        "documents": result.get("documents"),
        "metadatas": result.get("metadatas"),
        "embeddings": embeddings,
    }
    if any(not isinstance(values, list) for values in payload.values()):
        raise Stage8VectorRepairError("collection payload fields are missing")
    count = len(payload["ids"])
    if count != law["chunk_count"] or any(len(values) != count for values in payload.values()):
        raise Stage8VectorRepairError("collection payload fields are not aligned")
    if len(set(payload["ids"])) != count or any(
        not isinstance(value, str) or not value.strip() for value in payload["ids"]
    ):
        raise Stage8VectorRepairError("collection has invalid chunk IDs")
    if any(not isinstance(value, str) for value in payload["documents"]):
        raise Stage8VectorRepairError("collection has invalid documents")

    expected_provenance = {field: law[field] for field in _CHUNK_PROVENANCE_FIELDS}
    expected_provenance["effective_to"] = expected_provenance["effective_to"] or ""
    article_ids = set()
    for chunk_metadata, embedding in zip(
        payload["metadatas"], payload["embeddings"], strict=True
    ):
        if not isinstance(chunk_metadata, Mapping):
            raise Stage8VectorRepairError("collection has invalid chunk metadata")
        article_id = chunk_metadata.get("article_id")
        if not isinstance(article_id, str) or not article_id.strip():
            raise Stage8VectorRepairError("collection has blank article identity")
        if any(chunk_metadata.get(field) != value for field, value in expected_provenance.items()):
            raise Stage8VectorRepairError("collection chunk provenance differs from snapshot")
        if (
            not isinstance(embedding, Sequence)
            or isinstance(embedding, (str, bytes))
            or not embedding
            or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in embedding)
        ):
            raise Stage8VectorRepairError("collection has invalid stored embedding")
        article_ids.add(article_id)
    if article_ids != set(law["article_ids"]):
        raise Stage8VectorRepairError("collection article catalog differs from snapshot")
    return payload


def _queryability_check(collection: Any, payload: Mapping[str, list[Any]]) -> None:
    try:
        result = collection.query(query_embeddings=[payload["embeddings"][0]], n_results=1)
    except Exception as exc:
        raise Stage8VectorRepairError("collection queryability check failed") from exc
    if not isinstance(result, Mapping) or not result.get("ids") or not result["ids"][0]:
        raise Stage8VectorRepairError("collection queryability check returned no result")


def rebuild_snapshot_collections(
    source_client: Any,
    target_client: Any,
    laws: Mapping[str, Mapping[str, Any]],
    *,
    batch_size: int = 128,
) -> dict[str, list[dict[str, Any]]]:
    """Recreate each snapshot-bound collection from its stored payload.

    The caller must provide separate clients pointing at the source and a copied
    target directory.  No embedding model is invoked: existing vectors are
    reinserted solely to regenerate Chroma's physical HNSW segment files.
    """
    if source_client is target_client:
        raise Stage8VectorRepairError("source and target clients must be distinct")
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size <= 0:
        raise Stage8VectorRepairError("batch size must be a positive integer")

    repaired = []
    for slug, law in laws.items():
        try:
            source = source_client.get_collection(name=law["collection_name"])
        except Exception as exc:
            raise Stage8VectorRepairError("source collection is unavailable") from exc
        payload = _read_payload(source, law)
        digest = _payload_sha256(payload)
        metadata = dict(source.metadata or {})
        try:
            target_client.delete_collection(name=law["collection_name"])
            target = target_client.create_collection(name=law["collection_name"], metadata=metadata)
            for start in range(0, len(payload["ids"]), batch_size):
                stop = start + batch_size
                target.add(**{field: payload[field][start:stop] for field in _PAYLOAD_FIELDS})
        except Exception as exc:
            raise Stage8VectorRepairError("target collection rebuild failed") from exc

        imported = _read_payload(target, law)
        if _payload_sha256(imported) != digest:
            raise Stage8VectorRepairError("target collection payload differs after rebuild")
        _queryability_check(target, imported)
        repaired.append(
            {
                "knowledge_base_slug": slug,
                "collection_name": law["collection_name"],
                "chunk_count": law["chunk_count"],
                "payload_sha256": digest,
                "queryable": True,
            }
        )
    return {"collections": repaired}


def repair_isolated_copy(
    source_directory: Any,
    target_directory: Any,
    laws: Mapping[str, Mapping[str, Any]],
    *,
    client_factory: Any,
    copytree: Any = shutil.copytree,
) -> dict[str, list[dict[str, Any]]]:
    """Copy a writable evaluation index, then regenerate only its physical vectors.

    The target must be new.  This one-way boundary makes it impossible for this
    repair operation to mutate the directory used as its evidence source.
    """
    source = source_directory.resolve()
    target = target_directory.resolve()
    if not source.is_dir():
        raise Stage8VectorRepairError("source directory must exist")
    if target.exists():
        raise Stage8VectorRepairError("target directory must not exist")
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise Stage8VectorRepairError("source and target directories must be disjoint")
    try:
        copytree(source, target)
        source_client = client_factory(str(source))
        target_client = client_factory(str(target))
    except Exception as exc:
        raise Stage8VectorRepairError("isolated copy setup failed") from exc
    return rebuild_snapshot_collections(source_client, target_client, laws)
