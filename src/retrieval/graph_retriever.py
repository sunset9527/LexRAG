"""
知识图谱检索器

基于NetworkX实现法条引用关系图的多跳检索
"""

import logging
from collections import deque
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)


class GraphRetrievalResult:
    """图谱检索结果"""

    def __init__(
        self,
        center_article: str,
        hops: int,
        retrieved_articles: list[dict[str, Any]],
        path_details: list[list[str]],
        graph_stats: dict[str, Any],
    ):
        self.center_article = center_article
        self.hops = hops
        self.retrieved_articles = retrieved_articles
        self.path_details = path_details
        self.graph_stats = graph_stats

    def to_dict(self) -> dict[str, Any]:
        return {
            "center_article": self.center_article,
            "hops": self.hops,
            "retrieved_articles": self.retrieved_articles,
            "path_details": self.path_details,
            "graph_stats": self.graph_stats,
        }


class GraphRetriever:
    """
    知识图谱检索器

    基于法条引用关系图进行多跳检索
    支持：
    - 指定跳数的BFS检索
    - 路径追踪
    - 引用关系分析
    """

    def __init__(self, law_graph: nx.DiGraph, max_hops: int = 3):
        """
        初始化图谱检索器

        Args:
            law_graph: NetworkX有向图，表示法条引用关系
            max_hops: 最大检索跳数
        """
        self.graph = law_graph
        self.max_hops = max_hops

    def retrieve(
        self,
        article_id: str,
        max_hops: int | None = None,
        include_outgoing: bool = True,
        include_incoming: bool = True,
    ) -> GraphRetrievalResult:
        """
        从指定法条进行多跳检索

        Args:
            article_id: 起始法条ID
            max_hops: 最大跳数
            include_outgoing: 是否包含引用的法条
            include_incoming: 是否包含被引用的法条

        Returns:
            图谱检索结果
        """
        if max_hops is None:
            max_hops = self.max_hops

        if article_id not in self.graph:
            logger.warning(f"法条 {article_id} 不在图中")
            return GraphRetrievalResult(
                center_article=article_id,
                hops=0,
                retrieved_articles=[],
                path_details=[],
                graph_stats=self._get_graph_stats(),
            )

        # BFS多跳检索
        retrieved = set()
        paths = []
        queue = deque([(article_id, 0, [article_id])])

        while queue:
            current, depth, path = queue.popleft()

            if depth > max_hops:
                continue

            retrieved.add(current)

            # 获取邻居节点
            if include_outgoing:
                outgoing = list(self.graph.successors(current))
                for neighbor in outgoing:
                    if neighbor not in retrieved:
                        queue.append((neighbor, depth + 1, path + [neighbor]))
                        paths.append(path + [neighbor])

            if include_incoming:
                incoming = list(self.graph.predecessors(current))
                for neighbor in incoming:
                    if neighbor not in retrieved:
                        queue.append((neighbor, depth + 1, path + [neighbor]))
                        paths.append(path + [neighbor])

        # 转换为结果格式
        retrieved_articles = []
        for art_id in retrieved:
            node_data = self.graph.nodes[art_id]
            retrieved_articles.append(
                {
                    "article_id": art_id,
                    "content": node_data.get("content", ""),
                    "chapter": node_data.get("chapter", ""),
                    "references_from": list(self.graph.predecessors(art_id)),
                    "references_to": list(self.graph.successors(art_id)),
                }
            )

        return GraphRetrievalResult(
            center_article=article_id,
            hops=max_hops,
            retrieved_articles=retrieved_articles,
            path_details=paths[:20],  # 限制路径数量
            graph_stats=self._get_graph_stats(),
        )

    def retrieve_chain(self, article_ids: list[str], max_hops: int = 2) -> GraphRetrievalResult:
        """
        从多个法条同时检索，返回合并结果

        Args:
            article_ids: 起始法条ID列表
            max_hops: 最大跳数

        Returns:
            图谱检索结果
        """
        all_retrieved = set()
        all_paths = []

        for article_id in article_ids:
            result = self.retrieve(article_id, max_hops)
            all_retrieved.update([a["article_id"] for a in result.retrieved_articles])
            all_paths.extend(result.path_details)

        # 转换为结果格式
        retrieved_articles = []
        for art_id in all_retrieved:
            if art_id in self.graph:
                node_data = self.graph.nodes[art_id]
                retrieved_articles.append(
                    {
                        "article_id": art_id,
                        "content": node_data.get("content", ""),
                        "chapter": node_data.get("chapter", ""),
                        "references_from": list(self.graph.predecessors(art_id)),
                        "references_to": list(self.graph.successors(art_id)),
                    }
                )

        return GraphRetrievalResult(
            center_article="; ".join(article_ids),
            hops=max_hops,
            retrieved_articles=retrieved_articles,
            path_details=all_paths[:20],
            graph_stats=self._get_graph_stats(),
        )

    def find_shortest_path(self, source: str, target: str) -> list[str] | None:
        """
        查找两个法条之间的最短引用路径

        Args:
            source: 起始法条
            target: 目标法条

        Returns:
            最短路径，如果不存在则返回None
        """
        try:
            path = nx.shortest_path(self.graph, source, target)
            return path
        except nx.NetworkXNoPath:
            logger.warning(f"从 {source} 到 {target} 不存在路径")
            return None
        except nx.NodeNotFound as e:
            logger.error("图谱节点不存在 error_type=%s", type(e).__name__)
            return None

    def get_citation_chain(self, article_id: str) -> dict[str, Any]:
        """
        获取法条的完整引用链

        Args:
            article_id: 法条ID

        Returns:
            引用链信息
        """
        if article_id not in self.graph:
            return {"error": "法条不存在"}

        return {
            "article_id": article_id,
            "cited_by": list(self.graph.predecessors(article_id)),  # 被谁引用
            "cites": list(self.graph.successors(article_id)),  # 引用了谁
            "in_degree": self.graph.in_degree(article_id),
            "out_degree": self.graph.out_degree(article_id),
        }

    def find_circular_reference(self) -> list[list[str]]:
        """
        查找图中的循环引用

        Returns:
            循环引用路径列表
        """
        try:
            cycles = list(nx.simple_cycles(self.graph))
            return [list(cycle) for cycle in cycles[:10]]  # 限制数量
        except Exception as e:
            logger.error("查找循环引用失败 error_type=%s", type(e).__name__)
            return []

    def get_most_cited_articles(self, top_n: int = 10) -> list[dict[str, Any]]:
        """
        获取被引用次数最多的法条

        Args:
            top_n: 返回数量

        Returns:
            法条列表
        """
        in_degrees = dict(self.graph.in_degree())
        sorted_articles = sorted(in_degrees.items(), key=lambda x: x[1], reverse=True)[:top_n]

        results = []
        for article_id, in_degree in sorted_articles:
            if in_degree > 0 and article_id in self.graph:
                results.append(
                    {
                        "article_id": article_id,
                        "citation_count": in_degree,
                        "content": self.graph.nodes[article_id].get("content", "")[:100],
                    }
                )

        return results

    def get_referencing_articles(self, article_id: str) -> list[str]:
        """
        获取引用指定法条的所有法条

        Args:
            article_id: 被引用的法条

        Returns:
            引用该法条的法条列表
        """
        return list(self.graph.predecessors(article_id))

    def get_referenced_articles(self, article_id: str) -> list[str]:
        """
        获取指定法条引用的所有法条

        Args:
            article_id: 起始法条

        Returns:
            该法条引用的法条列表
        """
        return list(self.graph.successors(article_id))

    def _get_graph_stats(self) -> dict[str, Any]:
        """获取图统计信息"""
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "density": nx.density(self.graph),
        }

    def visualize_subgraph(self, article_ids: list[str], depth: int = 1) -> nx.DiGraph:
        """
        提取子图用于可视化

        Args:
            article_ids: 核心法条列表
            depth: 扩展深度

        Returns:
            子图
        """
        nodes_to_include = set(article_ids)

        for article_id in article_ids:
            if article_id in self.graph:
                # BFS扩展
                queue = deque([(article_id, 0)])
                visited = {article_id}

                while queue:
                    current, d = queue.popleft()
                    if d >= depth:
                        continue

                    for neighbor in list(self.graph.successors(current)) + list(
                        self.graph.predecessors(current)
                    ):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            nodes_to_include.add(neighbor)
                            queue.append((neighbor, d + 1))

        return self.graph.subgraph(nodes_to_include)
