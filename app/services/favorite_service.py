"""用户收藏的持久化服务。"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Optional

from app.models.favorite import Favorite


class FavoriteService:
    """集中处理收藏的创建、读取、删除与用户隔离。"""

    def __init__(self, session_factory: Callable[[], Any]):
        self._session_factory = session_factory

    @staticmethod
    def _fingerprint(
        question: str,
        answer: str,
        citations: list[dict[str, Any]],
        knowledge_base_slug: Optional[str],
    ) -> str:
        material = json.dumps(
            {
                "question": question,
                "answer": answer,
                "citations": citations,
                "knowledge_base_slug": knowledge_base_slug,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _to_dict(favorite: Favorite) -> dict[str, Any]:
        return {
            "id": favorite.id,
            "question": favorite.question,
            "answer": favorite.answer,
            "citations": favorite.citations or [],
            "knowledge_base_slug": favorite.knowledge_base_slug,
            "law_area": favorite.law_area,
            "created_at": favorite.created_at.isoformat() if favorite.created_at else None,
        }

    def create(
        self,
        *,
        user_id: int,
        question: str,
        answer: str,
        citations: list[dict[str, Any]],
        knowledge_base_slug: Optional[str],
        law_area: Optional[str],
    ) -> dict[str, Any]:
        fingerprint = self._fingerprint(question, answer, citations, knowledge_base_slug)
        with self._session_factory() as db:
            existing = (
                db.query(Favorite)
                .filter(Favorite.user_id == user_id, Favorite.answer_fingerprint == fingerprint)
                .first()
            )
            if existing:
                return self._to_dict(existing)
            favorite = Favorite(
                user_id=user_id,
                answer_fingerprint=fingerprint,
                question=question,
                answer=answer,
                citations=citations,
                knowledge_base_slug=knowledge_base_slug,
                law_area=law_area,
            )
            db.add(favorite)
            db.commit()
            db.refresh(favorite)
            return self._to_dict(favorite)

    def list_for_user(
        self,
        *,
        user_id: int,
        law_area: Optional[str] = None,
        knowledge_base_slug: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        with self._session_factory() as db:
            query = db.query(Favorite).filter(Favorite.user_id == user_id)
            if law_area:
                query = query.filter(Favorite.law_area == law_area)
            if knowledge_base_slug:
                query = query.filter(Favorite.knowledge_base_slug == knowledge_base_slug)
            return [self._to_dict(item) for item in query.order_by(Favorite.id.desc()).all()]

    def delete(self, *, user_id: int, favorite_id: int) -> bool:
        with self._session_factory() as db:
            favorite = db.query(Favorite).filter(Favorite.id == favorite_id, Favorite.user_id == user_id).first()
            if favorite is None:
                return False
            db.delete(favorite)
            db.commit()
            return True
