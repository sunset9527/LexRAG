"""Resolve one verified statute version for a legal query."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class QueryVersionSelection:
    """The only statute collection and provenance a query may use."""

    as_of: date
    collection_name: str
    provenance: Mapping[str, str]
    timeline: list[dict[str, Any]]
    assumption: str | None


class QueryVersionService:
    def __init__(
        self,
        statute_chains: Any,
        knowledge_bases: Any,
        *,
        today_provider: Callable[[], date] = date.today,
    ):
        self._statute_chains = statute_chains
        self._knowledge_bases = knowledge_bases
        self._today_provider = today_provider

    def resolve(
        self,
        law_slug: str,
        *,
        organization_id: int,
        case_date: date | None,
    ) -> QueryVersionSelection:
        as_of = case_date or self._today_provider()
        chain = self._statute_chains.get_indexable_chain_for_law(law_slug, as_of=as_of)
        provenance = self._statute_chains.get_index_provenance(chain["id"], as_of=as_of)
        collection_name = self._knowledge_bases.get_confirmed_version_collection_name_for_organization(
            law_slug,
            organization_id=organization_id,
            content_hash=provenance["content_hash"],
        )
        return QueryVersionSelection(
            as_of=as_of,
            collection_name=collection_name,
            provenance=provenance,
            timeline=self._statute_chains.list_chains_for_law(law_slug),
            assumption=("未提供案件发生时间，按当前有效法规检索" if case_date is None else None),
        )
