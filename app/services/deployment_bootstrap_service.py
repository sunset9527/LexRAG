"""Explicit runtime bootstrap for the verified local statute catalog.

This service deliberately treats source availability and Chroma/index readiness as
separate facts.  A missing or invalid local snapshot is reported as UNAVAILABLE;
it is never converted into a READY database record.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol

from app.services.knowledge_base_service import KnowledgeBaseAlreadyExistsError
from config import settings
from src.ingestion.index_identity import collection_identity_from_settings
from src.ingestion.statute_catalog import (
    STATUTE_CATALOG,
    CatalogStatute,
    StatuteIndexIdentity,
    inspect_statute_catalog,
)


class BootstrapKnowledgeBaseWriter(Protocol):
    """The narrow write contract needed by deployment bootstrap."""

    def create_knowledge_base(
        self,
        *,
        name: str,
        slug: str,
        law_area: str,
        is_system_shared: bool = False,
    ) -> dict[str, Any]: ...

    def rebuild_bootstrap_statute(
        self, slug: str, *, content: str, identity: StatuteIndexIdentity
    ) -> dict[str, Any]: ...

    def recover_expired_bootstrap_claim(self, slug: str, *, max_age: timedelta) -> bool: ...


class DeploymentBootstrapService:
    """Build only source-validated statute collections, one law at a time."""

    BOOTSTRAP_CLAIM_MAX_AGE = timedelta(minutes=30)

    def __init__(
        self,
        knowledge_base_service: BootstrapKnowledgeBaseWriter,
        *,
        catalog: tuple[CatalogStatute, ...] = STATUTE_CATALOG,
        project_root: Path | None = None,
    ) -> None:
        self._knowledge_base_service = knowledge_base_service
        self._catalog = catalog
        self._project_root = project_root or Path(__file__).resolve().parents[2]

    def validate(self, slugs: Iterable[str] | None = None) -> dict[str, object]:
        """Report catalog-source facts without initializing a database or Chroma."""
        selected = self._select_catalog(slugs)
        reports = inspect_statute_catalog(selected, project_root=self._project_root)
        return {
            "action": "validate",
            "laws": [
                {
                    "slug": report.slug,
                    "status": report.status,
                    **({"error_code": report.error_code} if report.error_code else {}),
                }
                for report in reports
            ],
        }

    def bootstrap_all(self) -> dict[str, object]:
        """Attempt every catalog statute independently and retain all outcomes."""
        return self.bootstrap()

    def bootstrap_statute(self, slug: str) -> dict[str, object]:
        """Bootstrap exactly one catalog statute."""
        return self.bootstrap((slug,))

    def bootstrap(self, slugs: Iterable[str] | None = None) -> dict[str, object]:
        """Build available snapshots; failure of one statute never stops the next."""
        selected = self._select_catalog(slugs)
        reports = inspect_statute_catalog(selected, project_root=self._project_root)
        report_by_slug = {report.slug: report for report in reports}
        outcomes: list[dict[str, str]] = []
        for item in selected:
            report = report_by_slug[item.definition.slug]
            if report.status != "AVAILABLE":
                outcomes.append(
                    {
                        "slug": item.definition.slug,
                        "status": "UNAVAILABLE",
                        "error_code": report.error_code or "STATUTE_SOURCE_INVALID",
                    }
                )
                continue
            try:
                self._knowledge_base_service.recover_expired_bootstrap_claim(
                    item.definition.slug,
                    max_age=self.BOOTSTRAP_CLAIM_MAX_AGE,
                )
                self._create_or_reuse_statute(item)
                content = (self._project_root / item.clean_text_path).read_text(encoding="utf-8")
                embedding_identity = collection_identity_from_settings(settings)
                result = self._knowledge_base_service.rebuild_bootstrap_statute(
                    item.definition.slug,
                    content=content,
                    identity=StatuteIndexIdentity(
                        slug=item.definition.slug,
                        source_hash=report.clean_text_sha256 or "",
                        embedding_fingerprint=embedding_identity.fingerprint,
                        index_schema_version=embedding_identity.schema_version,
                    ),
                )
                if result.get("status") != "READY":
                    raise RuntimeError("BOOTSTRAP_RESULT_NOT_READY")
                outcomes.append(
                    {
                        "slug": item.definition.slug,
                        "status": "READY",
                        "bootstrap_action": str(result.get("bootstrap_action", "rebuilt")),
                        "collection_name": str(result.get("collection_name", "")),
                    }
                )
            except Exception as exc:
                outcomes.append(
                    {
                        "slug": item.definition.slug,
                        "status": "FAILED",
                        "error_code": f"BOOTSTRAP_FAILED:{type(exc).__name__}",
                    }
                )
        return {"action": "bootstrap", "laws": outcomes}

    def _select_catalog(self, slugs: Iterable[str] | None) -> tuple[CatalogStatute, ...]:
        if slugs is None:
            return self._catalog
        requested = tuple(slugs)
        by_slug = {item.definition.slug: item for item in self._catalog}
        unknown = [slug for slug in requested if slug not in by_slug]
        if unknown:
            raise ValueError(f"未知法律 slug: {', '.join(unknown)}")
        return tuple(by_slug[slug] for slug in requested)

    def _create_or_reuse_statute(self, item: CatalogStatute) -> None:
        try:
            self._knowledge_base_service.create_knowledge_base(
                name=item.definition.name,
                slug=item.definition.slug,
                law_area=item.definition.law_area,
                is_system_shared=True,
            )
        except KnowledgeBaseAlreadyExistsError:
            pass
