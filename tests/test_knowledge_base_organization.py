"""组织不能通过猜测知识库 slug 访问他人私有 collection。"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.models.knowledge_base import KnowledgeBase
from app.models.organization import Organization
from app.services.knowledge_base_service import KnowledgeBaseNotFoundError, KnowledgeBaseService


def test_ready_collection_is_visible_only_to_owner_organization_or_system_share():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all([Organization(id=1, name="甲", slug="a"), Organization(id=2, name="乙", slug="b")])
        db.add_all(
            [
                KnowledgeBase(
                    name="甲私有库", slug="a-private", type="document", law_area="civil",
                    collection_name="kb_a_private", status="READY", document_count=1, chunk_count=1,
                    organization_id=1, is_system_shared=False,
                ),
                KnowledgeBase(
                    name="共享法规", slug="shared-law", type="statute", law_area="civil",
                    collection_name="kb_shared_law", status="READY", document_count=1, chunk_count=1,
                    organization_id=None, is_system_shared=True,
                ),
            ]
        )
        db.commit()
    service = KnowledgeBaseService(factory)

    assert service.get_ready_collection_name_for_organization("a-private", organization_id=1) == "kb_a_private"
    assert service.get_ready_collection_name_for_organization("shared-law", organization_id=2) == "kb_shared_law"
    with pytest.raises(KnowledgeBaseNotFoundError):
        service.get_ready_collection_name_for_organization("a-private", organization_id=2)


def test_new_library_is_owned_by_the_creating_organization():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(Organization(id=7, name="甲", slug="a"))
        db.commit()

    item = KnowledgeBaseService(factory).create_document_library(
        name="甲的合同", slug="a-contracts", law_area="contract", organization_id=7
    )

    assert item["organization_id"] == 7
    assert item["is_system_shared"] is False
