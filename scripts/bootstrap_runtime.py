"""Explicit Stage 3 runtime bootstrap: validate or build catalog statute indexes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in raw_args
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("all", help="逐部构建全部可用法规")
    statute = actions.add_parser("statute", help="构建一个指定法规")
    statute.add_argument("slug", help="法规 slug")
    actions.add_parser("validate", help="只验证本地法规快照，不写数据库或 Chroma")
    args = parser.parse_args([argument for argument in raw_args if argument != "--json"])
    args.json = json_output
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    from app.db import session as db_session
    from app.db.session import init_db
    from app.services.deployment_bootstrap_service import DeploymentBootstrapService
    from app.services.knowledge_base_service import KnowledgeBaseService

    if args.action == "validate":
        summary = DeploymentBootstrapService(KnowledgeBaseService(db_session.SessionLocal)).validate()
    else:
        init_db()
        service = DeploymentBootstrapService(KnowledgeBaseService(db_session.SessionLocal))
        summary = service.bootstrap_all() if args.action == "all" else service.bootstrap_statute(args.slug)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        for result in summary["laws"]:
            suffix = result.get("error_code") or result.get("bootstrap_action", "")
            print(f"{result['slug']}: {result['status']}{f' ({suffix})' if suffix else ''}")
    laws_ready = all(item["status"] in {"READY", "AVAILABLE"} for item in summary["laws"])
    return 0 if laws_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
