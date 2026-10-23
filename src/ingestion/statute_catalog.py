"""Canonical, verifiable local statute catalog for the Stage 3 bootstrap.

The catalog describes *local clean-text snapshots*, not an assertion that those
snapshots are current official sources.  A fresh checkout may not include the
texts; callers receive ``UNAVAILABLE`` rather than a false READY result.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.ingestion.statute_ingestion import (
    StatuteDefinition,
    StatuteValidationError,
    validate_clean_law_text,
)


@dataclass(frozen=True)
class CatalogStatute:
    """One local snapshot and the facts verified when it was added."""

    definition: StatuteDefinition
    clean_text_path: Path
    clean_text_sha256: str
    article_count: int
    first_article_number: int
    last_article_number: int


@dataclass(frozen=True)
class StatuteCatalogReport:
    """Source-only bootstrap preflight result; it is not a KB READY status."""

    slug: str
    status: str
    error_code: str | None
    article_count: int | None
    first_article_number: int | None
    last_article_number: int | None
    clean_text_sha256: str | None


@dataclass(frozen=True)
class StatuteIndexIdentity:
    """Inputs that identify an isolated collection built from one statute."""

    slug: str
    source_hash: str
    embedding_fingerprint: str
    index_schema_version: int

    @property
    def collection_name(self) -> str:
        """Never reuse the former unscoped ``law_articles`` collection."""
        safe_slug = self.slug.replace("-", "_")
        return (
            f"kb_{safe_slug}_v_{self.source_hash[:12]}_"
            f"{self.embedding_fingerprint[:12]}"
        )


_LAWS_DIRECTORY = Path("data") / "laws"


STATUTE_CATALOG: tuple[CatalogStatute, ...] = (
    CatalogStatute(
        StatuteDefinition(
            "civil-code",
            "中华人民共和国民法典",
            "civil",
            "civil-code-local-snapshot",
            terminal_article_number=1260,
            first_article_marker="为了保护民事主体的合法权益",
        ),
        _LAWS_DIRECTORY / "中华人民共和国民法典.txt",
        "c9b39cfaed0d8303472105cd7b698764e0ce8262322b025372ecdf00adf978df",
        1262,
        1,
        1260,
    ),
    CatalogStatute(
        StatuteDefinition(
            "criminal-law", "中华人民共和国刑法", "criminal", "criminal-code", 452, "为了惩罚犯罪"
        ),
        _LAWS_DIRECTORY / "criminal-law.txt",
        "0e39e12688a665dcf2b615e9520596c84188b96b8302a3e45189f01e444ffe05",
        491,
        1,
        452,
    ),
    CatalogStatute(
        StatuteDefinition(
            "labor-law", "中华人民共和国劳动法", "labor", "labor-code", 107, "为了保护劳动者的合法权益"
        ),
        _LAWS_DIRECTORY / "labor-law.txt",
        "d033f4134248a1e1c39c2f78b722384551d1a6f2afd4bf3e59f0589cd9e47a07",
        107,
        1,
        107,
    ),
    CatalogStatute(
        StatuteDefinition(
            "labor-contract-law", "中华人民共和国劳动合同法", "labor", "labor-code", 98, "为了完善劳动合同制度"
        ),
        _LAWS_DIRECTORY / "labor-contract-law.txt",
        "682aa37b74340046336ce7f162d98876cc3254855b728089643b3fc886d0517a",
        98,
        1,
        98,
    ),
    CatalogStatute(
        StatuteDefinition(
            "company-law", "中华人民共和国公司法", "company", "company-code", 218, "为了规范公司的组织和行为"
        ),
        _LAWS_DIRECTORY / "company-law.txt",
        "ee0504506473dc14ea9c912a1f74d3ffbb3babcfcd02279cc191e7dab7ff805e",
        218,
        1,
        218,
    ),
    CatalogStatute(
        StatuteDefinition(
            "patent-law", "中华人民共和国专利法", "intellectual-property", "intellectual-property-code", 69, "为了保护专利权人的合法权益"
        ),
        _LAWS_DIRECTORY / "patent-law.txt",
        "dce83a64235b411f73388e3db411f99c5de7e82c8073aadbb99c0202d2822659",
        69,
        1,
        69,
    ),
    CatalogStatute(
        StatuteDefinition(
            "trademark-law", "中华人民共和国商标法", "intellectual-property", "intellectual-property-code", 73, "为了加强商标管理"
        ),
        _LAWS_DIRECTORY / "trademark-law.txt",
        "88554a300d6c2a7d89c7b92d1aae9840522b2d3a4557c38d8f983051cd0d5c05",
        73,
        1,
        73,
    ),
    CatalogStatute(
        StatuteDefinition(
            "copyright-law", "中华人民共和国著作权法", "intellectual-property", "intellectual-property-code", 61, "为保护文学、艺术和科学作品作者的著作权"
        ),
        _LAWS_DIRECTORY / "copyright-law.txt",
        "9c6ec45fc77150fc19802ff1c6e2030b41cdc4bdd6c33b13c72570b79a0f6f00",
        61,
        1,
        61,
    ),
)


def statute_definitions() -> tuple[StatuteDefinition, ...]:
    """Compatibility view for existing preparation and ingestion commands."""
    return tuple(item.definition for item in STATUTE_CATALOG)


def statute_by_slug(slug: str) -> CatalogStatute:
    """Return the canonical entry or fail before a command writes anything."""
    for item in STATUTE_CATALOG:
        if item.definition.slug == slug:
            return item
    raise ValueError(f"未知法律 slug: {slug}")


def inspect_statute_catalog(
    catalog: tuple[CatalogStatute, ...] = STATUTE_CATALOG, *, project_root: Path
) -> tuple[StatuteCatalogReport, ...]:
    """Verify present snapshots and explicitly report absent or invalid files."""
    return tuple(_inspect_one(item, project_root=project_root) for item in catalog)


def _inspect_one(item: CatalogStatute, *, project_root: Path) -> StatuteCatalogReport:
    text_path = project_root / item.clean_text_path
    if not text_path.is_file():
        return StatuteCatalogReport(
            item.definition.slug, "UNAVAILABLE", "STATUTE_SOURCE_MISSING", None, None, None, None
        )

    try:
        report = validate_clean_law_text(text_path.read_text(encoding="utf-8"), item.definition)
    except (OSError, StatuteValidationError, UnicodeError):
        return StatuteCatalogReport(
            item.definition.slug, "UNAVAILABLE", "STATUTE_SOURCE_INVALID", None, None, None, None
        )

    actual_facts = (
        report.clean_text_sha256,
        report.article_count,
        report.first_article_number,
        report.last_article_number,
    )
    expected_facts = (
        item.clean_text_sha256,
        item.article_count,
        item.first_article_number,
        item.last_article_number,
    )
    if actual_facts != expected_facts:
        return StatuteCatalogReport(
            item.definition.slug, "UNAVAILABLE", "STATUTE_SOURCE_FACTS_MISMATCH", None, None, None, None
        )

    return StatuteCatalogReport(
        item.definition.slug,
        "AVAILABLE",
        None,
        report.article_count,
        report.first_article_number,
        report.last_article_number,
        report.clean_text_sha256,
    )
