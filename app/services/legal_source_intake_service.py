"""持久化 Stage 4 的本地法规版本候选。"""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.legal_source_import import LegalSourceImport
from src.ingestion.statute_source_intake import Stage4SourceCandidate


class LegalSourceIntakeService:
    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def record_candidate(self, candidate: Stage4SourceCandidate) -> dict[str, Any]:
        """Save one extracted original idempotently without granting query eligibility."""
        with self._session_factory() as session:
            item = session.scalar(
                select(LegalSourceImport).where(
                    LegalSourceImport.version_id == candidate.version_id,
                    LegalSourceImport.raw_sha256 == candidate.raw_sha256,
                )
            )
            if item is None:
                item = LegalSourceImport(
                    law_slug=candidate.law_slug,
                    law_name=candidate.law_name,
                    version_id=candidate.version_id,
                    source_path=str(candidate.source_path),
                    raw_sha256=candidate.raw_sha256,
                    content_sha256=candidate.content_sha256,
                    content=candidate.content,
                    promulgated_on=candidate.promulgated_on,
                    effective_from=candidate.effective_from,
                    source_status=candidate.source_status,
                    document_type=candidate.document_type,
                    authority_status=candidate.authority_status,
                    parser_version=candidate.parser_version,
                )
                session.add(item)
                session.commit()
                session.refresh(item)
            return self._serialize(item)

    def list_candidates(self) -> list[dict[str, Any]]:
        """Return provenance cards only; legal-body text remains outside admin listings."""
        with self._session_factory() as session:
            items = session.scalars(
                select(LegalSourceImport).order_by(
                    LegalSourceImport.law_slug,
                    LegalSourceImport.effective_from,
                    LegalSourceImport.id,
                )
            ).all()
            return [self._serialize(item) for item in items]

    def verify_candidate(
        self, candidate_id: int, *, authority_url: str, reviewer_user_id: int
    ) -> dict[str, Any]:
        """人工核验后记录官方出处；未提供 http(s) URL 时拒绝启用。"""
        parsed = urlparse(authority_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("权威来源必须是完整的 http(s) URL")
        with self._session_factory() as session:
            item = session.get(LegalSourceImport, candidate_id)
            if item is None:
                raise ValueError("候选来源不存在")
            item.authority_status = "VERIFIED"
            item.authority_url = authority_url
            item.verified_by_user_id = reviewer_user_id
            item.verified_at = datetime.now()
            session.commit()
            session.refresh(item)
            return self._serialize(item)

    @staticmethod
    def _serialize(item: LegalSourceImport) -> dict[str, Any]:
        return {
            "id": item.id,
            "law_slug": item.law_slug,
            "law_name": item.law_name,
            "version_id": item.version_id,
            "source_status": item.source_status,
            "document_type": item.document_type,
            "authority_status": item.authority_status,
            "authority_url": item.authority_url,
            "verified_at": item.verified_at.isoformat() if item.verified_at else None,
            "effective_from": item.effective_from.isoformat(),
            "raw_sha256": item.raw_sha256,
            "content_sha256": item.content_sha256,
        }
