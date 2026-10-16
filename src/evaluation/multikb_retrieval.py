"""按知识库路由的检索评测运行辅助。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from .retrieval_evaluation import evaluate_labels_by_knowledge_base

RetrievalMode = Literal["vector", "bm25", "rrf"]


def _unique_article_ids(article_ids: list[str], *, top_k: int) -> list[str]:
    """保留首次出现的有效法条 ID，避免同一法条的分块重复占位。"""
    unique_ids: list[str] = []
    seen_ids: set[str] = set()
    for article_id in article_ids:
        if not article_id or article_id in seen_ids:
            continue
        seen_ids.add(article_id)
        unique_ids.append(article_id)
        if len(unique_ids) >= top_k:
            break
    return unique_ids


def collect_ranked_article_ids(
    retriever: Any,
    query: str,
    *,
    mode: RetrievalMode,
    top_k: int,
    law_name: str | None = None,
) -> list[str]:
    """以指定路线检索并规范化为条文 ID 排序。"""
    if mode == "vector":
        results = retriever.retrieve(query, top_k=top_k)
        return _unique_article_ids([result.article_id for result in results], top_k=top_k)

    if mode == "bm25":
        retriever._ensure_optimization_data()
        bm25 = retriever._bm25
        if bm25 is None:
            raise RuntimeError("BM25 索引构建失败，无法完成评测")
        results = bm25.retrieve(query, top_k=top_k * 5)
        return _unique_article_ids(
            [str((result.metadata or {}).get("article_id", "")) for result in results],
            top_k=top_k,
        )

    if mode == "rrf":
        if not law_name:
            raise ValueError("RRF 评测缺少知识库对应的法律名称")
        results, _, _ = retriever.retrieve_optimized(query, top_k=top_k, law_name=law_name)
        return _unique_article_ids([result.article_id for result in results], top_k=top_k)

    raise ValueError(f"不支持的检索路线: {mode}")


def evaluate_multi_knowledge_base(
    labels: list[dict[str, Any]],
    retriever_for_slug: Callable[[str], Any],
    *,
    mode: RetrievalMode,
    top_k: int,
    law_name_for_slug: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """按样本所属知识库取检索器，并计算总体及分库指标。"""

    def retrieve(label: dict[str, Any]) -> list[str]:
        slug = label["knowledge_base_slug"]
        retriever = retriever_for_slug(slug)
        law_name = law_name_for_slug(slug) if mode == "rrf" and law_name_for_slug else None
        return collect_ranked_article_ids(
            retriever,
            label["query"],
            mode=mode,
            top_k=top_k,
            law_name=law_name,
        )

    return evaluate_labels_by_knowledge_base(labels, retrieve, top_k=top_k)
