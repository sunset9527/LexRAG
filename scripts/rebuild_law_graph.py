"""从 data/laws 的八部已校验法规文本重建 data/law_graph.json。"""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.graph.rebuild import LawGraphSource, build_graph_from_sources  # noqa: E402


SOURCES = (
    ("中华人民共和国民法典", "中华人民共和国民法典.txt"),
    ("中华人民共和国刑法", "criminal-law.txt"),
    ("中华人民共和国劳动法", "labor-law.txt"),
    ("中华人民共和国劳动合同法", "labor-contract-law.txt"),
    ("中华人民共和国公司法", "company-law.txt"),
    ("中华人民共和国专利法", "patent-law.txt"),
    ("中华人民共和国商标法", "trademark-law.txt"),
    ("中华人民共和国著作权法", "copyright-law.txt"),
)


def main() -> int:
    laws_directory = PROJECT_ROOT / "data" / "laws"
    graph = build_graph_from_sources(
        LawGraphSource(law_name=name, path=laws_directory / filename)
        for name, filename in SOURCES
    )
    output = PROJECT_ROOT / "data" / "law_graph.json"
    graph.to_json(output)
    stats = graph.get_statistics()
    print(f"重建完成：{stats['node_count']} 个法条节点，{stats['edge_count']} 条显式引用边")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
