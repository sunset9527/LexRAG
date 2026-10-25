"""查询应明确选择一个经核验的法规版本。"""

from datetime import date

from app.services.query_version_service import QueryVersionService


class FakeChains:
    def get_indexable_chain_for_law(self, law_slug, *, as_of):
        assert law_slug == "public-security-administration-punishment-law"
        return {
            "id": 11,
            "law_slug": law_slug,
            "target_version_id": "public-security-administration-punishment-law@2025-06-27",
            "effective_from": "2026-01-01",
            "effective_to": None,
        }

    def get_index_provenance(self, chain_id, *, as_of):
        assert chain_id == 11
        return {
            "version_id": "public-security-administration-punishment-law@2025-06-27",
            "effective_from": "2026-01-01",
            "effective_to": "",
            "source_url": "https://flk.npc.gov.cn/",
            "content_hash": "a" * 64,
        }

    def list_chains_for_law(self, law_slug):
        assert law_slug == "public-security-administration-punishment-law"
        return [
            {
                "target_version_id": "public-security-administration-punishment-law@2012-10-26",
                "effective_from": "2013-01-01",
                "effective_to": "2025-12-31",
            },
            {
                "target_version_id": "public-security-administration-punishment-law@2025-06-27",
                "effective_from": "2026-01-01",
                "effective_to": None,
            },
        ]


class FakeKnowledgeBases:
    def get_confirmed_version_collection_name_for_organization(
        self, slug, *, organization_id, content_hash
    ):
        assert slug == "public-security-administration-punishment-law"
        assert organization_id == 9
        assert content_hash == "a" * 64
        return "kb_public_security_administration_punishment_law_v_aaaaaaaaaaaa"


def test_explicit_case_date_returns_selected_version_provenance_and_timeline():
    selection = QueryVersionService(
        FakeChains(), FakeKnowledgeBases(), today_provider=lambda: date(2026, 10, 25)
    ).resolve(
        "public-security-administration-punishment-law",
        organization_id=9,
        case_date=date(2026, 2, 1),
    )

    assert selection.collection_name.endswith("aaaaaaaaaaaa")
    assert selection.assumption is None
    assert selection.provenance["version_id"].endswith("2025-06-27")
    assert len(selection.timeline) == 2


def test_missing_case_date_uses_today_and_returns_explicit_assumption():
    selection = QueryVersionService(
        FakeChains(), FakeKnowledgeBases(), today_provider=lambda: date(2026, 10, 25)
    ).resolve(
        "public-security-administration-punishment-law",
        organization_id=9,
        case_date=None,
    )

    assert selection.as_of == date(2026, 10, 25)
    assert selection.assumption == "未提供案件发生时间，按当前有效法规检索"
