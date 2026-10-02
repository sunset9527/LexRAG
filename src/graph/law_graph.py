"""
法律知识图谱

使用NetworkX构建和管理法条引用关系图
"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import networkx as nx

logger = logging.getLogger(__name__)


class LawGraph:
    """
    法律知识图谱
    
    使用NetworkX有向图表示法条之间的引用关系
    - 节点：法条（article_id）
    - 边：引用关系（从引用法指向被引用法）
    """
    
    def __init__(self):
        """初始化空图谱"""
        self.graph = nx.DiGraph()
        self.metadata: Dict[str, Any] = {
            "name": "法律知识图谱",
            "version": "1.0",
            "description": "法条引用关系图"
        }
    
    def add_node(
        self,
        article_id: str,
        content: str = "",
        law_name: str = "",
        chapter: str = "",
        section: str = "",
        **kwargs
    ):
        """
        添加法条节点
        
        Args:
            article_id: 法条ID
            content: 法条内容
            law_name: 法律名称
            chapter: 所属章节
            section: 所属小节
            **kwargs: 其他属性
        """
        self.graph.add_node(
            article_id,
            content=content,
            law_name=law_name,
            chapter=chapter,
            section=section,
            **kwargs
        )
    
    def add_edge(
        self,
        from_article: str,
        to_article: str,
        relation_type: str = "cites",
        weight: float = 1.0,
        **kwargs
    ):
        """
        添加引用边（from引用to）
        
        Args:
            from_article: 引用法条
            to_article: 被引用法条
            relation_type: 关系类型
            weight: 权重
        """
        self.graph.add_edge(
            from_article,
            to_article,
            relation_type=relation_type,
            weight=weight,
            **kwargs
        )
    
    def remove_node(self, article_id: str):
        """移除法条节点"""
        if article_id in self.graph:
            self.graph.remove_node(article_id)
    
    def remove_edge(self, from_article: str, to_article: str):
        """移除引用边"""
        if self.graph.has_edge(from_article, to_article):
            self.graph.remove_edge(from_article, to_article)
    
    def get_node_data(self, article_id: str) -> Optional[Dict[str, Any]]:
        """获取节点数据"""
        if article_id in self.graph:
            return dict(self.graph.nodes[article_id])
        return None
    
    def get_neighbors(
        self,
        article_id: str,
        direction: str = "both"
    ) -> List[str]:
        """
        获取邻居节点
        
        Args:
            article_id: 法条ID
            direction: 方向 ('out'/'in'/'both')
            
        Returns:
            邻居节点列表
        """
        if article_id not in self.graph:
            return []
        
        if direction == "out":
            return list(self.graph.successors(article_id))
        elif direction == "in":
            return list(self.graph.predecessors(article_id))
        else:
            return list(self.graph.successors(article_id)) + list(self.graph.predecessors(article_id))
    
    def get_citation_chain(
        self,
        article_id: str,
        max_depth: int = 3
    ) -> List[Tuple[str, List[str]]]:
        """
        获取引用链
        
        Args:
            article_id: 起始法条
            max_depth: 最大深度
            
        Returns:
            引用链列表
        """
        chains = []
        
        def dfs(current, path, depth):
            if depth > max_depth:
                return
            successors = list(self.graph.successors(current))
            if not successors:
                chains.append(path)
            else:
                for s in successors:
                    dfs(s, path + [s], depth + 1)
        
        dfs(article_id, [article_id], 0)
        return chains
    
    def find_shortest_path(
        self,
        source: str,
        target: str
    ) -> Optional[List[str]]:
        """查找最短路径"""
        try:
            return nx.shortest_path(self.graph, source, target)
        except nx.NetworkXNoPath:
            return None
        except nx.NodeNotFound:
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取图谱统计信息"""
        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "density": nx.density(self.graph),
            "is_dag": nx.is_directed_acyclic_graph(self.graph),
            "avg_degree": sum(dict(self.graph.degree()).values()) / self.graph.number_of_nodes() 
                if self.graph.number_of_nodes() > 0 else 0,
        }
    
    def get_most_cited(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """获取被引用最多的法条"""
        in_degrees = dict(self.graph.in_degree())
        sorted_nodes = sorted(
            in_degrees.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]
        
        return [
            {
                "article_id": node,
                "citation_count": degree,
                "content": self.graph.nodes[node].get("content", "")[:100]
            }
            for node, degree in sorted_nodes
            if degree > 0
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字典"""
        nodes = []
        for node in self.graph.nodes():
            nodes.append({
                "id": node,
                **dict(self.graph.nodes[node])
            })
        
        edges = []
        for u, v, data in self.graph.edges(data=True):
            edges.append({
                "from": u,
                "to": v,
                **data
            })
        
        return {
            "metadata": self.metadata,
            "nodes": nodes,
            "edges": edges
        }
    
    def to_json(self, file_path: str):
        """保存为JSON文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"图谱已保存到: {file_path}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LawGraph":
        """从字典加载"""
        graph = cls()
        graph.metadata = data.get("metadata", {})
        
        for node_data in data.get("nodes", []):
            node_id = node_data.pop("id")
            graph.add_node(node_id, **node_data)
        
        for edge_data in data.get("edges", []):
            from_node = edge_data.pop("from")
            to_node = edge_data.pop("to")
            graph.add_edge(from_node, to_node, **edge_data)
        
        return graph
    
    @classmethod
    def from_json(cls, file_path: str) -> "LawGraph":
        """从JSON文件加载"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def visualize_data(self) -> Dict[str, Any]:
        """生成可视化所需的数据"""
        return {
            "nodes": [
                {
                    "id": node,
                    "label": node,
                    "chapter": self.graph.nodes[node].get("chapter", ""),
                    "law_name": self.graph.nodes[node].get("law_name", ""),
                    "article_number": self.graph.nodes[node].get("article_number", ""),
                    "citation_count": self.graph.in_degree(node)
                }
                for node in self.graph.nodes()
            ],
            "edges": [
                {"from": u, "to": v}
                for u, v in self.graph.edges()
            ]
        }
