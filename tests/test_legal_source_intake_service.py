from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.legal_source_import import LegalSourceImport
from app.services.legal_source_intake_service import LegalSourceIntakeService
from src.ingestion.statute_source_intake import (
    SOURCE_STATUS_PUBLISHED_NOT_EFFECTIVE,
    Stage4SourceCandidate,
)


def _candidate() -> Stage4SourceCandidate:
    return Stage4SourceCandidate(
        source_path=Path("E:/source/中华人民共和国商标法_20260626.docx"),
        law_slug="trademark-law",
        law_name="中华人民共和国商标法",
        version_id="trademark-law@2026-06-26",
        promulgated_on=date(2026, 6, 26),
        effective_from=date(2027, 1, 1),
        source_status=SOURCE_STATUS_PUBLISHED_NOT_EFFECTIVE,
        raw_sha256="a" * 64,
        content_sha256="b" * 64,
        content="中华人民共和国商标法\n第一条",
    )


def test_record_candidate_is_idempotent_and_keeps_it_pending_authority_review():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = LegalSourceIntakeService(factory)

    first = service.record_candidate(_candidate())
    second = service.record_candidate(_candidate())

    assert first["id"] == second["id"]
    assert first["source_status"] == "PUBLISHED_NOT_EFFECTIVE"
    assert first["authority_status"] == "PENDING_REVIEW"
    assert first["authority_url"] is None
    assert first["document_type"] == "STATUTE"
    with factory() as db:
        assert db.query(LegalSourceImport).count() == 1


def test_list_candidates_exposes_provenance_status_without_returning_full_legal_text():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = LegalSourceIntakeService(factory)
    service.record_candidate(_candidate())

    items = service.list_candidates()

    assert items == [
        {
            "id": 1,
            "law_slug": "trademark-law",
            "law_name": "中华人民共和国商标法",
            "version_id": "trademark-law@2026-06-26",
            "source_status": "PUBLISHED_NOT_EFFECTIVE",
            "document_type": "STATUTE",
            "authority_status": "PENDING_REVIEW",
            "authority_url": None,
            "verified_at": None,
            "effective_from": "2027-01-01",
            "raw_sha256": "a" * 64,
            "content_sha256": "b" * 64,
        }
    ]


def test_verify_candidate_requires_an_official_url_and_records_review_provenance():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = LegalSourceIntakeService(factory)
    candidate = service.record_candidate(_candidate())

    verified = service.verify_candidate(
        candidate["id"],
        authority_url="https://www.cnipa.gov.cn/example",
        reviewer_user_id=7,
    )

    assert verified["authority_status"] == "VERIFIED"
    assert verified["authority_url"] == "https://www.cnipa.gov.cn/example"
    assert verified["verified_at"] is not None
