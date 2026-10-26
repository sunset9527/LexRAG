"""
法律条文检索器

基于Chroma向量检索+元数据过滤
支持：
- 向量相似度检索
- 元数据过滤（法律名称、章节、法条范围）
- 重排序
- 引用关系增强
- 优化模式（v2.1）：BM25+向量加权RRF融合 + 精确条号置顶 + 条款组聚合
  + 引用图增强召回 + 检索/生成字段分离（轻量摘要控制上下文）
  （对应滴普 HR 建议「召回颗粒度 + 重排 + 上下文瘦身」）
"""

import logging
from dataclasses import dataclass, replace
from typing import Any

# v1.7: 使用 Langfuse 可观测工厂
from app.services.langfuse_helper import create_llm

from . import retrieval_optimizer as ropt
from .bm25_retriever import BM25Retriever
from .chroma_collection import ChromaCollectionGateway
from .intent_router import IntentType, QueryIntent

logger = logging.getLogger(__name__)


def _unit_interval(value: float) -> float:
    """将可比较的相关性显式限制到 ``[0, 1]``。"""
    return max(0.0, min(1.0, float(value)))


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
    section: str | None
    score: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
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
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        enable_optimization: bool = True,
    ):
        """
        初始化检索器

        Args:
            vectorstore: Chroma向量存储
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
            enable_optimization: 是否启用优化模式（BM25+向量加权RRF + 条号置顶 + 条款组聚合）
        """
        self.vectorstore = vectorstore
        self.enable_optimization = enable_optimization
        self._bm25: BM25Retriever | None = None
        self._chapter_map: dict[str, set[int]] | None = None
        self._article_lookup: dict[int, str] | None = None
        self._references_map: dict[str, set[str]] | None = None
        self.llm = create_llm(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.0,
        )

    def _ensure_optimization_data(self):
        """懒加载：从向量库拉全部文档构建 BM25 索引 + 章节映射 + 条文内容映射"""
        if self._bm25 is not None:
            return
        try:
            all_data = ChromaCollectionGateway(self.vectorstore).get(
                include=["documents", "metadatas"]
            )
            metadatas = all_data["metadatas"]
            docs_bm25 = [
                {
                    "id": metadatas[i].get("chunk_id", str(i)),
                    "content": all_data["documents"][i],
                    "metadata": metadatas[i],
                }
                for i in range(len(all_data["documents"]))
            ]
            self._bm25 = BM25Retriever()
            self._bm25.build_index(docs_bm25)
            self._chapter_map = ropt.build_chapter_article_map(metadatas)
            # 引用图边集合：条号 -> 被引用条号（供 expand_by_references 做引用扩展）
            self._references_map = ropt.build_references_map(metadatas)
            self._article_lookup = {}
            import re as _re

            for i, md in enumerate(metadatas):
                an = str(md.get("article_number", ""))
                if an.isdigit() and int(an) not in self._article_lookup:
                    raw = md.get("full_article_content") or all_data["documents"][i]
                    # page_content 结构：条文内容 + 【完整法条上下文】{full}
                    # 只提取完整法条正文，避免上下文重复膨胀（上下文瘦身）
                    m = _re.search(r"【完整法条上下文】\s*(.*)$", raw, _re.S)
                    content = m.group(1).strip() if m else raw
                    if content:
                        self._article_lookup[int(an)] = content
            logger.info(
                f"优化数据就绪：BM25 {len(docs_bm25)} docs, "
                f"{len(self._chapter_map)} 章节, {len(self._article_lookup)} 条文, "
                f"{len(self._references_map)} 条带引用边"
            )
        except Exception as exc:
            logger.warning("优化数据构建失败 error_type=%s", type(exc).__name__)
            self.enable_optimization = False

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        law_name: str | None = None,
        chapter: str | None = None,
        article_range: tuple | None = None,
        intent: QueryIntent | None = None,
    ) -> list[RetrievalResult]:
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

        retrieval_query = ropt.expand_legal_aliases(query)

        # 执行检索
        try:
            if hasattr(self.vectorstore, "similarity_search_with_relevance_scores"):
                if filter_dict:
                    results = self.vectorstore.similarity_search_with_relevance_scores(
                        retrieval_query, k=top_k * 2, filter=filter_dict
                    )
                else:
                    results = self.vectorstore.similarity_search_with_relevance_scores(
                        retrieval_query, k=top_k * 2
                    )
            elif filter_dict:
                results = [
                    (doc, 1.0 / (1.0 + float(distance)))
                    for doc, distance in self.vectorstore.similarity_search_with_score(
                        retrieval_query, k=top_k * 2, filter=filter_dict
                    )
                ]
            else:
                results = [
                    (doc, 1.0 / (1.0 + float(distance)))
                    for doc, distance in self.vectorstore.similarity_search_with_score(
                        retrieval_query, k=top_k * 2
                    )
                ]
        except Exception as exc:
            logger.error("向量检索失败 error_type=%s", type(exc).__name__)
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
                score=float(score),
                metadata={
                    **metadata,
                    "score_type": "vector_relevance",
                    "score_direction": "higher_is_more_relevant",
                    "normalized_score": _unit_interval(float(score)),
                    "query_expanded_with_aliases": retrieval_query != query,
                },
            )

            retrieval_results.append(result)

            if len(retrieval_results) >= top_k:
                break

        # 如果启用了意图分析，进行重排序
        if intent and intent.intent_type == IntentType.CASE_QUERY:
            retrieval_results = self._rerank_for_case_query(retrieval_results, query)

        return retrieval_results

    def retrieve_multi_query(
        self,
        queries: list[str],
        *,
        hyde_query: str | None = None,
        top_k: int = 5,
        **retrieve_kwargs: Any,
    ) -> list[RetrievalResult]:
        """对原问题、改写候选和可选 HyDE 文本分别召回后做 RRF 融合。"""
        retrieval_queries: list[str] = []
        for query in [*queries, hyde_query]:
            normalized = query.strip() if isinstance(query, str) else ""
            if normalized and normalized not in retrieval_queries:
                retrieval_queries.append(normalized)
        if not retrieval_queries:
            return []

        fused: dict[str, tuple[float, RetrievalResult]] = {}
        for query in retrieval_queries:
            if getattr(self, "enable_optimization", False):
                results, _, _ = self.retrieve_optimized(query, top_k=top_k, **retrieve_kwargs)
            else:
                results = self.retrieve(query, top_k=top_k, **retrieve_kwargs)
            for rank, result in enumerate(results):
                score, first_result = fused.get(result.article_id, (0.0, result))
                fused[result.article_id] = (score + 1 / (60 + rank), first_result)

        ordered = sorted(fused.values(), key=lambda item: (-item[0], item[1].article_id))[:top_k]
        normalization_denominator = ordered[0][0] if ordered else 1.0
        return [
            replace(
                result,
                score=score,
                metadata={
                    **result.metadata,
                    "retrieval_queries": retrieval_queries,
                    "score_type": "multi_query_rrf",
                    "score_direction": "higher_is_more_relevant",
                    "normalized_score": _unit_interval(score / normalization_denominator),
                },
            )
            for score, result in ordered
        ]

    def retrieve_optimized(
        self,
        query: str,
        top_k: int = 5,
        law_name: str | None = None,
        intent: QueryIntent | None = None,
        context_max_chars: int = 500,
    ) -> tuple[list[RetrievalResult], str, list[str]]:
        """
        优化检索：BM25 + 向量 加权RRF融合 -> 精确条号置顶 -> 章节窗口聚合
        + 引用图增强召回 -> 生成上下文轻量摘要（检索/生成字段分离）

        Args:
            context_max_chars: 生成上下文单条条文最大字符数（轻量摘要上限，
                超过则保留首尾、省略中间；传 None/极大值 = 不压缩，保留全文）

        Returns:
            (results, grouped_context, top_article_numbers)
            - results: top_k 条 RetrievalResult（已按融合分排序、按条号去重）
            - grouped_context: 聚合后章节窗口 + 引用扩展条文上下文（生成阶段用，
              引用扩展的条文标注「·引用相关」，每条内容已过轻量摘要）
            - top_article_numbers: top_k 命中条号列表
        """
        self._ensure_optimization_data()
        if not self.enable_optimization or self._bm25 is None:
            results = self.retrieve(query, top_k=top_k, law_name=law_name, intent=intent)
            return results, "", [r.article_number for r in results]

        retrieval_query = ropt.expand_legal_aliases(query)

        # 1) 两路召回
        bm25_results = self._bm25.retrieve(retrieval_query, top_k=top_k * 2)
        vec_results = self.vectorstore.similarity_search(retrieval_query, k=top_k * 2)

        # 2) 加权 RRF 融合
        wb, wv = ropt.rrf_weights(query)
        score_map: dict[str, float] = {}
        info: dict[str, dict[str, Any]] = {}
        for rank, r in enumerate(bm25_results):
            key = str((r.metadata or {}).get("chunk_id", "")) or r.doc_id
            score_map[key] = score_map.get(key, 0) + wb / (60 + rank)
            if key not in info:
                md = r.metadata or {}
                info[key] = {
                    "article": str(md.get("article_number", "?")),
                    "chapter": str(md.get("chapter", "")),
                    "content": r.content or "",
                    "full": md.get("full_article_content", r.content or ""),
                }
        for rank, d in enumerate(vec_results):
            md = d.metadata or {}
            key = str(md.get("chunk_id", ""))
            score_map[key] = score_map.get(key, 0) + wv / (60 + rank)
            if key not in info:
                info[key] = {
                    "article": str(md.get("article_number", "?")),
                    "chapter": str(md.get("chapter", "")),
                    "content": d.page_content or "",
                    "full": md.get("full_article_content", d.page_content or ""),
                }
        ranked = sorted(score_map.items(), key=lambda x: -x[1])

        # 3) 精确条号置顶
        ranked = ropt.exact_article_boost(ranked, info, query)
        normalization_denominator = max((score for _, score in ranked), default=1.0)

        # 4) 按条号去重，构建 RetrievalResult
        seen: set[str] = set()
        results: list[RetrievalResult] = []
        top_articles: list[str] = []
        for key, _score in ranked:
            val = info[key]
            art = val["article"]
            if art in seen or art == "?":
                continue
            seen.add(art)
            top_articles.append(art)
            results.append(
                RetrievalResult(
                    chunk_id=key,
                    article_id=f"{law_name or '中华人民共和国民法典'}第{art}条",
                    article_number=art,
                    law_name=law_name or "",
                    content=val["content"],
                    full_content=val["full"],
                    chapter=val["chapter"],
                    section=None,
                    score=_score,
                    metadata={
                        "article_number": art,
                        "chapter": val["chapter"],
                        "score_type": "rrf",
                        "score_direction": "higher_is_more_relevant",
                        "normalized_score": _unit_interval(_score / normalization_denominator),
                        "query_expanded_with_aliases": retrieval_query != query,
                    },
                )
            )
            if len(results) >= top_k:
                break

        # 5) 章节窗口聚合 + 引用图增强召回（top_k*2 命中条号 -> 组上下文）
        grouped_context = ""
        if self._chapter_map and self._article_lookup:
            top_hits = [a for a in top_articles] + [
                info[k]["article"]
                for k, _ in ranked[: top_k * 2]
                if info[k]["article"] not in top_articles
            ]
            # 5a) 章节窗口聚合：命中条号 -> 所在章节 ±2 条窗口（相邻条文语义相关）
            grouped = ropt.chapter_window_aggregate(top_hits, self._chapter_map)
            # 5b) 引用图增强召回：沿 referenced_articles 引用边 BFS 扩展 1 跳，
            #     补充被命中条文引用 / 引用命中条文的关联条文（如 第402条引用第395条）
            expanded = ropt.expand_by_references(
                top_hits,
                self._article_lookup,
                references_map=self._references_map,
                max_hops=1,
                max_add=3,
            )
            grouped = grouped | expanded
            # 5c) 生成字段分离：每条条文先过轻量摘要（≤ context_max_chars 字）再拼接，
            #     检索用全文命中、生成用摘要，控制生成上下文长度（上下文瘦身）
            grouped_context = ropt.format_grouped_context(
                grouped,
                self._article_lookup,
                law_name or "中华人民共和国民法典",
                max_chars_per_article=context_max_chars,
                expanded_articles=expanded,
            )

        return results, grouped_context, top_articles

    def retrieve_by_article_number(
        self, article_number: str, law_name: str | None = None
    ) -> RetrievalResult | None:
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
                doc_content = results["documents"][0]
                return RetrievalResult(
                    chunk_id=metadata.get("chunk_id", ""),
                    article_id=metadata.get("article_id", ""),
                    article_number=metadata.get("article_number", ""),
                    law_name=metadata.get("law_name", ""),
                    content=doc_content,
                    # metadata 无 full_article_content 时回退到文档内容（否则自校验拿到空法条原文）
                    full_content=metadata.get("full_article_content", doc_content),
                    chapter=metadata.get("chapter", ""),
                    section=metadata.get("section", ""),
                    score=1.0,
                    metadata={
                        **metadata,
                        "score_type": "exact_article",
                        "score_direction": "higher_is_more_relevant",
                        "normalized_score": 1.0,
                    },
                )
        except Exception as exc:
            logger.error("精确检索失败 error_type=%s", type(exc).__name__)

        return None

    def retrieve_by_references(self, article_ids: list[str]) -> list[RetrievalResult]:
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

            match = re.search(r"第(\d+)条", article_id)
            if match:
                article_num = match.group(1)
                result = self.retrieve_by_article_number(article_num)
                if result:
                    results.append(result)

        return results

    def _rerank_for_case_query(
        self, results: list[RetrievalResult], query: str
    ) -> list[RetrievalResult]:
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
        self, results: list[RetrievalResult], max_length: int = 4000
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
