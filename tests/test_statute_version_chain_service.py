from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.services.legal_source_intake_service import LegalSourceIntakeService
from app.services.statute_version_chain_service import StatuteVersionChainService
from src.ingestion.statute_source_intake import (
    SOURCE_STATUS_CURRENT,
    SOURCE_STATUS_HISTORICAL,
    SOURCE_STATUS_SUPPLEMENTAL_AMENDMENT,
    Stage4SourceCandidate,
)


def _candidate(
    *,
    version_id: str,
    document_type: str,
    source_status: str,
    effective_from: date,
) -> Stage4SourceCandidate:
    return Stage4SourceCandidate(
        source_path=Path(f"E:/sources/{version_id}.docx"),
        law_slug="criminal-law",
        law_name="中华人民共和国刑法",
        version_id=version_id,
        promulgated_on=effective_from,
        effective_from=effective_from,
        source_status=source_status,
        raw_sha256=(version_id.encode().hex() + "0" * 64)[:64],
        content_sha256=("c" + version_id.encode().hex() + "0" * 64)[:64],
        content="中华人民共和国刑法\n第一条 测试正文",
        document_type=document_type,
    )


def test_criminal_amendment_chain_is_not_indexable_without_reviewed_consolidated_text():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sources = LegalSourceIntakeService(factory)
    base = sources.record_candidate(
        _candidate(
            version_id="criminal-law@2020-12-26",
            document_type="STATUTE",
            source_status=SOURCE_STATUS_HISTORICAL,
            effective_from=date(2021, 3, 1),
        )
    )
    amendment = sources.record_candidate(
        _candidate(
            version_id="criminal-amendment-12@2023-12-29",
            document_type="AMENDMENT",
            source_status=SOURCE_STATUS_SUPPLEMENTAL_AMENDMENT,
            effective_from=date(2024, 3, 1),
        )
    )
    for item in (base, amendment):
        sources.verify_candidate(
            item["id"], authority_url="https://www.npc.gov.cn/example", reviewer_user_id=1
        )
    consolidated = sources.record_candidate(
        _candidate(
            version_id="criminal-law@2024-03-01",
            document_type="STATUTE",
            source_status=SOURCE_STATUS_CURRENT,
            effective_from=date(2024, 3, 1),
        )
    )
    sources.verify_candidate(
        consolidated["id"], authority_url="https://www.npc.gov.cn/example", reviewer_user_id=1
    )

    chain = StatuteVersionChainService(factory).create_chain(
        law_slug="criminal-law",
        target_version_id="criminal-law@2024-03-01",
        effective_from=date(2024, 3, 1),
        members=[
            {"source_import_id": base["id"], "role": "BASE_TEXT"},
            {"source_import_id": amendment["id"], "role": "AMENDMENT"},
        ],
    )

    assert chain["is_indexable"] is False
    assert chain["index_block_reason"] == "CONSOLIDATED_TEXT_REQUIRED"

    completed = StatuteVersionChainService(factory).attach_consolidated_source(
        chain["id"], source_import_id=consolidated["id"]
    )

    assert completed["is_indexable"] is True
    assert completed["consolidated_source_import_id"] == consolidated["id"]
    assert completed["members"][-1]["role"] == "CONSOLIDATED_TEXT"


def test_verified_complete_chain_exports_provenance_only_when_effective():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sources = LegalSourceIntakeService(factory)
    source = sources.record_candidate(
        _candidate(
            version_id="criminal-law@2024-03-01-consolidated",
            document_type="STATUTE",
            source_status=SOURCE_STATUS_CURRENT,
            effective_from=date(2024, 3, 1),
        )
    )
    sources.verify_candidate(
        source["id"], authority_url="https://www.npc.gov.cn/example", reviewer_user_id=1
    )
    chains = StatuteVersionChainService(factory)
    chain = chains.create_chain(
        law_slug="criminal-law",
        target_version_id="criminal-law@2024-03-01",
        effective_from=date(2024, 3, 1),
        consolidated_source_import_id=source["id"],
        members=[{"source_import_id": source["id"], "role": "CONSOLIDATED_TEXT"}],
    )

    metadata = chains.get_index_provenance(chain["id"], as_of=date(2025, 1, 1))

    assert metadata == {
        "version_id": "criminal-law@2024-03-01",
        "effective_from": "2024-03-01",
        "effective_to": "",
        "source_url": "https://www.npc.gov.cn/example",
        "content_hash": source["content_sha256"],
    }


def test_selects_the_effective_chain_when_one_law_has_history_and_current_versions():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sources = LegalSourceIntakeService(factory)
    historic = sources.record_candidate(
        _candidate(
            version_id="criminal-law@2020-12-26",
            document_type="STATUTE",
            source_status=SOURCE_STATUS_HISTORICAL,
            effective_from=date(2021, 3, 1),
        )
    )
    current = sources.record_candidate(
        _candidate(
            version_id="criminal-law@2024-03-01",
            document_type="STATUTE",
            source_status=SOURCE_STATUS_CURRENT,
            effective_from=date(2024, 3, 1),
        )
    )
    for item in (historic, current):
        sources.verify_candidate(
            item["id"], authority_url="https://flk.npc.gov.cn/example", reviewer_user_id=1
        )
    chains = StatuteVersionChainService(factory)
    chains.create_chain(
        law_slug="criminal-law",
        target_version_id=historic["version_id"],
        effective_from=date(2021, 3, 1),
        effective_to=date(2024, 2, 29),
        consolidated_source_import_id=historic["id"],
        members=[{"source_import_id": historic["id"], "role": "CONSOLIDATED_TEXT"}],
    )
    chains.create_chain(
        law_slug="criminal-law",
        target_version_id=current["version_id"],
        effective_from=date(2024, 3, 1),
        consolidated_source_import_id=current["id"],
        members=[{"source_import_id": current["id"], "role": "CONSOLIDATED_TEXT"}],
    )

    chain = chains.get_indexable_chain_for_law("criminal-law", as_of=date(2026, 10, 24))

    assert chain["target_version_id"] == "criminal-law@2024-03-01"


def test_lists_a_single_law_timeline_in_effective_date_order():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sources = LegalSourceIntakeService(factory)
    historic = sources.record_candidate(
        _candidate(
            version_id="criminal-law@2020-12-26",
            document_type="STATUTE",
            source_status=SOURCE_STATUS_HISTORICAL,
            effective_from=date(2021, 3, 1),
        )
    )
    current = sources.record_candidate(
        _candidate(
            version_id="criminal-law@2024-03-01",
            document_type="STATUTE",
            source_status=SOURCE_STATUS_CURRENT,
            effective_from=date(2024, 3, 1),
        )
    )
    for item in (historic, current):
        sources.verify_candidate(
            item["id"], authority_url="https://flk.npc.gov.cn/example", reviewer_user_id=1
        )
    chains = StatuteVersionChainService(factory)
    chains.create_chain(
        law_slug="criminal-law",
        target_version_id=historic["version_id"],
        effective_from=date(2021, 3, 1),
        effective_to=date(2024, 2, 29),
        consolidated_source_import_id=historic["id"],
        members=[{"source_import_id": historic["id"], "role": "CONSOLIDATED_TEXT"}],
    )
    chains.create_chain(
        law_slug="criminal-law",
        target_version_id=current["version_id"],
        effective_from=date(2024, 3, 1),
        consolidated_source_import_id=current["id"],
        members=[{"source_import_id": current["id"], "role": "CONSOLIDATED_TEXT"}],
    )

    timeline = chains.list_chains_for_law("criminal-law")

    assert [item["target_version_id"] for item in timeline] == [
        "criminal-law@2020-12-26",
        "criminal-law@2024-03-01",
    ]
