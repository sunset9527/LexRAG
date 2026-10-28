"""Run Stage 8 formal oracle retrieval and automatic routing against a verified snapshot.

This result does not measure answer quality or abstention accuracy. No generation
method is called. The legacy engineering-regression runners remain independent.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.run_manifest import build_run_manifest
from src.evaluation.stage8_dataset import load_stage8_dataset
from src.evaluation.stage8_materializer import load_stage4_snapshot
from src.evaluation.stage8_retrieval_evaluation import (
    evaluate_oracle_retrieval,
    evaluate_routing,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--persist-directory", type=Path, required=True)
    parser.add_argument("--mode", choices=("vector", "bm25", "rrf"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _validate_paths(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    chroma = args.persist_directory.resolve()
    if output in {args.dataset.resolve(), args.snapshot.resolve()}:
        raise ValueError("output overlaps a source artifact")
    if output == chroma or output.is_relative_to(chroma):
        raise ValueError("output overlaps the Chroma input directory")
    if not chroma.is_dir():
        raise ValueError("persist-directory must already exist")


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


def _build_retrievers(laws: dict[str, dict], directory: Path) -> dict[str, Any]:
    client_type, indexer_type, retriever_type, identity = _runtime_components()
    client = client_type(path=str(directory))
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
            "lexrag_statute_source_sha256": law["content_hash"],
            "lexrag_embedding_fingerprint": law["embedding_fingerprint"],
            "lexrag_index_schema_version": law["index_schema_version"],
        }
        if collection.name != law["collection_name"] or any(
            metadata.get(key) != value for key, value in expected.items()
        ):
            raise ValueError("live collection provenance differs from snapshot")
        if collection.count() != law["chunk_count"]:
            raise ValueError("live collection chunk count differs from snapshot")
    retrievers = {}
    for slug, law in laws.items():
        indexer = indexer_type(
            persist_directory=str(directory),
            collection_name=law["collection_name"],
            source_hash=law["content_hash"],
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
        records = load_stage8_dataset(args.dataset, require_approved=True)
        snapshot, _ = load_stage4_snapshot(args.snapshot)
        laws = _bind_snapshot(records, snapshot)
        manifest = build_run_manifest(
            run_name=f"stage8-formal-retrieval-routing-{args.mode}",
            dataset_paths=[args.dataset],
            legal_source_manifest_paths=[args.snapshot],
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
        )
        retrievers = _build_retrievers(laws, args.persist_directory)
        report = {
            "schema": "lexrag.stage8-formal-retrieval-routing",
            "version": 1,
            "mode": args.mode,
            "scope": "Stage 8 formal oracle retrieval and automatic routing only; does not measure answer quality or abstention accuracy.",
            "dataset": manifest["datasets"][0],
            "snapshot": {
                **manifest["legal_source_manifests"][0],
                "as_of": snapshot["as_of"],
                "laws": snapshot["laws"],
            },
            "persist_directory": str(args.persist_directory.resolve()),
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
