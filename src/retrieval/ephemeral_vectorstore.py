"""Read-only in-process Chroma mirror for Windows persistent-index recovery."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from langchain_core.documents import Document


class EphemeralVectorStoreError(RuntimeError):
    """The persisted vector payload cannot safely become a runtime mirror."""


def _read_payload(source_collection: Any) -> dict[str, list[Any]]:
    """Read all stored values before initializing the local embedding runtime.

    Chroma's Windows persistent HNSW reader can fail after the transformer model
    has been loaded.  The source read deliberately happens first, and only reads
    stored vectors; it never invokes Chroma's persistent query path.
    """
    try:
        raw = source_collection.get(include=["documents", "metadatas", "embeddings"])
    except Exception as exc:
        raise EphemeralVectorStoreError("persistent payload is unavailable") from exc
    if not isinstance(raw, Mapping):
        raise EphemeralVectorStoreError("persistent payload is malformed")
    embeddings = raw.get("embeddings")
    if hasattr(embeddings, "tolist"):
        embeddings = embeddings.tolist()
    payload = {
        "ids": raw.get("ids"),
        "documents": raw.get("documents"),
        "metadatas": raw.get("metadatas"),
        "embeddings": embeddings,
    }
    if any(not isinstance(values, list) for values in payload.values()):
        raise EphemeralVectorStoreError("persistent payload fields are malformed")
    count = len(payload["ids"])
    if not count or any(len(values) != count for values in payload.values()):
        raise EphemeralVectorStoreError("persistent payload fields are misaligned")
    if len(set(payload["ids"])) != count or any(
        not isinstance(value, str) or not value for value in payload["ids"]
    ):
        raise EphemeralVectorStoreError("persistent payload contains invalid ids")
    if any(not isinstance(value, str) for value in payload["documents"]):
        raise EphemeralVectorStoreError("persistent payload contains invalid documents")
    if any(not isinstance(value, Mapping) for value in payload["metadatas"]):
        raise EphemeralVectorStoreError("persistent payload contains invalid metadata")
    if any(
        not isinstance(vector, Sequence)
        or isinstance(vector, (str, bytes))
        or not vector
        for vector in payload["embeddings"]
    ):
        raise EphemeralVectorStoreError("persistent payload contains invalid embeddings")
    return payload


class EphemeralVectorStore:
    """Small LangChain-compatible query facade over an in-process collection."""

    def __init__(self, *, client: Any, collection: Any, embeddings: Any) -> None:
        self._client = client  # Keep the ephemeral client alive with its collection.
        self._collection = collection
        self._embedding_function = embeddings

    def _query(self, query: str, *, k: int, filter: dict[str, Any] | None = None) -> list[tuple[Document, float]]:
        try:
            vector = self._embedding_function.embed_query(query)
            result = self._collection.query(
                query_embeddings=[vector],
                n_results=k,
                where=filter,
                include=["documents", "metadatas", "distances"],
            )
            documents = result["documents"][0]
            metadatas = result["metadatas"][0]
            distances = result["distances"][0]
        except Exception as exc:
            raise EphemeralVectorStoreError("runtime vector query failed") from exc
        if not (len(documents) == len(metadatas) == len(distances)):
            raise EphemeralVectorStoreError("runtime vector query returned misaligned results")
        return [
            (Document(page_content=document, metadata=dict(metadata or {})), float(distance))
            for document, metadata, distance in zip(documents, metadatas, distances, strict=True)
        ]

    def similarity_search_with_score(
        self, query: str, *, k: int, filter: dict[str, Any] | None = None
    ) -> list[tuple[Document, float]]:
        return self._query(query, k=k, filter=filter)

    def similarity_search_with_relevance_scores(
        self, query: str, *, k: int, filter: dict[str, Any] | None = None
    ) -> list[tuple[Document, float]]:
        # Stored BGE-M3 vectors are normalized and the existing Chroma indexes use
        # L2 distance.  Match LangChain's L2 relevance transformation.
        return [
            (document, max(0.0, 1.0 - distance / math.sqrt(2)))
            for document, distance in self._query(query, k=k, filter=filter)
        ]

    def similarity_search(
        self, query: str, *, k: int, filter: dict[str, Any] | None = None
    ) -> list[Document]:
        return [document for document, _distance in self._query(query, k=k, filter=filter)]

    def get(self, **kwargs: Any) -> dict[str, Any]:
        return self._collection.get(**kwargs)


def _build_from_payload(
    *,
    payload: dict[str, list[Any]],
    collection_name: str,
    embeddings_factory: Callable[[], Any],
    client_factory: Callable[[], Any] | None,
) -> EphemeralVectorStore:
    embeddings = embeddings_factory()
    if client_factory is None:
        from chromadb import EphemeralClient

        client_factory = EphemeralClient
    try:
        client = client_factory()
        collection = client.create_collection(name=f"runtime_{collection_name[:96]}")
        for start in range(0, len(payload["ids"]), 128):
            stop = start + 128
            collection.add(**{key: value[start:stop] for key, value in payload.items()})
    except Exception as exc:
        raise EphemeralVectorStoreError("runtime vector mirror initialization failed") from exc
    return EphemeralVectorStore(client=client, collection=collection, embeddings=embeddings)


def build_ephemeral_vectorstore(
    *,
    source_collection: Any,
    collection_name: str,
    embeddings_factory: Callable[[], Any],
    client_factory: Callable[[], Any] | None = None,
) -> EphemeralVectorStore:
    """Create an in-process mirror from existing vectors without re-embedding.

    The source must already have passed collection identity validation.  The
    temporary collection is intentionally process-local and is never persisted.
    """
    return _build_from_payload(
        payload=_read_payload(source_collection),
        collection_name=collection_name,
        embeddings_factory=embeddings_factory,
        client_factory=client_factory,
    )


def _load_verified_artifact_collection(
    artifact_path: str | Path, collection_name: str
) -> Mapping[str, Any]:
    """Return one integrity-checked runtime payload collection without loading embeddings."""
    path = Path(artifact_path)
    try:
        compressed = path.read_bytes()
        manifest_path = path.with_name(path.name.removesuffix(".json.gz") + ".manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact = json.loads(gzip.decompress(compressed).decode("utf-8"))
        selected = artifact["collections"]
        record = next(
            item
            for item in selected.values()
            if isinstance(item, Mapping) and item.get("collection_name") == collection_name
        )
        payload = record["payload"]
    except (OSError, KeyError, StopIteration, TypeError, ValueError) as exc:
        raise EphemeralVectorStoreError("runtime payload artifact is unavailable") from exc
    if artifact.get("schema") != "lexrag.stage8-runtime-payload" or artifact.get("version") != 1:
        raise EphemeralVectorStoreError("runtime payload artifact schema is invalid")
    if manifest.get("schema") != artifact["schema"] or manifest.get("version") != artifact["version"]:
        raise EphemeralVectorStoreError("runtime payload manifest schema is invalid")
    if manifest.get("payload_sha256") != hashlib.sha256(compressed).hexdigest():
        raise EphemeralVectorStoreError("runtime payload artifact checksum differs from manifest")
    if not isinstance(payload, Mapping):
        raise EphemeralVectorStoreError("runtime payload artifact is malformed")
    normalized = {key: payload.get(key) for key in ("ids", "documents", "metadatas", "embeddings")}
    manifest_record = next(
        (
            item
            for item in manifest.get("collections", [])
            if isinstance(item, Mapping) and item.get("collection_name") == collection_name
        ),
        None,
    )
    payload_bytes = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if not isinstance(manifest_record, Mapping) or manifest_record.get("payload_sha256") != hashlib.sha256(
        payload_bytes
    ).hexdigest():
        raise EphemeralVectorStoreError("runtime payload collection checksum differs from manifest")
    return normalized


def has_verified_runtime_collection(artifact_path: str | Path, collection_name: str) -> bool:
    """Whether an immutable runtime artifact safely provides a named collection."""
    try:
        _load_verified_artifact_collection(artifact_path, collection_name)
    except EphemeralVectorStoreError:
        return False
    return True


def build_ephemeral_vectorstore_from_artifact(
    *,
    artifact_path: str | Path,
    collection_name: str,
    embeddings_factory: Callable[[], Any],
    client_factory: Callable[[], Any] | None = None,
) -> EphemeralVectorStore:
    """Load one verified collection from a gzipped runtime-payload artifact."""
    normalized = _load_verified_artifact_collection(artifact_path, collection_name)
    # Reuse the strict source validation without opening any persistent Chroma client.
    class _ArtifactCollection:
        def get(self, *, include: list[str]) -> dict[str, Any]:
            if include != ["documents", "metadatas", "embeddings"]:
                raise ValueError("unexpected artifact read")
            return normalized

    return _build_from_payload(
        payload=_read_payload(_ArtifactCollection()),
        collection_name=collection_name,
        embeddings_factory=embeddings_factory,
        client_factory=client_factory,
    )
