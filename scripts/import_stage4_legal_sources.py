"""Register reviewed-scope local legal originals as non-authoritative candidates.

This command never builds a vector index and never grants authority status.  Run
``alembic upgrade head`` first, then use ``--dry-run`` to inspect the catalogue
before persisting source records.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import session as db_session
from app.db.session import init_db
from app.services.legal_source_intake_service import LegalSourceIntakeService
from src.ingestion.criminal_law_merge import (
    build_consolidated_candidate,
    load_amendment_12_patch_manifest,
)
from src.ingestion.statute_source_intake import scan_stage4_source_directory


def _summary(scan) -> dict[str, object]:
    return {
        "candidate_count": len(scan.candidates),
        "candidates": [
            {
                "filename": candidate.source_path.name,
                "version_id": candidate.version_id,
                "source_status": candidate.source_status,
                "document_type": candidate.document_type,
                "effective_from": candidate.effective_from.isoformat(),
                "authority_status": candidate.authority_status,
            }
            for candidate in scan.candidates
        ],
        "skipped_files": [path.name for path in scan.skipped_files],
    }


def _criminal_consolidated_candidate(scan):
    """Build the review-pending 2024 Criminal Law candidate from local originals."""
    candidates = {candidate.version_id: candidate for candidate in scan.candidates}
    base = candidates.get("criminal-law@2020-12-26")
    amendment = candidates.get("criminal-amendment-12@2023-12-29")
    if base is None or amendment is None:
        return None
    return build_consolidated_candidate(base, amendment, load_amendment_12_patch_manifest())


def main() -> None:
    parser = argparse.ArgumentParser(description="登记 Stage 4 本地法规候选来源")
    parser.add_argument("source_dir", type=Path, help="用户下载的法规原件目录")
    parser.add_argument("--dry-run", action="store_true", help="只扫描并输出清单，不写数据库")
    args = parser.parse_args()

    scan = scan_stage4_source_directory(args.source_dir)
    result = _summary(scan)
    criminal_candidate = _criminal_consolidated_candidate(scan)
    if criminal_candidate is not None:
        result["generated_criminal_candidate"] = {
            "version_id": criminal_candidate.version_id,
            "source_status": criminal_candidate.source_status,
            "authority_status": criminal_candidate.authority_status,
            "content_sha256": criminal_candidate.content_sha256,
        }
    if not args.dry_run:
        init_db()
        if db_session.SessionLocal is None:
            raise SystemExit("数据库服务未初始化")
        service = LegalSourceIntakeService(db_session.SessionLocal)
        records = [service.record_candidate(candidate) for candidate in scan.candidates]
        if criminal_candidate is not None:
            records.append(service.record_candidate(criminal_candidate))
        result["records"] = records

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
