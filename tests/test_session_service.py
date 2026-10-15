"""v2.4 会话服务：用户隔离、受控记忆与画像更新。"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.models.user import User

try:
    from app.models.session import ConversationSession
    from app.models.user_profile import UserProfile
    from app.services.session_service import SessionNotFoundError, SessionService
except ImportError:
    ConversationSession = None
    UserProfile = None
    SessionNotFoundError = None
    SessionService = None


def make_service():
    assert SessionService is not None, "v2.4 应提供独立的 SessionService"
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add_all(
            [
                User(id=1, username="alice", hashed_password="hash"),
                User(id=2, username="bob", hashed_password="hash"),
            ]
        )
        db.commit()
    return SessionService(factory), factory


def test_session_service_creates_user_owned_session_with_question_title():
    service, _ = make_service()

    session = service.create(user_id=1, initial_question="劳动合同解除后经济补偿如何计算？")

    assert session["user_id"] == 1
    assert session["is_active"] is True
    assert len(session["id"]) == 36
    assert session["title"] == "劳动合同解除后经济补偿如何计算？"


def test_sessions_are_searchable_and_inaccessible_to_other_user():
    service, _ = make_service()
    matched = service.create(user_id=1, initial_question="劳动合同解除补偿")
    service.create(user_id=1, initial_question="公司股权转让")
    service.create(user_id=2, initial_question="劳动争议仲裁")

    assert [item["id"] for item in service.list_for_user(user_id=1, query="劳动")] == [
        matched["id"]
    ]
    with pytest.raises(SessionNotFoundError):
        service.get_for_user(user_id=2, session_id=matched["id"])


def test_memory_keeps_only_latest_five_turns_and_verified_citations():
    service, _ = make_service()
    session = service.create(user_id=1, initial_question="第 1 轮")
    for index in range(1, 7):
        service.record_turn(
            user_id=1,
            session_id=session["id"],
            question=f"第 {index} 轮问题",
            answer=f"第 {index} 轮回答",
            intent="factual",
            citations=[
                {"article_id": f"中华人民共和国民法典第{index}条", "is_verified": index % 2 == 0},
            ],
            verification_status="pass",
            metadata={},
            knowledge_base_slug="civil-code",
        )

    memory = service.load_memory(user_id=1, session_id=session["id"])

    assert [turn.question for turn in memory] == [f"第 {index} 轮问题" for index in range(2, 7)]
    assert memory[0].verified_citations == ["中华人民共和国民法典第2条"]
    assert memory[1].verified_citations == []


def test_archived_session_rejects_new_turn_and_verified_turn_updates_profile():
    service, factory = make_service()
    session = service.create(user_id=1, initial_question="格式条款")
    service.record_turn(
        user_id=1,
        session_id=session["id"],
        question="格式条款是否有效？",
        answer="依据法条判断。",
        intent="factual",
        citations=[{"article_id": "中华人民共和国民法典第496条", "is_verified": True}],
        verification_status="pass",
        metadata={},
        knowledge_base_slug="civil-code",
    )
    assert service.archive(user_id=1, session_id=session["id"]) is True

    with pytest.raises(SessionNotFoundError):
        service.record_turn(
            user_id=1,
            session_id=session["id"],
            question="还能继续吗？",
            answer="不应写入。",
            intent="factual",
            citations=[],
            verification_status="pass",
            metadata={},
            knowledge_base_slug="civil-code",
        )

    with factory() as db:
        profile = db.get(UserProfile, 1)
        assert profile.law_area_counts == {"civil-code": 1}
        assert profile.intent_counts == {"factual": 1}
