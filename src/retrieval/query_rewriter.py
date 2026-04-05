"""查询改写模块"""
import logging
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

@dataclass
class RewrittenQuery:
    """改写后的查询"""
    original_query: str
    rewritten_query: str
    search_keywords: List[str]
    hyde_answer: Optional[str] = None

class QueryRewriter:
    """
    查询改写器
    
    功能：
    1. 将口语化问题改写为法律专业查询词
    2. 提取搜索关键词
    3. 可选：生成HyDE假设回答用于检索
    """
    
    REWRITE_PROMPT = """你是一个法律检索专家，需要将用户的口语化问题改写为更适合法律检索的查询。

用户问题：{query}

请将这个问题改写为法律专业术语的检索查询，并提取3-5个搜索关键词。

输出JSON格式：
{{
    "rewritten_query": "改写后的查询",
    "search_keywords": ["关键词1", "关键词2", "关键词3"]
}}

请严格按照JSON格式返回，不要包含markdown代码块标记或其他内容。"""
    
    HYDE_PROMPT = """你是一个法律专家，请针对以下问题写一段假设性的回答（不需要完全正确，但要包含相关的法律术语和概念）。

问题：{query}

假设回答："""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat"
    ):
        self.llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.1
        )
    
    def rewrite(self, query: str) -> RewrittenQuery:
        """改写查询"""
        try:
            prompt = self.REWRITE_PROMPT.format(query=query)
            response = self.llm.invoke(prompt)
            content = response.content.strip().replace('```json','').replace('```','')
            result = json.loads(content)
            
            return RewrittenQuery(
                original_query=query,
                rewritten_query=result.get("rewritten_query", query),
                search_keywords=result.get("search_keywords", [])
            )
        except Exception as e:
            logger.error(f"查询改写失败: {e}")
            return RewrittenQuery(
                original_query=query,
                rewritten_query=query,
                search_keywords=[query]
            )
    
    def generate_hyde(self, query: str) -> str:
        """生成HyDE假设回答"""
        try:
            prompt = self.HYDE_PROMPT.format(query=query)
            response = self.llm.invoke(prompt)
            return response.content
        except Exception as e:
            logger.error(f"HyDE生成失败: {e}")
            return query
    
    def rewrite_with_hyde(self, query: str) -> RewrittenQuery:
        """改写查询 + 生成HyDE"""
        rewritten = self.rewrite(query)
        rewritten.hyde_answer = self.generate_hyde(query)
        return rewritten
