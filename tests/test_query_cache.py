"""查询缓存服务的最小契约测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import app.services as services


def test_query_cache_service_is_exposed_as_a_separate_service():
    """缓存能力必须有独立服务边界，不能散落在 API 路由中。"""
    assert hasattr(services, "QueryCacheService")


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.setex_calls = []

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.values[key] = value

    def scan_iter(self, match):
        prefix = match.removesuffix("*")
        return [key for key in self.values if key.startswith(prefix)]


def test_exact_cache_is_scoped_by_user_knowledge_base_and_model_config():
    """同问题仅能在完全相同的用户与运行时配置中复用回答。"""
    redis_client = FakeRedis()
    service = services.QueryCacheService(redis_client, ttl_seconds=3600)
    scope = {
        "user_id": 7,
        "knowledge_base_slug": "civil-code",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "prompt_version": "v1",
        "retrieval_version": "v2.0",
    }
    payload = {"answer": "民法典第17条规定……", "citations": []}

    assert service.get_exact(" 成年人的年龄规定 ", scope) is None
    service.set_exact(" 成年人的年龄规定 ", scope, payload)

    assert redis_client.setex_calls[0][1] == 3600
    assert service.get_exact("成年人的年龄规定", scope) == payload
    assert service.get_exact("成年人的年龄规定", {**scope, "user_id": 8}) is None
    assert service.get_exact("成年人的年龄规定", {**scope, "model": "qwen-plus"}) is None


def test_semantic_cache_returns_original_question_only_above_threshold():
    """语义缓存必须同作用域、超过阈值，并返回其命中的原问题与相似度。"""
    service = services.QueryCacheService(FakeRedis(), semantic_threshold=0.9)
    scope = {"user_id": 7, "knowledge_base_slug": "civil-code", "model": "deepseek-chat"}
    service.set_semantic(
        "成年人多大",
        scope,
        {"answer": "年满十八周岁的自然人为成年人。"},
        embedding=[1.0, 0.0],
    )

    hit = service.get_semantic("成年人的年龄规定", scope, embedding=[0.95, 0.05])

    assert hit == {
        "payload": {"answer": "年满十八周岁的自然人为成年人。"},
        "original_query": "成年人多大",
        "similarity": 0.998618,
    }
    assert service.get_semantic("成年人的年龄规定", scope, embedding=[0.5, 0.5]) is None
    assert service.get_semantic("成年人的年龄规定", {**scope, "user_id": 8}, embedding=[1.0, 0.0]) is None
