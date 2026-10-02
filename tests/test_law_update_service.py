"""法规更新：同一快照幂等，变更必须经确认。"""
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from app.db.base import Base
from app.models.organization import Organization

try:
    from app.models.law_update import LawSubscription, LawUpdateEvent, LawVersion
    from app.services.law_update_service import LawUpdateService
except ImportError:
    LawSubscription = LawUpdateEvent = LawVersion = LawUpdateService = None


def test_change_requires_admin_confirmation_and_identical_snapshot_is_idempotent():
    assert LawUpdateService is not None
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(Organization(id=1, name="演示", slug="demo")); db.commit()
    service = LawUpdateService(factory)
    subscription = service.subscribe(organization_id=1, law_name="中华人民共和国民法典", source_url="https://flk.npc.gov.cn/")
    assert service.observe(subscription_id=subscription["id"], organization_id=1, content="第一版") is None
    event = service.observe(subscription_id=subscription["id"], organization_id=1, content="第二版")
    assert event["status"] == "PENDING_REVIEW"
    assert service.observe(subscription_id=subscription["id"], organization_id=1, content="第二版") is None
    assert service.confirm(event_id=event["id"], organization_id=1, reviewer_user_id=7)["status"] == "CONFIRMED"
    with factory() as db:
        assert db.query(LawSubscription).one().last_content_hash
        assert db.query(LawUpdateEvent).one().status == "CONFIRMED"
        assert db.query(LawVersion).one().content_hash == event["current_hash"]
