from pathlib import Path

from src.graph.rebuild import LawGraphSource, build_graph_from_sources


def test_graph_rebuild_adds_all_parsed_articles_and_explicit_references(tmp_path: Path):
    source = tmp_path / "示例法.txt"
    source.write_text(
        "示例法\n第一条 为了测试。\n第二条 依照本法第一条执行。\n",
        encoding="utf-8",
    )

    graph = build_graph_from_sources([
        LawGraphSource(law_name="示例法", path=source),
    ])

    assert graph.graph.number_of_nodes() == 2
    assert graph.graph.has_edge("示例法第2条", "示例法第1条")


def test_graph_rebuild_skips_references_to_articles_absent_from_the_current_source(tmp_path: Path):
    source = tmp_path / "示例法.txt"
    source.write_text(
        "示例法\n第一条 为了测试。\n第二条 依照本法第九十九条执行。\n",
        encoding="utf-8",
    )

    graph = build_graph_from_sources([
        LawGraphSource(law_name="示例法", path=source),
    ])

    assert graph.graph.number_of_nodes() == 2
    assert not graph.graph.has_edge("示例法第2条", "示例法第99条")


def test_visualization_data_keeps_law_identity_for_frontend_filtering(tmp_path: Path):
    source = tmp_path / "示例法.txt"
    source.write_text("示例法\n第一条 为了测试。\n", encoding="utf-8")

    graph = build_graph_from_sources([LawGraphSource(law_name="示例法", path=source)])
    node = graph.visualize_data()["nodes"][0]

    assert node["law_name"] == "示例法"
    assert node["article_number"] == "1"
