"""Prometheus 指标仅使用低基数、非敏感标签。"""
from prometheus_client import Counter, Histogram

QUERY_TOTAL = Counter("lexrag_queries_total", "法律查询总数", ["verification_status", "cache_hit"])
QUERY_LATENCY = Histogram("lexrag_query_latency_seconds", "法律查询耗时", ["cache_hit"])
LAW_UPDATE_TOTAL = Counter("lexrag_law_updates_total", "法规更新事件", ["status"])

def record_query_metrics(*, verification_status: str, cache_hit: str, latency_ms: int) -> None:
    QUERY_TOTAL.labels(verification_status=verification_status, cache_hit=cache_hit).inc()
    QUERY_LATENCY.labels(cache_hit=cache_hit).observe(max(0, latency_ms) / 1000)
