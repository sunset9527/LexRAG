from __future__ import annotations

from types import SimpleNamespace

from app.api.graph import get_graph
from app.runtime import RuntimeContainer


class FakeGraph:
    def visualize_data(self):
        return {
            "nodes": [
                {"id": "a1", "law_name": "民法典", "article_number": 1, "citation_count": 2},
                {"id": "a2", "law_name": "刑法", "article_number": 2, "citation_count": 0},
            ],
            "edges": [{"from": "a1", "to": "a2"}],
        }

    def get_statistics(self):
        return {"nodes": 2}

    def get_most_cited(self, *, top_n):
        assert top_n == 10
        return [{"id": "a1"}]


def test_graph_router_filters_the_visualization_by_law() -> None:
    response = get_graph(
        law_name="民法典",
        authorization_context=SimpleNamespace(
            can=lambda permission: permission == "knowledge_bases:read"
        ),
        runtime=RuntimeContainer(law_graph=FakeGraph()),
    )

    assert response["available_laws"] == ["刑法", "民法典"]
    assert response["visualization_data"] == {
        "nodes": [
            {
                "id": "a1",
                "name": "第1条",
                "symbolSize": 28,
                "category": 0,
                "law_name": "民法典",
            }
        ],
        "links": [],
    }
