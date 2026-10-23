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
from app.services.knowledge_base_service import (
    KnowledgeBaseAlreadyExistsError,
    KnowledgeBaseService,
)
from src.ingestion.statute_catalog import statute_by_slug

CIVIL_CODE_STATUTE = statute_by_slug("civil-code")
SOURCE_FILE = PROJECT_ROOT / CIVIL_CODE_STATUTE.clean_text_path


def main() -> None:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(f"未找到民法典源文件: {SOURCE_FILE}")

    init_db()
    service = KnowledgeBaseService(db_session.SessionLocal)
    try:
        service.create_knowledge_base(
            name=CIVIL_CODE_STATUTE.definition.name,
            slug=CIVIL_CODE_STATUTE.definition.slug,
            law_area=CIVIL_CODE_STATUTE.definition.law_area,
        )
    except KnowledgeBaseAlreadyExistsError:
        pass

    result = service.rebuild_knowledge_base(
        CIVIL_CODE_STATUTE.definition.slug,
        content=SOURCE_FILE.read_text(encoding="utf-8"),
    )
    print(
        f"完成：{result['name']}，法条 {result['document_count']} 条，"
        f"chunk {result['chunk_count']} 个，状态 {result['status']}"
    )


if __name__ == "__main__":
    main()
