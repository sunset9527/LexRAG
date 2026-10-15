"""从已校验法规原文重建可解释的法条引用图谱。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from src.graph.builder import GraphBuilder
from src.graph.law_graph import LawGraph
from src.ingestion.law_parser import LawArticle, LawParser


@dataclass(frozen=True)
class LawGraphSource:
    """一部法规的可追溯清洗文本来源。"""

    law_name: str
    path: Path


def build_graph_from_sources(sources: Iterable[LawGraphSource]) -> LawGraph:
    """为每条解析到的法条建节点，并仅保留文本中可解释的显式引用边。"""
    articles: list[LawArticle] = []
    for source in sources:
        content = Path(source.path).read_text(encoding="utf-8")
        articles.extend(LawParser().parse_law_content(content, law_name=source.law_name))
    return GraphBuilder().build_from_articles(articles, add_implicit_references=False)
