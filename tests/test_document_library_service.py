"""文档知识库服务测试。"""

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import app.models.knowledge_base  # noqa: F401
from app.db.base import Base
from app.services.knowledge_base_service import KnowledgeBaseService


def build_service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return KnowledgeBaseService(sessionmaker(bind=engine, expire_on_commit=False))


def test_create_document_library_uses_its_own_collection():
    """自定义文档库应与法规库相同地拥有独立 collection，但标明 document 类型。"""
    service = build_service()

    library = service.create_document_library(
        name="劳动仲裁材料",
        slug="labor-arbitration-materials",
        law_area="labor",
    )

    assert library["type"] == "document"
    assert library["collection_name"] == "kb_labor_arbitration_materials"
    assert library["status"] == "EMPTY"
    assert library["document_count"] == 0
