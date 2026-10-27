"""Export verified Stage 4 DB/Chroma provenance at an explicit as-of date."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.stage4_provenance_snapshot import (
    Stage4ProvenanceSnapshotError,
    build_stage4_provenance_snapshot,
)

DEFAULT_STAGE4_SLUGS = (
    "civil-code",
    "company-law",
    "copyright-law",
    "criminal-law",
    "labor-contract-law",
    "labor-law",
    "patent-law",
    "trademark-law",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", required=True, type=date.fromisoformat)
    parser.add_argument("--chroma-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--slug",
        action="append",
        dest="slugs",
        help="law slug to snapshot; repeat as needed (defaults to the eight Stage 4 laws)",
    )
    return parser


def _write_atomically(output: Path, payload: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_output_path(chroma_directory: Path, output: Path) -> None:
    chroma_root = chroma_directory.resolve()
    resolved_output = output.resolve()
    if resolved_output == chroma_root or resolved_output.is_relative_to(chroma_root):
        raise Stage4ProvenanceSnapshotError(
            "snapshot output must be outside the Chroma input directory"
        )


def _runtime_snapshot(slugs: list[str], *, as_of: date, chroma_directory: Path) -> dict[str, Any]:
    import chromadb

    from app.db import session as db_session
    from app.db.session import init_db
    from app.services.knowledge_base_service import KnowledgeBaseService
    from app.services.statute_version_chain_service import StatuteVersionChainService

    init_db()
    if db_session.SessionLocal is None:
        raise Stage4ProvenanceSnapshotError("database session is unavailable")
    client = chromadb.PersistentClient(path=str(chroma_directory))

    def read_collection(name: str) -> dict[str, Any]:
        collection = client.get_collection(name)
        return {
            "name": collection.name,
            "metadata": collection.metadata or {},
            "metadatas": collection.get(include=["metadatas"]).get("metadatas", []),
        }

    return build_stage4_provenance_snapshot(
        slugs,
        as_of=as_of,
        chain_service=StatuteVersionChainService(db_session.SessionLocal),
        knowledge_base_service=KnowledgeBaseService(db_session.SessionLocal),
        collection_reader=read_collection,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    slugs = args.slugs or list(DEFAULT_STAGE4_SLUGS)
    try:
        _validate_output_path(args.chroma_directory, args.output)
        snapshot = _runtime_snapshot(
            slugs,
            as_of=args.as_of,
            chroma_directory=args.chroma_directory,
        )
        payload = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        _write_atomically(args.output, payload)
    except (Stage4ProvenanceSnapshotError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        # Database/Chroma exceptions can embed connection strings.  Report only
        # the exception class so this maintenance command never leaks credentials.
        print(f"Stage 4 snapshot runtime failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "schema": snapshot["schema"],
                "as_of": snapshot["as_of"],
                "law_count": len(snapshot["laws"]),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
