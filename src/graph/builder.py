"""
图谱构建器

从法律文档和标注数据构建法律知识图谱
"""

import logging
import re
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

from .law_graph import LawGraph
from ..ingestion.law_parser import LawArticle, LawParser

logger = logging.getLogger(__name__)


class GraphBuilder:
    """
    法律知识图谱构建器
    
    从法律文档和结构化数据构建法条引用关系图
    """
    
    # 法条引用正则表达式
    REFERENCE_PATTERN = re.compile(
        r'(?:依据|依照|根据|参照|适用|比照|适用于|本章)?(?:本法|(?:《[^》]+》))'
        r'(?:第)?([零一二三四五六七八九十百千\d]+)?条'
    )
    
    # 常见引用模式
    CITATION_PATTERNS = [
        r'依据本法第(\d+)条',
        r'依照本法第(\d+)条',
        r'根据本法第(\d+)条',
        r'参照本法第(\d+)条',
        r'适用本法第(\d+)条',
        r'比照本法第(\d+)条',
        r'本章第(\d+)条',
        r'前条第(\d+)款',
        r'第(\d+)条(?:之(\d+))?',
    ]
    
    def __init__(self):
        """初始化构建器"""
        self.graph = LawGraph()
        self.parser = LawParser()
    
    def build_from_articles(
        self,
        articles: List[LawArticle],
        add_implicit_references: bool = True
    ) -> LawGraph:
        """
        从法律条文列表构建图谱
        
        Args:
            articles: 法律条文列表
            add_implicit_references: 是否添加隐式引用关系
            
        Returns:
            构建好的图谱
        """
        self.graph = LawGraph()
        
        # 1. 添加所有节点
        for article in articles:
            self._add_article_node(article)
        
        # 2. 提取引用关系并添加边
        for article in articles:
            self._extract_and_add_references(article)
        
        # 3. 添加隐式引用关系（可选）
        if add_implicit_references:
            self._add_implicit_references(articles)
        
        logger.info(
            f"图谱构建完成: {self.graph.graph.number_of_nodes()} 节点, "
            f"{self.graph.graph.number_of_edges()} 边"
        )
        
        return self.graph
    
    def build_from_file(
        self,
        file_path: str,
        law_name: str = "法律"
    ) -> LawGraph:
        """
        从法律文件构建图谱
        
        Args:
            file_path: 法律文件路径
            law_name: 法律名称
            
        Returns:
            构建好的图谱
        """
        articles = self.parser.parse_law_file(file_path)
        
        # 设置法律名称
        for article in articles:
            article.law_name = law_name
        
        return self.build_from_articles(articles)
    
    def build_from_json(self, json_path: str) -> LawGraph:
        """
        从JSON文件加载图谱
        
        Args:
            json_path: JSON文件路径
            
        Returns:
            图谱对象
        """
        return LawGraph.from_json(json_path)
    
    def _add_article_node(self, article: LawArticle):
        """添加法条节点"""
        article_id = article.article_id
        
        self.graph.add_node(
            article_id,
            content=article.content,
            law_name=article.law_name,
            chapter=article.chapter,
            section=article.section,
            article_number=article.article_number,
            references=article.references,
            effective_date=article.effective_date
        )
    
    def _extract_and_add_references(self, article: LawArticle):
        """提取引用关系并添加边"""
        article_id = article.article_id
        content = article.content
        
        # 使用预解析的引用列表
        for ref in article.references:
            target_id = self._build_article_id(ref, article.law_name)
            if target_id and target_id != article_id:
                self.graph.add_edge(
                    article_id,
                    target_id,
                    relation_type="cites",
                    weight=1.0
                )
        
        # 从内容中额外提取
        for pattern in self.CITATION_PATTERNS:
            matches = re.finditer(pattern, content)
            for match in matches:
                if match.group(1):
                    ref_num = match.group(1)
                    target_id = self._build_article_id(
                        f"第{ref_num}条",
                        article.law_name
                    )
                    if target_id and target_id != article_id:
                        # 避免重复边
                        if not self.graph.graph.has_edge(article_id, target_id):
                            self.graph.add_edge(
                                article_id,
                                target_id,
                                relation_type="cites",
                                weight=0.5
                            )
    
    def _add_implicit_references(
        self,
        articles: List[LawArticle]
    ):
        """添加隐式引用关系"""
        # 按章节或主题添加语义相关的引用
        articles_by_chapter = {}
        for article in articles:
            chapter = article.chapter or "default"
            if chapter not in articles_by_chapter:
                articles_by_chapter[chapter] = []
            articles_by_chapter[chapter].append(article)
        
        # 章节内的相邻条文可以添加弱引用
        for chapter, chapter_articles in articles_by_chapter.items():
            sorted_articles = sorted(
                chapter_articles,
                key=lambda x: int(x.article_number) if x.article_number.isdigit() else 0
            )
            
            for i in range(len(sorted_articles) - 1):
                current = sorted_articles[i]
                next_article = sorted_articles[i + 1]
                
                # 如果没有显式引用，添加弱引用
                if not self.graph.graph.has_edge(current.article_id, next_article.article_id):
                    # 检查内容是否有关联词
                    linking_words = ["前款", "前项", "上述", "以下"]
                    if any(word in current.content for word in linking_words):
                        self.graph.add_edge(
                            current.article_id,
                            next_article.article_id,
                            relation_type="implicit_cites",
                            weight=0.3
                        )
    
    def _build_article_id(self, ref: str, law_name: str) -> Optional[str]:
        """构建完整的法条ID"""
        # 提取条号
        match = re.search(r'第([零一二三四五六七八九十百千\d]+)条', ref)
        if match:
            return f"{law_name}第{match.group(1)}条"
        return None
    
    def add_manual_edges(
        self,
        edges: List[Dict[str, str]]
    ):
        """
        添加手动指定的边
        
        Args:
            edges: 边列表 [{"from": "法条1", "to": "法条2", "relation": "类型"}]
        """
        for edge in edges:
            self.graph.add_edge(
                edge["from"],
                edge["to"],
                relation_type=edge.get("relation", "cites"),
                weight=edge.get("weight", 1.0)
            )
    
    def save(self, output_path: str):
        """保存图谱"""
        self.graph.to_json(output_path)
    
    def merge_graphs(self, other_graph: LawGraph):
        """合并另一个图谱"""
        # 合并节点
        for node in other_graph.graph.nodes():
            if node not in self.graph.graph:
                self.graph.add_node(node, **other_graph.get_node_data(node))
        
        # 合并边
        for u, v, data in other_graph.graph.edges(data=True):
            if not self.graph.graph.has_edge(u, v):
                self.graph.add_edge(u, v, **data)
    
    def get_circular_references(self) -> List[List[str]]:
        """检测循环引用"""
        return self.graph.find_circular_reference()
