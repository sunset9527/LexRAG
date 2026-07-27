"""
法律条文检索器

基于Chroma向量检索+元数据过滤
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from langchain_core.prompts import ChatPromptTemplate

from .intent_router import QueryIntent, IntentType

# v1.7: 使用 Langfuse 可观测工厂
from app.services.langfuse_helper import create_llm

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """检索结果"""
    chunk_id: str
    article_id: str
    article_number: str
    law_name: str
    content: str
    full_content: str
    chapter: str
    section: Optional[str]
    score: float
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "article_id": self.article_id,
            "article_number": self.article_number,
            "law_name": self.law_name,
            "content": self.content,
            "full_content": self.full_content,
            "chapter": self.chapter,
            "section": self.section,
            "score": self.score,
            "metadata": self.metadata,
        }


class LawRetriever:
    """
    法律条文检索器
    
    支持：
    - 向量相似度检索
    - 元数据过滤（法律名称、章节、法条范围）
    - 重排序
    - 引用关系增强
    """
    
    def __init__(
        self,
        vectorstore,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat"
    ):
        """
        初始化检索器
        
        Args:
            vectorstore: Chroma向量存储
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
        """
        self.vectorstore = vectorstore
        self.llm = create_llm(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.0,
        )
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        law_name: Optional[str] = None,
        chapter: Optional[str] = None,
        article_range: Optional[tuple] = None,
        intent: Optional[QueryIntent] = None
    ) -> List[RetrievalResult]:
        """
        检索相关法律条文
        
        Args:
            query: 查询文本
            top_k: 返回数量
            law_name: 法律名称过滤
            chapter: 章节过滤
            article_range: 法条范围过滤 (起始, 结束)
            intent: 查询意图
            
        Returns:
            检索结果列表
        """
        # 构建元数据过滤条件
        filter_dict = {}
        if law_name:
            filter_dict["law_name"] = law_name
        if chapter:
            filter_dict["chapter"] = chapter
        
        # 执行检索
        try:
            if filter_dict:
                results = self.vectorstore.similarity_search_with_score(
                    query, k=top_k * 2, filter=filter_dict
                )
            else:
                results = self.vectorstore.similarity_search_with_score(
                    query, k=top_k * 2
                )
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []
        
        # 解析结果
        retrieval_results = []
        seen_articles = set()
        
        for doc, score in results:
            metadata = doc.metadata
            
            # 去重：同一法条只保留最相关的chunk
            article_id = metadata.get("article_id", "")
            if article_id in seen_articles:
                continue
            
            seen_articles.add(article_id)
            
            # 解析内容
            content = doc.page_content
            
            # 提取full_article_content
            full_content = metadata.get("full_article_content", content)
            
            result = RetrievalResult(
                chunk_id=metadata.get("chunk_id", ""),
                article_id=article_id,
                article_number=metadata.get("article_number", ""),
                law_name=metadata.get("law_name", ""),
                content=content,
                full_content=full_content,
                chapter=metadata.get("chapter", ""),
                section=metadata.get("section", ""),
                score=score,
                metadata=metadata
            )
            
            retrieval_results.append(result)
            
            if len(retrieval_results) >= top_k:
                break
        
        # 如果启用了意图分析，进行重排序
        if intent and intent.intent_type == IntentType.CASE_QUERY:
            retrieval_results = self._rerank_for_case_query(retrieval_results, query)
        
        return retrieval_results
    
    def retrieve_by_article_number(
        self, 
        article_number: str, 
        law_name: Optional[str] = None
    ) -> Optional[RetrievalResult]:
        """
        根据法条编号精确检索
        
        Args:
            article_number: 法条编号
            law_name: 法律名称
            
        Returns:
            检索结果
        """
        filter_dict = {"article_number": article_number}
        if law_name:
            filter_dict["law_name"] = law_name
        
        try:
            results = self.vectorstore.get(where=filter_dict)
            if results and results.get("documents"):
                metadata = results["metadatas"][0]
                return RetrievalResult(
                    chunk_id=metadata.get("chunk_id", ""),
                    article_id=metadata.get("article_id", ""),
                    article_number=metadata.get("article_number", ""),
                    law_name=metadata.get("law_name", ""),
                    content=results["documents"][0],
                    full_content=metadata.get("full_article_content", ""),
                    chapter=metadata.get("chapter", ""),
                    section=metadata.get("section", ""),
                    score=1.0,
                    metadata=metadata
                )
        except Exception as e:
            logger.error(f"精确检索失败: {e}")
        
        return None
    
    def retrieve_by_references(
        self, 
        article_ids: List[str]
    ) -> List[RetrievalResult]:
        """
        根据引用关系检索相关法条
        
        Args:
            article_ids: 被引用的法条ID列表
            
        Returns:
            检索结果列表
        """
        results = []
        for article_id in article_ids:
            # 从article_id中提取法条编号
            import re
            match = re.search(r'第(\d+)条', article_id)
            if match:
                article_num = match.group(1)
                result = self.retrieve_by_article_number(article_num)
                if result:
                    results.append(result)
        
        return results
    
    def _rerank_for_case_query(
        self, 
        results: List[RetrievalResult], 
        query: str
    ) -> List[RetrievalResult]:
        """为案例查询重排序"""
        # 简单策略：优先返回有"案例"、"判例"、"判决"等关键词的结果
        case_keywords = ["案例", "判例", "判决", "裁判", "情形", "规定"]
        
        def case_relevance(r: RetrievalResult) -> float:
            content_lower = r.content.lower()
            for kw in case_keywords:
                if kw in content_lower:
                    return r.score + 0.1
            return r.score
        
        return sorted(results, key=case_relevance, reverse=True)
    
    def get_context_for_generation(
        self, 
        results: List[RetrievalResult],
        max_length: int = 4000
    ) -> str:
        """
        构建生成所需的上下文
        
        Args:
            results: 检索结果
            max_length: 最大长度
            
        Returns:
            上下文文本
        """
        context_parts = []
        current_length = 0
        
        for result in results:
            part = f"\n【{result.article_id}】\n{result.full_content}\n"
            if current_length + len(part) > max_length:
                break
            context_parts.append(part)
            current_length += len(part)
        
        return "\n".join(context_parts)
