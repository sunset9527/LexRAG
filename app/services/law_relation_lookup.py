"""法规 Chroma 集合的精确条号查询适配器。"""

from collections.abc import Callable
from typing import Any


def build_collection_law_lookup(
    collection: Any,
) -> Callable[[str, str], list[dict[str, str]]]:
    """将 Chroma 的法规元数据读取封装为关系服务需要的目标列表。"""

    def lookup(law_name: str, article_number: str) -> list[dict[str, str]]:
        result = collection.get(
            where={
                "$and": [
                    {"law_name": law_name},
                    {"article_number": str(article_number)},
                ]
            },
            include=["metadatas"],
        )
        return [
            {
                "target_id": str(metadata.get("article_id") or chunk_id),
                "target_type": "law_article",
            }
            for chunk_id, metadata in zip(
                result.get("ids", []), result.get("metadatas", []), strict=True
            )
            if metadata is not None and (metadata.get("article_id") or chunk_id)
        ]

    return lookup


def build_lazy_law_lookup(
    indexer_factory: Callable[[], Any],
) -> Callable[[str, str], list[dict[str, str]]]:
    """首次真正引用法条时才打开法规 Chroma 集合，避免普通文档额外开销。"""
    lookup: Callable[[str, str], list[dict[str, str]]] | None = None

    def lazy_lookup(law_name: str, article_number: str) -> list[dict[str, str]]:
        nonlocal lookup
        if lookup is None:
            indexer = indexer_factory()
            lookup = build_collection_law_lookup(indexer.vectorstore._collection)
        return lookup(law_name, article_number)

    return lazy_lookup
