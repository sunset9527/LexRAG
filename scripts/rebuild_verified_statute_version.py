"""Build one verified, effective statute version into an isolated collection."""

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import session as db_session
from app.db.session import init_db
from app.models.legal_source_import import LegalSourceImport
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.statute_version_chain_service import StatuteVersionChainService


def main() -> None:
    parser = argparse.ArgumentParser(description="重建一部已核验法规的隔离版本索引")
    parser.add_argument("law_slug", help="法规 slug，例如 company-law")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--without-activation",
        action="store_true",
        help="只构建指定历史版本的隔离 collection，不切换当前知识库指针",
    )
    args = parser.parse_args()

    init_db()
    if db_session.SessionLocal is None:
        raise SystemExit("数据库服务未初始化")
    chains = StatuteVersionChainService(db_session.SessionLocal)
    try:
        chain = chains.get_indexable_chain_for_law(args.law_slug, as_of=args.as_of)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    provenance = chains.get_index_provenance(chain["id"], as_of=args.as_of)
    with db_session.SessionLocal() as session:
        source = session.get(LegalSourceImport, chain["consolidated_source_import_id"])
        if source is None:
            raise SystemExit("版本链的合并全文来源不存在")
        content = source.content
        content_hash = source.content_sha256

    result = KnowledgeBaseService(db_session.SessionLocal).rebuild_confirmed_law_version(
        args.law_slug,
        organization_id=None,
        content=content,
        version_hash=content_hash,
        provenance_metadata=provenance,
        activate=not args.without_activation,
    )
    print(
        {
            "law_slug": args.law_slug,
            "collection_name": result["collection_name"],
            "document_count": result["document_count"],
            "chunk_count": result["chunk_count"],
        }
    )


if __name__ == "__main__":
    main()
