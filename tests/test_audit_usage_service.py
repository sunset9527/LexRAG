"""v3.0 审计与日统计：不复制敏感原文，重复投递不重复计数。"""

import sys
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.models.organization import Organization  # noqa: F401
from app.models.user import User  # noqa: F401

try:
    from app.models.audit_log import AuditLog
    from app.models.usage_daily import UsageDaily
    from app.services.audit_service import AuditService
    from app.services.usage_service import UsageService
except ImportError:
    AuditLog = UsageDaily = AuditService = UsageService = None


def make_services():
    assert AuditService is not None and UsageService is not None, "v3.0 应提供审计和统计服务"
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return AuditService(factory), UsageService(factory), factory


def test_query_audit_keeps_hashes_but_never_persists_question_answer_or_credentials():
    audit, _usage, factory = make_services()

    created = audit.append_query(
        event_id="evt-1",
        organization_id=7,
        actor_user_id=9,
        request_id="req-1",
        question="我的身份证号是 123456789012345678",
        answer="请不要泄露这段回答",
        verification_status="pass",
        metadata={"api_key": "sk-secret", "jwt": "token", "cache_hit": "exact"},
    )

    assert created is True
    with factory() as db:
        row = db.query(AuditLog).one()
        assert row.metadata_["question_sha256"]
        assert row.metadata_["answer_sha256"]
        assert row.metadata_["question_length"] > 0
        assert row.metadata_["answer_length"] > 0
        assert row.metadata_["cache_hit"] == "exact"
        assert "123456789012345678" not in str(row.metadata_)
        assert "sk-secret" not in str(row.metadata_)
        assert "token" not in str(row.metadata_)


def test_duplicate_query_event_is_audit_and_usage_idempotent():
    audit, usage, factory = make_services()
    kwargs = {
        "event_id": "evt-2",
        "organization_id": 7,
        "actor_user_id": 9,
        "request_id": "req-2",
        "question": "劳动合同是否有效？",
        "answer": "请参考法条。",
        "verification_status": "pass",
        "metadata": {"cache_hit": "none", "law_area": "劳动"},
    }

    assert audit.append_query(**kwargs) is True
    assert (
        usage.record_query(
            event_id="evt-2",
            organization_id=7,
            actor_user_id=9,
            latency_ms=120,
            estimated_tokens=88,
        )
        is True
    )
    assert audit.append_query(**kwargs) is False
    assert (
        usage.record_query(
            event_id="evt-2",
            organization_id=7,
            actor_user_id=9,
            latency_ms=120,
            estimated_tokens=88,
        )
        is False
    )

    with factory() as db:
        assert db.query(AuditLog).count() == 1
        daily = db.query(UsageDaily).one()
        assert daily.stat_date == date.today()
        assert daily.query_count == 1
        assert daily.success_count == 1
        assert daily.total_latency_ms == 120
        assert daily.estimated_token_count == 88
