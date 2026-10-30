"""Run Stage 8 formal oracle retrieval and automatic routing against a verified snapshot.

This result does not measure answer quality or abstention accuracy. No generation
method is called. The legacy engineering-regression runners remain independent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.run_manifest import build_run_manifest
from src.evaluation.stage8_dataset import load_stage8_dataset
from src.evaluation.stage8_materializer import load_stage4_snapshot, validate_formal_freeze_counts
from src.evaluation.stage8_retrieval_evaluation import (
    evaluate_oracle_retrieval,
    evaluate_routing,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--frozen-manifest", type=Path, required=True)
    parser.add_argument("--persist-directory", type=Path, required=True)
    parser.add_argument("--runtime-payload", type=Path)
    parser.add_argument("--mode", choices=("vector", "bm25", "rrf"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _validate_paths(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    chroma = args.persist_directory.resolve()
    if output in {args.dataset.resolve(), args.snapshot.resolve(), args.frozen_manifest.resolve()}:
        raise ValueError("output overlaps a source artifact")
    if output == chroma or output.is_relative_to(chroma):
        raise ValueError("output overlaps the Chroma input directory")
    if not chroma.is_dir():
        raise ValueError("persist-directory must already exist")
    if args.runtime_payload is not None and not args.runtime_payload.is_file():
        raise ValueError("runtime-payload must be an existing file")


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite manifest JSON constant")


def _shape(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError("unexpected frozen manifest schema")


def _load_frozen_manifest(args: argparse.Namespace) -> dict:
    manifest = json.loads(
        args.frozen_manifest.read_bytes().decode("utf-8"),
        object_pairs_hook=_strict_object,
        parse_constant=_reject_constant,
    )
    _shape(
        manifest,
        {
            "schema",
            "version",
            "generated_at",
            "dataset",
            "inputs",
            "evidence_count",
            "label_count",
            "per_slug",
            "provenance_statement",
        },
    )
    if (
        manifest["schema"] != "lexrag.stage8-frozen-dataset-manifest"
        or type(manifest["version"]) is not int
        or manifest["version"] != 1
    ):
        raise ValueError("unsupported frozen manifest schema/version")
    generated_at = datetime.fromisoformat(manifest["generated_at"])
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("frozen manifest timestamp must include a timezone")
    if (
        not isinstance(manifest["provenance_statement"], str)
        or not manifest["provenance_statement"].strip()
    ):
        raise ValueError("frozen manifest provenance statement is missing")
    _shape(manifest["dataset"], {"row_count", "sha256"})
    _shape(manifest["inputs"], {"reviewed_baseline_sha256", "stage4_snapshot_sha256"})
    for container, key, expected in (
        (manifest["dataset"], "row_count", 280),
        (manifest, "evidence_count", 320),
        (manifest, "label_count", 460),
    ):
        if type(container[key]) is not int or container[key] != expected:
            raise ValueError("frozen manifest has incorrect formal counts")
    digests = [manifest["dataset"]["sha256"], *manifest["inputs"].values()]
    if any(
        not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        for digest in digests
    ):
        raise ValueError("frozen manifest hash is invalid")
    for path, expected in (
        (args.dataset, manifest["dataset"]["sha256"]),
        (args.snapshot, manifest["inputs"]["stage4_snapshot_sha256"]),
    ):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("formal input bytes differ from frozen manifest")
    per_slug = manifest["per_slug"]
    if not isinstance(per_slug, dict) or not per_slug:
        raise ValueError("frozen manifest per-law identities are missing")
    for slug, law in per_slug.items():
        _shape(law, {"version_id", "content_hash", "evidence_count", "label_count"})
        if (
            not isinstance(slug, str)
            or not slug.strip()
            or not isinstance(law["version_id"], str)
            or not law["version_id"].strip()
        ):
            raise ValueError("frozen manifest law identity is invalid")
        if (
            not isinstance(law["content_hash"], str)
            or re.fullmatch(r"[0-9a-f]{64}", law["content_hash"]) is None
        ):
            raise ValueError("frozen manifest law hash is invalid")
        if any(
            type(law[key]) is not int or law[key] < 0 for key in ("evidence_count", "label_count")
        ):
            raise ValueError("frozen manifest law counts are invalid")
    return manifest


def _validate_frozen_records(records: list[dict], laws: dict[str, dict], frozen: dict) -> None:
    validate_formal_freeze_counts(records)
    if sum(row["should_abstain"] for row in records) != 20:
        raise ValueError("formal run requires 260 answerable and 20 abstention rows")
    actual = {
        slug: {
            "version_id": law["version_id"],
            "content_hash": law["content_hash"],
            "evidence_count": 0,
            "label_count": 0,
        }
        for slug, law in laws.items()
    }
    for row in records:
        for source in row["source_evidence"]:
            law = actual[source["knowledge_base_slug"]]
            law["evidence_count"] += 1
            law["label_count"] += len(source["article_ids"])
    if actual != frozen["per_slug"]:
        raise ValueError("formal records disagree with frozen per-law manifest")


def _dependency_versions() -> dict[str, str]:
    versions = {"python": platform.python_version()}
    for package in (
        "chromadb",
        "langchain-community",
        "langchain-core",
        "rank-bm25",
        "jieba",
        "sentence-transformers",
        "torch",
        "numpy",
    ):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "unavailable"
    return versions


def _bind_snapshot(records: list[dict], snapshot: dict) -> dict[str, dict]:
    laws = {law["knowledge_base_slug"]: law for law in snapshot["laws"]}
    expected = {slug for row in records for slug in row["expected_knowledge_base_slugs"]}
    if expected != set(laws):
        raise ValueError("dataset and snapshot law scopes differ")
    collections = [law["collection_name"] for law in laws.values()]
    if any(not isinstance(name, str) or not name.strip() for name in collections):
        raise ValueError("snapshot collection mapping is missing")
    if len(set(collections)) != len(collections):
        raise ValueError("snapshot collection mappings are not unique")
    for slug, law in laws.items():
        name = f"kb_{slug.replace('-', '_')}_v_{law['content_hash'][:12]}"
        if law["collection_name"] != name:
            raise ValueError("snapshot collection disagrees with source identity")
    for row in records:
        for source in row["source_evidence"]:
            law = laws[source["knowledge_base_slug"]]
            for field in (
                "version_id",
                "effective_from",
                "effective_to",
                "source_url",
                "content_hash",
            ):
                if source[field] != law[field]:
                    raise ValueError("dataset source provenance disagrees with snapshot")
            if not set(source["article_ids"]).issubset(law["article_ids"]):
                raise ValueError("dataset label is absent from snapshot article catalog")
    return laws


def _runtime_components():
    # Lazy imports keep --help and input validation independent of model loading.
    from chromadb import PersistentClient

    from config import settings
    from src.ingestion.index_identity import collection_identity_from_settings
    from src.ingestion.indexer import LawIndexer
    from src.retrieval.law_retriever import LawRetriever

    return (
        PersistentClient,
        LawIndexer,
        LawRetriever,
        collection_identity_from_settings(settings, zhipu_model="embedding-3"),
    )


class _QueryFailureGuard:
    """Observe vector errors that the legacy LawRetriever converts to an empty list."""

    def __init__(self, vectorstore):
        self.vectorstore = vectorstore
        self.error_type: str | None = None

    def __getattr__(self, name):
        attribute = getattr(self.vectorstore, name)
        if not name.startswith("similarity_search") or not callable(attribute):
            return attribute

        def observed(*args, **kwargs):
            try:
                return attribute(*args, **kwargs)
            except Exception as exc:
                self.error_type = type(exc).__name__
                raise RuntimeError("vector query failed") from None

        return observed


def _verify_legacy_chunks(collection: Any, law: dict) -> None:
    """Apply Stage 4's document-level proof when a collection has no source marker."""
    result = collection.get(include=["metadatas"])
    chunks = result.get("metadatas") if isinstance(result, Mapping) else None
    if not isinstance(chunks, list) or len(chunks) != law["chunk_count"]:
        raise ValueError("legacy collection chunk metadata count differs from snapshot")
    provenance = {
        field: law[field]
        for field in ("version_id", "effective_from", "effective_to", "source_url", "content_hash")
    }
    # Stage 4 stores an open-ended effective_to as an empty Chroma scalar,
    # while its JSON snapshot represents the same boundary as null.
    provenance["effective_to"] = law["effective_to"] or ""
    articles = set()
    for chunk in chunks:
        if not isinstance(chunk, Mapping):
            raise ValueError("legacy collection contains malformed chunk metadata")
        article = chunk.get("article_id")
        if not isinstance(article, str) or not article.strip():
            raise ValueError("legacy collection contains a blank article identity")
        if any(chunk.get(field) != value for field, value in provenance.items()):
            raise ValueError("legacy collection chunk provenance differs from snapshot")
        articles.add(article)
    if articles != set(law["article_ids"]):
        raise ValueError("legacy collection article catalog differs from snapshot")


def _build_retrievers(
    laws: dict[str, dict], directory: Path, runtime_payload: Path | None = None
) -> dict[str, Any]:
    client_type, indexer_type, retriever_type, identity = _runtime_components()
    if runtime_payload is not None:
        from config import settings
        from src.retrieval.ephemeral_vectorstore import build_ephemeral_vectorstore_from_artifact
        from src.utils.embedding_factory import create_embeddings

        retrievers = {}
        for slug, law in laws.items():
            if (
                identity.fingerprint != law["embedding_fingerprint"]
                or identity.schema_version != law["index_schema_version"]
            ):
                raise ValueError("configured embedding/index identity differs from snapshot")
            vectorstore = build_ephemeral_vectorstore_from_artifact(
                artifact_path=runtime_payload,
                collection_name=law["collection_name"],
                embeddings_factory=lambda: create_embeddings(
                    provider=settings.embedding_provider,
                    model_path=settings.local_embedding_model_path,
                    local_model_id=settings.local_embedding_model_id,
                    zhipuai_api_key=settings.zhipuai_api_key,
                    zhipuai_model=settings.embedding_model,
                    dimensions=settings.embedding_dimensions,
                    normalize=settings.embedding_normalize,
                    index_schema_version=settings.index_schema_version,
                ),
            )
            retriever = retriever_type(vectorstore)
            retrievers[slug] = retriever
        return retrievers
    client = client_type(path=str(directory))
    source_hashes = {}
    # Check every existing collection before LawIndexer can get-or-create any.
    for law in laws.values():
        if (
            identity.fingerprint != law["embedding_fingerprint"]
            or identity.schema_version != law["index_schema_version"]
        ):
            raise ValueError("configured embedding/index identity differs from snapshot")
        collection = client.get_collection(name=law["collection_name"])
        metadata = collection.metadata or {}
        expected = {
            "lexrag_embedding_fingerprint": law["embedding_fingerprint"],
            "lexrag_index_schema_version": law["index_schema_version"],
        }
        if collection.name != law["collection_name"] or any(
            metadata.get(key) != value for key, value in expected.items()
        ):
            raise ValueError("live collection provenance differs from snapshot")
        if collection.count() != law["chunk_count"]:
            raise ValueError("live collection chunk count differs from snapshot")
        source_hash = metadata.get("lexrag_statute_source_sha256")
        if source_hash is None:
            _verify_legacy_chunks(collection, law)
        elif source_hash != law["content_hash"]:
            raise ValueError("live collection source hash differs from snapshot")
        source_hashes[law["knowledge_base_slug"]] = source_hash
    retrievers = {}
    for slug, law in laws.items():
        indexer = indexer_type(
            persist_directory=str(directory),
            collection_name=law["collection_name"],
            # LawIndexer must not demand or add a collection source marker for
            # legacy collections just proven through every chunk's provenance.
            source_hash=source_hashes[slug],
        )
        retriever = retriever_type(indexer.vectorstore)
        if hasattr(retriever, "vectorstore"):
            retriever.vectorstore = _QueryFailureGuard(retriever.vectorstore)
        retrievers[slug] = retriever
    return retrievers


def _retrieval_callback(laws: dict[str, dict], retrievers: dict, mode: str):
    from src.ingestion.statute_catalog import statute_by_slug

    # Catalog lookup must succeed before any evaluator call; no civil-law default.
    names = {slug: statute_by_slug(slug).definition.name for slug in laws}
    article_laws: dict[str, list[str]] = {}
    for slug, law in laws.items():
        for article in law["article_ids"]:
            article_laws.setdefault(article, []).append(slug)

    def retrieve(question: str, slug: str, top_k: int):
        try:
            retriever = retrievers[slug]
            guard = getattr(retriever, "vectorstore", None)
            if isinstance(guard, _QueryFailureGuard):
                guard.error_type = None
            if mode == "vector":
                results = retriever.retrieve(question, top_k=top_k)
                articles = [result.article_id for result in results]
            else:
                retriever._ensure_optimization_data()
                if retriever._bm25 is None or not retriever.enable_optimization:
                    raise RuntimeError("BM25 optimization data unavailable")
                if mode == "bm25":
                    results = retriever._bm25.retrieve(question, top_k=top_k * 5)
                    articles = [(result.metadata or {}).get("article_id") for result in results]
                else:
                    results, _, _ = retriever.retrieve_optimized(
                        question, top_k=top_k, law_name=names[slug]
                    )
                    articles = [result.article_id for result in results]
            if isinstance(guard, _QueryFailureGuard) and guard.error_type is not None:
                raise RuntimeError("vector query failed")
            evidence = []
            for article in articles:
                owners = article_laws.get(article, [])
                if len(owners) != 1:
                    raise ValueError("result has an unknown or ambiguous snapshot article identity")
                item = {"knowledge_base_slug": owners[0], "article_id": article}
                if item not in evidence:
                    evidence.append(item)
                if len(evidence) == top_k:
                    break
            return evidence
        except Exception as exc:
            # The pure evaluator retains messages; never pass provider exception
            # text (which can contain credentials) into that report boundary.
            raise RuntimeError(f"retrieval failed ({type(exc).__name__})") from None

    return retrieve


def _make_router():
    from src.retrieval.knowledge_base_router import KnowledgeBaseRouter

    return KnowledgeBaseRouter()


def _routing_callback(laws: dict[str, dict]):
    router = _make_router()
    available = [{"slug": slug} for slug in laws]

    def route(question: str):
        try:
            decision = router.route(question, available)
            return [candidate.slug for candidate in decision.candidates]
        except Exception as exc:
            raise RuntimeError(f"routing failed ({type(exc).__name__})") from None

    return route


def _write_atomically(output: Path, report: dict) -> None:
    payload = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_runtime_payload(payload_path: Path, snapshot_path: Path, laws: Mapping[str, Mapping[str, Any]]) -> dict:
    manifest_path = payload_path.with_name(payload_path.name.removesuffix(".json.gz") + ".manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("runtime payload manifest is unavailable") from exc
    if manifest.get("schema") != "lexrag.stage8-runtime-payload" or manifest.get("version") != 1:
        raise ValueError("runtime payload manifest schema is invalid")
    if manifest.get("snapshot_sha256") != hashlib.sha256(snapshot_path.read_bytes()).hexdigest():
        raise ValueError("runtime payload manifest snapshot differs from formal snapshot")
    expected = {
        law["collection_name"]: law["chunk_count"]
        for law in laws.values()
    }
    actual = {
        item.get("collection_name"): item.get("chunk_count")
        for item in manifest.get("collections", [])
        if isinstance(item, Mapping)
    }
    if actual != expected:
        raise ValueError("runtime payload collection scope differs from snapshot")
    return {"path": str(payload_path.resolve()), "sha256": hashlib.sha256(payload_path.read_bytes()).hexdigest(), "manifest": str(manifest_path.resolve())}


def _runner_commit() -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _validate_paths(args)
        frozen = _load_frozen_manifest(args)
        records = load_stage8_dataset(args.dataset, require_approved=True)
        snapshot, _ = load_stage4_snapshot(args.snapshot)
        laws = _bind_snapshot(records, snapshot)
        _validate_frozen_records(records, laws, frozen)
        runtime_payload = (
            _validate_runtime_payload(args.runtime_payload, args.snapshot, laws)
            if args.runtime_payload is not None
            else None
        )
        manifest = build_run_manifest(
            run_name=f"stage8-formal-retrieval-routing-{args.mode}",
            dataset_paths=[args.dataset],
            legal_source_manifest_paths=[args.snapshot, args.frozen_manifest],
            collection_names=[law["collection_name"] for law in laws.values()],
            embedding_version=json.dumps(
                {slug: law["embedding_fingerprint"] for slug, law in laws.items()}, sort_keys=True
            ),
            # Stage 4 records index schema, not a chunker implementation version.
            # Expose that limitation instead of claiming the current default.
            chunker_version="not-recorded-in-stage4-snapshot;index-schema="
            + json.dumps(
                {slug: law["index_schema_version"] for slug, law in laws.items()}, sort_keys=True
            ),
            runtime_identity={"provider": "local", "model": "no-model"},
            commit_provider=_runner_commit,
            dependency_versions=_dependency_versions(),
        )
        retrievers = _build_retrievers(laws, args.persist_directory, args.runtime_payload)
        report = {
            "schema": "lexrag.stage8-formal-retrieval-routing",
            "version": 1,
            "mode": args.mode,
            "scope": "Stage 8 formal oracle retrieval and automatic routing only; does not measure answer quality or abstention accuracy.",
            "dataset": manifest["datasets"][0],
            "frozen_manifest": manifest["legal_source_manifests"][1],
            "snapshot": {
                **manifest["legal_source_manifests"][0],
                "as_of": snapshot["as_of"],
                "laws": snapshot["laws"],
            },
            "persist_directory": str(args.persist_directory.resolve()),
            **({"runtime_payload": runtime_payload} if runtime_payload else {}),
            "run_manifest": manifest,
            "oracle_retrieval": evaluate_oracle_retrieval(
                records, _retrieval_callback(laws, retrievers, args.mode)
            ),
            "routing": evaluate_routing(records, _routing_callback(laws)),
        }
        _write_atomically(args.output, report)
    except Exception as exc:
        print(f"Stage 8 formal retrieval/routing failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(f"Stage 8 formal retrieval/routing report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
