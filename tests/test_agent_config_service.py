"""Agent 配置只能保存白名单参数，并以组织为边界。"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.models.organization import Organization


def test_agent_config_accepts_only_safe_whitelist_and_is_organization_scoped():
    from app.services.agent_config_service import AgentConfigService

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all([Organization(id=1, name="甲", slug="a"), Organization(id=2, name="乙", slug="b")])
        db.commit()

    service = AgentConfigService(factory)
    saved = service.upsert(organization_id=1, values={"top_k": 8, "case_search_enabled": False})
    assert saved["top_k"] == 8
    assert service.get(organization_id=2) == service.defaults()
    with pytest.raises(ValueError, match="不允许"):
        service.upsert(organization_id=1, values={"python_code": "import os"})
    with pytest.raises(ValueError, match="top_k"):
        service.upsert(organization_id=1, values={"top_k": 999})
