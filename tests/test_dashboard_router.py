from __future__ import annotations

from app.api.dashboard import get_dashboard_stats
from app.runtime import RuntimeContainer


class FakeCaseService:
    def get_statistics(self) -> dict[str, int]:
        return {"case_count": 623, "source_count": 10}


def test_dashboard_router_reads_case_statistics_from_runtime() -> None:
    response = get_dashboard_stats(
        current_user=object(),
        runtime=RuntimeContainer(case_ingestion_service=FakeCaseService()),
    )

    assert response.model_dump() == {"case_count": 623, "source_count": 10}
