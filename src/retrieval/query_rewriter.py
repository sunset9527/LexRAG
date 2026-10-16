"""查询改写模块"""

import json
import logging
from dataclasses import dataclass, field

# v1.7: Langfuse 可观测工厂
from app.services.langfuse_helper import create_llm

logger = logging.getLogger(__name__)


@dataclass
class RewrittenQuery:
    """改写后的查询"""

    original_query: str
    rewritten_query: str
    search_keywords: list[str]
    hyde_answer: str | None = None
    search_queries: list[str] = field(default_factory=list)


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

    MULTI_REWRITE_PROMPT = """你是一个法律检索专家。请将用户的口语化问题改写为最多 3 条不同的法律专业检索查询，并提取 3-5 个关键词。

用户问题：{query}

输出 JSON：
{{
    "rewritten_queries": ["候选检索查询 1", "候选检索查询 2"],
    "search_keywords": ["关键词1", "关键词2"]
}}

不要输出 Markdown 或其他文字。"""

    HYDE_PROMPT = """你是一个法律专家，请针对以下问题写一段假设性的回答（不需要完全正确，但要包含相关的法律术语和概念）。

问题：{query}

假设回答："""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
    ):
        self.llm = create_llm(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.1,
        )

    def rewrite(self, query: str) -> RewrittenQuery:
        """改写查询"""
        try:
            prompt = self.REWRITE_PROMPT.format(query=query)
            response = self.llm.invoke(prompt)
            content = response.content.strip().replace("```json", "").replace("```", "")
            result = json.loads(content)

            return RewrittenQuery(
                original_query=query,
                rewritten_query=result.get("rewritten_query", query),
                search_keywords=result.get("search_keywords", []),
            )
        except Exception as e:
            logger.error(f"查询改写失败: {e}")
            return RewrittenQuery(
                original_query=query, rewritten_query=query, search_keywords=[query]
            )

    def rewrite_candidates(self, query: str) -> RewrittenQuery:
        """生成最多三条去重候选；原问题总是第一个检索查询。"""
        try:
            prompt = self.MULTI_REWRITE_PROMPT.format(query=query)
            response = self.llm.invoke(prompt)
            content = response.content.strip().replace("```json", "").replace("```", "")
            result = json.loads(content)
            raw_candidates = result.get("rewritten_queries")
            if not isinstance(raw_candidates, list):
                raw_candidates = [result.get("rewritten_query", "")]

            search_queries = [query]
            for candidate in raw_candidates:
                if not isinstance(candidate, str):
                    continue
                normalized = candidate.strip()
                if normalized and normalized not in search_queries:
                    search_queries.append(normalized)
                if len(search_queries) == 4:
                    break

            return RewrittenQuery(
                original_query=query,
                rewritten_query=search_queries[1] if len(search_queries) > 1 else query,
                search_keywords=result.get("search_keywords", []),
                search_queries=search_queries,
            )
        except Exception as exc:
            logger.warning(f"多候选查询改写失败，使用原始查询: {exc}")
            return RewrittenQuery(
                original_query=query,
                rewritten_query=query,
                search_keywords=[query],
                search_queries=[query],
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
