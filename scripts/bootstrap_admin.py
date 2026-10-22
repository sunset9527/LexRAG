"""Create the initial production administrator from environment variables.

Required variables:
  LEXRAG_BOOTSTRAP_USERNAME
  LEXRAG_BOOTSTRAP_PASSWORD
  LEXRAG_BOOTSTRAP_ORGANIZATION_NAME
  LEXRAG_BOOTSTRAP_ORGANIZATION_SLUG

The password is intentionally not accepted as a command-line argument.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import session as db_session
from app.db.session import init_db
from app.services.bootstrap_service import bootstrap_administrator
from config import settings, validate_security_settings


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"缺少环境变量: {name}")
    return value


def main() -> None:
    validate_security_settings(settings)
    init_db()
    if db_session.SessionLocal is None:
        raise SystemExit("数据库服务未初始化")
    result = bootstrap_administrator(
        db_session.SessionLocal,
        username=_required("LEXRAG_BOOTSTRAP_USERNAME"),
        password=_required("LEXRAG_BOOTSTRAP_PASSWORD"),
        email=os.environ.get("LEXRAG_BOOTSTRAP_EMAIL") or None,
        organization_name=_required("LEXRAG_BOOTSTRAP_ORGANIZATION_NAME"),
        organization_slug=_required("LEXRAG_BOOTSTRAP_ORGANIZATION_SLUG"),
    )
    print(
        "管理员初始化完成: "
        f"user_id={result['user_id']} organization_id={result['organization_id']}"
    )


if __name__ == "__main__":
    main()
