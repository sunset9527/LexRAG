"""Stage 3 statute catalog contracts: source facts, availability and version identity."""

from __future__ import annotations

from pathlib import Path


def test_catalog_has_eight_unique_laws_with_project_relative_text_paths():
    """The catalog is the one source of truth and must not encode a host path."""
    from src.ingestion.statute_catalog import STATUTE_CATALOG

    assert len(STATUTE_CATALOG) == 8
    assert len({item.definition.slug for item in STATUTE_CATALOG}) == 8
    assert len({item.definition.name for item in STATUTE_CATALOG}) == 8
    assert len({item.clean_text_path for item in STATUTE_CATALOG}) == 8
    assert all(not item.clean_text_path.is_absolute() for item in STATUTE_CATALOG)
    assert all("E:" not in str(item.clean_text_path) for item in STATUTE_CATALOG)


def test_catalog_reports_missing_source_as_unavailable_without_claiming_ready(tmp_path: Path):
    """A fresh checkout may lack statute texts; bootstrap must say so truthfully."""
    from src.ingestion.statute_catalog import STATUTE_CATALOG, inspect_statute_catalog

    reports = inspect_statute_catalog(STATUTE_CATALOG, project_root=tmp_path)

    assert len(reports) == 8
    assert {report.status for report in reports} == {"UNAVAILABLE"}
    assert {report.error_code for report in reports} == {"STATUTE_SOURCE_MISSING"}
    assert all(report.article_count is None for report in reports)
    assert all(report.clean_text_sha256 is None for report in reports)


def test_catalog_reports_existing_snapshots_as_available_after_validation():
    """The eight checked-in snapshots must agree with their recorded source facts."""
    from src.ingestion.statute_catalog import STATUTE_CATALOG, inspect_statute_catalog

    project_root = Path(__file__).parent.parent
    reports = inspect_statute_catalog(STATUTE_CATALOG, project_root=project_root)

    assert [report.slug for report in reports if report.status == "AVAILABLE"] == [
        "civil-code",
        "criminal-law",
        "labor-law",
        "labor-contract-law",
        "company-law",
        "patent-law",
        "trademark-law",
        "copyright-law",
    ]
    assert all(report.error_code is None for report in reports)
    assert reports[0].article_count == 1260
    assert {report.slug for report in reports} == {
        "civil-code",
        "criminal-law",
        "labor-law",
        "labor-contract-law",
        "company-law",
        "patent-law",
        "trademark-law",
        "copyright-law",
    }


def test_versioned_collection_name_isolated_from_legacy_default_collection():
    """A bootstrap build can never target or delete the historic ``law_articles`` collection."""
    from src.ingestion.statute_catalog import StatuteIndexIdentity

    identity = StatuteIndexIdentity(
        slug="civil-code",
        source_hash="a" * 64,
        embedding_fingerprint="b" * 64,
        index_schema_version=1,
    )

    assert identity.collection_name == "kb_civil_code_v_aaaaaaaaaaaa_bbbbbbbbbbbb"
    assert identity.collection_name != "law_articles"


def test_legacy_ingestion_entrypoint_reuses_the_canonical_catalog():
    """The older command must not retain an independent seven-law definition list."""
    from scripts.ingest_statutes import STATUTE_DEFINITIONS
    from src.ingestion.statute_catalog import statute_definitions

    assert STATUTE_DEFINITIONS == statute_definitions()


def test_legacy_civil_rebuild_entrypoint_reuses_the_catalog_source_path():
    """Civil-code compatibility command must not retain its own source definition."""
    from scripts.rebuild_civil_code_knowledge_base import CIVIL_CODE_STATUTE, SOURCE_FILE
    from src.ingestion.statute_catalog import statute_by_slug

    assert CIVIL_CODE_STATUTE == statute_by_slug("civil-code")
    assert SOURCE_FILE == Path(__file__).parent.parent / CIVIL_CODE_STATUTE.clean_text_path
