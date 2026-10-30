"""Export verified Stage 8 collection payloads before loading any embedding model."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def export_payloads(*, source_directory: Path, snapshot_path: Path, output_path: Path) -> dict[str, Any]:
    """Create an auditable compressed payload without querying persistent HNSW."""
    from chromadb import PersistentClient

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    laws = snapshot.get("laws")
    if not isinstance(laws, list) or len(laws) != 8:
        raise ValueError("snapshot must define exactly eight laws")
    client = PersistentClient(path=str(source_directory))
    collections: dict[str, dict[str, Any]] = {}
    manifest_collections: list[dict[str, Any]] = []
    for law in laws:
        if not isinstance(law, dict):
            raise ValueError("snapshot law record is invalid")
        slug = law["knowledge_base_slug"]
        name = law["collection_name"]
        collection = client.get_collection(name=name)
        metadata = collection.metadata or {}
        for field in ("lexrag_embedding_fingerprint", "lexrag_index_schema_version"):
            expected = law["embedding_fingerprint"] if field.endswith("fingerprint") else law["index_schema_version"]
            if metadata.get(field) != expected:
                raise ValueError("source collection identity differs from snapshot")
        result = collection.get(include=["documents", "metadatas", "embeddings"])
        embeddings = result.get("embeddings")
        if hasattr(embeddings, "tolist"):
            embeddings = embeddings.tolist()
        payload = {
            "ids": result.get("ids"),
            "documents": result.get("documents"),
            "metadatas": result.get("metadatas"),
            "embeddings": embeddings,
        }
        if any(not isinstance(value, list) for value in payload.values()):
            raise ValueError("source collection payload is malformed")
        if any(len(value) != law["chunk_count"] for value in payload.values()):
            raise ValueError("source collection payload count differs from snapshot")
        article_ids = {item.get("article_id") for item in payload["metadatas"] if isinstance(item, dict)}
        if article_ids != set(law["article_ids"]):
            raise ValueError("source collection article catalog differs from snapshot")
        collections[slug] = {"collection_name": name, "payload": payload}
        manifest_collections.append(
            {
                "knowledge_base_slug": slug,
                "collection_name": name,
                "chunk_count": law["chunk_count"],
                "payload_sha256": hashlib.sha256(_canonical_bytes(payload)).hexdigest(),
            }
        )
    artifact = {"schema": "lexrag.stage8-runtime-payload", "version": 1, "collections": collections}
    compressed = gzip.compress(_canonical_bytes(artifact), mtime=0)
    _write_atomic_bytes(output_path, compressed)
    return {
        "schema": artifact["schema"],
        "version": artifact["version"],
        "snapshot_sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        "payload_sha256": hashlib.sha256(compressed).hexdigest(),
        "collections": manifest_collections,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-directory", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.manifest.exists():
            raise ValueError("output and manifest must be new paths")
        manifest = export_payloads(
            source_directory=args.source_directory,
            snapshot_path=args.snapshot,
            output_path=args.output,
        )
        _write_atomic_bytes(args.manifest, _canonical_bytes(manifest) + b"\n")
    except Exception as exc:
        print(f"runtime payload export failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
