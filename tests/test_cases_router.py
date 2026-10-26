from __future__ import annotations

from types import SimpleNamespace

from app.api.cases import list_cases
from app.runtime import RuntimeContainer


class FakeCaseService:
    def list_cases(self, *, domain, case_cause, source_id):
        assert (domain, case_cause, source_id) == ("civil", None, None)
        return [{"case_id": "case-1"}]


def test_cases_router_reads_from_the_runtime_service() -> None:
    response = list_cases(
        domain="civil",
        case_cause=None,
        source_id=None,
        authorization_context=SimpleNamespace(can=lambda permission: permission == "cases:read"),
        runtime=RuntimeContainer(case_ingestion_service=FakeCaseService()),
    )

    assert response == {"items": [{"case_id": "case-1"}]}
