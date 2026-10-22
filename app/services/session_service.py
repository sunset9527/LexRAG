"""会话持久化、受控记忆与用户画像服务。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import or_

from app.models.chat_history import ChatHistory
from app.models.knowledge_base import KnowledgeBase
from app.models.session import ConversationSession
from app.models.user_profile import UserProfile


class SessionNotFoundError(ValueError):
    """会话不存在、不属于当前用户或已经归档。"""


@dataclass(frozen=True)
class ConversationTurn:
    """传入回答生成器前经过最小化处理的一轮历史。"""

    question: str
    answer: str
    verified_citations: list[str]


class SessionService:
    """集中处理会话所有权、历史边界和画像更新。"""

    def __init__(self, session_factory: Callable[[], Any]):
        self._session_factory = session_factory

    @staticmethod
    def _title(question: str | None) -> str:
        normalized = " ".join((question or "").split())
        return normalized[:120] or "新法律咨询"

    @staticmethod
    def _to_dict(session: ConversationSession) -> dict[str, Any]:
        return {
            "id": session.id,
            "user_id": session.user_id,
            "title": session.title,
            "is_active": session.is_active,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        }

    @staticmethod
    def _verified_citations(citations: Any) -> list[str]:
        if not isinstance(citations, list):
            return []
        return [
            str(citation["article_id"])
            for citation in citations
            if isinstance(citation, dict)
            and citation.get("is_verified") is True
            and citation.get("article_id")
        ]

    @staticmethod
    def _active_session(
        db: Any, *, user_id: int, session_id: str, organization_id: int | None = None
    ) -> ConversationSession:
        query = db.query(ConversationSession).filter(
            ConversationSession.id == session_id,
            ConversationSession.user_id == user_id,
            ConversationSession.is_active.is_(True),
        )
        if organization_id is not None:
            query = query.filter(ConversationSession.organization_id == organization_id)
        session = query.first()
        if session is None:
            raise SessionNotFoundError("会话不存在或不可用")
        return session

    def create(
        self,
        *,
        user_id: int,
        initial_question: str | None = None,
        organization_id: int | None = None,
    ) -> dict[str, Any]:
        with self._session_factory() as db:
            session = ConversationSession(
                id=str(uuid4()),
                user_id=user_id,
                organization_id=organization_id,
                title=self._title(initial_question),
            )
            db.add(session)
            db.commit()
            db.refresh(session)
            return self._to_dict(session)

    def list_for_user(
        self, *, user_id: int, query: str | None = None, organization_id: int | None = None
    ) -> list[dict[str, Any]]:
        with self._session_factory() as db:
            statement = db.query(ConversationSession).filter(
                ConversationSession.user_id == user_id,
                ConversationSession.is_active.is_(True),
            )
            if organization_id is not None:
                statement = statement.filter(ConversationSession.organization_id == organization_id)
            if query and query.strip():
                statement = statement.filter(ConversationSession.title.contains(query.strip()))
            sessions = statement.order_by(ConversationSession.updated_at.desc()).all()
            return [self._to_dict(item) for item in sessions]

    def get_for_user(
        self, *, user_id: int, session_id: str, organization_id: int | None = None
    ) -> dict[str, Any]:
        with self._session_factory() as db:
            session = self._active_session(
                db, user_id=user_id, session_id=session_id, organization_id=organization_id
            )
            payload = self._to_dict(session)
            history = (
                db.query(ChatHistory)
                .filter(ChatHistory.user_id == user_id, ChatHistory.session_id == session_id)
                .order_by(ChatHistory.created_at.asc(), ChatHistory.id.asc())
                .all()
            )
            payload["messages"] = [
                {
                    "id": item.id,
                    "question": item.question,
                    "answer": item.answer,
                    "intent": item.intent,
                    "citations": item.citations or [],
                    "verification_status": item.verification_status,
                    "metadata": item.metadata_ or {},
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in history
            ]
            return payload

    def rename(
        self, *, user_id: int, session_id: str, title: str, organization_id: int | None = None
    ) -> dict[str, Any]:
        with self._session_factory() as db:
            session = self._active_session(
                db, user_id=user_id, session_id=session_id, organization_id=organization_id
            )
            session.title = self._title(title)
            session.updated_at = datetime.now()
            db.commit()
            db.refresh(session)
            return self._to_dict(session)

    def archive(self, *, user_id: int, session_id: str, organization_id: int | None = None) -> bool:
        with self._session_factory() as db:
            session = self._active_session(
                db, user_id=user_id, session_id=session_id, organization_id=organization_id
            )
            session.is_active = False
            session.updated_at = datetime.now()
            db.commit()
            return True

    def load_memory(
        self, *, user_id: int, session_id: str, limit: int = 5, organization_id: int | None = None
    ) -> list[ConversationTurn]:
        with self._session_factory() as db:
            self._active_session(
                db, user_id=user_id, session_id=session_id, organization_id=organization_id
            )
            rows = (
                db.query(ChatHistory)
                .filter(ChatHistory.user_id == user_id, ChatHistory.session_id == session_id)
                .order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())
                .limit(limit)
                .all()
            )
            return [
                ConversationTurn(
                    question=row.question,
                    answer=row.answer,
                    verified_citations=self._verified_citations(row.citations),
                )
                for row in reversed(rows)
            ]

    def record_turn(
        self,
        *,
        user_id: int,
        session_id: str,
        question: str,
        answer: str,
        intent: str | None,
        citations: list[dict[str, Any]],
        verification_status: str | None,
        metadata: dict[str, Any],
        knowledge_base_slug: str | None,
        organization_id: int | None = None,
    ) -> None:
        with self._session_factory() as db:
            session = self._active_session(
                db, user_id=user_id, session_id=session_id, organization_id=organization_id
            )
            db.add(
                ChatHistory(
                    user_id=user_id,
                    organization_id=organization_id,
                    session_id=session_id,
                    question=question,
                    answer=answer,
                    intent=intent,
                    citations=citations,
                    verification_status=verification_status,
                    metadata_=metadata,
                )
            )
            session.updated_at = datetime.now()
            if verification_status == "pass":
                profile = db.get(UserProfile, user_id)
                if profile is None:
                    profile = UserProfile(user_id=user_id, law_area_counts={}, intent_counts={})
                    db.add(profile)
                if knowledge_base_slug:
                    law_areas = dict(profile.law_area_counts or {})
                    law_areas[knowledge_base_slug] = law_areas.get(knowledge_base_slug, 0) + 1
                    profile.law_area_counts = law_areas
                if intent:
                    intents = dict(profile.intent_counts or {})
                    intents[intent] = intents.get(intent, 0) + 1
                    profile.intent_counts = intents
            db.commit()

    def get_recommendations(self, *, user_id: int, organization_id: int) -> dict[str, Any]:
        """基于已校验问答计数返回可解释的静态入口，不做法律判断。"""
        common_questions = {
            "civil-code": ["合同成立需要满足哪些条件？", "格式条款什么情况下无效？"],
            "labor-law": ["劳动合同解除的经济补偿如何计算？", "用人单位何时可以解除劳动合同？"],
            "company-law": ["公司股东的出资义务有哪些？", "股权转让需要注意什么？"],
        }
        with self._session_factory() as db:
            profile = db.get(UserProfile, user_id)
            counts = dict(profile.law_area_counts or {}) if profile else {}
            ready_slugs = {
                item.slug
                for item in db.query(KnowledgeBase)
                .filter(
                    KnowledgeBase.status == "READY",
                    or_(
                        KnowledgeBase.organization_id == organization_id,
                        KnowledgeBase.is_system_shared.is_(True),
                    ),
                )
                .all()
            }
            ranked = sorted(
                (slug for slug in counts if slug in ready_slugs),
                key=lambda slug: (-counts[slug], slug),
            )
            based_on = ranked[0] if ranked else "civil-code"
            return {
                "based_on_law_area": based_on,
                "items": [
                    {
                        "type": "law_browser",
                        "label": "浏览相关法规",
                        "path": f"/laws?knowledge_base={based_on}",
                    },
                    {
                        "type": "case_search",
                        "label": "检索相关案例",
                        "path": f"/cases?knowledge_base={based_on}",
                    },
                    {
                        "type": "common_questions",
                        "label": "常见问题",
                        "questions": common_questions.get(based_on, common_questions["civil-code"]),
                    },
                ],
            }
