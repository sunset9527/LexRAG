"""将清洗后的民法典重建到 v1.9 专属知识库。"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from app.db import session as db_session
from app.db.session import init_db
from app.services.deployment_bootstrap_service import DeploymentBootstrapService
from app.services.knowledge_base_service import KnowledgeBaseService
from src.ingestion.statute_catalog import statute_by_slug

CIVIL_CODE_STATUTE = statute_by_slug("civil-code")
SOURCE_FILE = PROJECT_ROOT / CIVIL_CODE_STATUTE.clean_text_path


def main() -> None:
    init_db()
    summary = DeploymentBootstrapService(
        KnowledgeBaseService(db_session.SessionLocal)
    ).bootstrap_statute(CIVIL_CODE_STATUTE.definition.slug)
    result = summary["laws"][0]
    if result["status"] != "READY":
        raise RuntimeError(f"民法典 bootstrap 未就绪: {result.get('error_code', result['status'])}")
    print(f"完成：{CIVIL_CODE_STATUTE.definition.name}，collection {result['collection_name']}")


if __name__ == "__main__":
    main()
