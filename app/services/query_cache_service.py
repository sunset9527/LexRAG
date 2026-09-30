"""查询结果缓存的服务边界。"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import Any, Mapping, Optional


logger = logging.getLogger(__name__)


class QueryCacheService:
    """封装缓存键、Redis 访问和失效旁路。"""

    def __init__(
        self,
        redis_client: Any,
        *,
        ttl_seconds: int = 3600,
        semantic_threshold: float = 0.9,
    ):
        self.redis_client = redis_client
        self.ttl_seconds = ttl_seconds
        self.semantic_threshold = semantic_threshold

    @staticmethod
    def _normalize_query(query: str) -> str:
        return " ".join(query.split())

    def _exact_key(self, query: str, scope: Mapping[str, Any]) -> str:
        material = {
            "query": self._normalize_query(query),
            "scope": dict(scope),
        }
        digest = hashlib.sha256(
            json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"lexrag:query:v2:{digest}"

    @staticmethod
    def _scope_digest(scope: Mapping[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(dict(scope), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _semantic_key(self, query: str, scope: Mapping[str, Any]) -> str:
        query_digest = hashlib.sha256(self._normalize_query(query).encode("utf-8")).hexdigest()
        return f"lexrag:semantic:v2:{self._scope_digest(scope)}:{query_digest}"

    def get_exact(self, query: str, scope: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        """读取精确命中；Redis 不可用时无声旁路到正常查询。"""
        try:
            raw = self.redis_client.get(self._exact_key(query, scope))
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception as exc:
            logger.warning("查询缓存读取失败，已旁路: %s", exc)
            return None

    def set_exact(self, query: str, scope: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
        """仅缓存已经成功序列化的查询结果；失败不影响主请求。"""
        try:
            self.redis_client.setex(
                self._exact_key(query, scope),
                self.ttl_seconds,
                json.dumps(dict(payload), ensure_ascii=False),
            )
        except Exception as exc:
            logger.warning("查询缓存写入失败，已旁路: %s", exc)

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0

    def set_semantic(
        self,
        query: str,
        scope: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        embedding: list[float],
    ) -> None:
        """保存与精确缓存同作用域的向量候选，供相似问题复用。"""
        try:
            record = {
                "original_query": self._normalize_query(query),
                "embedding": embedding,
                "payload": dict(payload),
            }
            self.redis_client.setex(
                self._semantic_key(query, scope),
                self.ttl_seconds,
                json.dumps(record, ensure_ascii=False),
            )
        except Exception as exc:
            logger.warning("语义查询缓存写入失败，已旁路: %s", exc)

    def get_semantic(
        self,
        query: str,
        scope: Mapping[str, Any],
        *,
        embedding: list[float],
    ) -> Optional[dict[str, Any]]:
        """返回同作用域内阈值以上的最佳近似缓存，失败时旁路。"""
        try:
            prefix = f"lexrag:semantic:v2:{self._scope_digest(scope)}:"
            best: Optional[dict[str, Any]] = None
            for key in self.redis_client.scan_iter(f"{prefix}*"):
                raw = self.redis_client.get(key)
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                record = json.loads(raw)
                similarity = self._cosine_similarity(embedding, record.get("embedding", []))
                if similarity <= self.semantic_threshold:
                    continue
                if best is None or similarity > best["similarity"]:
                    best = {
                        "payload": record["payload"],
                        "original_query": record["original_query"],
                        "similarity": similarity,
                    }
            if best is not None:
                best["similarity"] = round(best["similarity"], 6)
            return best
        except Exception as exc:
            logger.warning("语义查询缓存读取失败，已旁路: %s", exc)
            return None
