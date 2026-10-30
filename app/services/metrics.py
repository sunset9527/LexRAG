"""Prometheus 指标仅使用低基数、非敏感标签。"""

from collections.abc import Iterable, Mapping
from typing import Any

from prometheus_client import Counter, Histogram

QUERY_TOTAL = Counter("lexrag_queries_total", "法律查询总数", ["verification_status", "cache_hit"])
QUERY_LATENCY = Histogram("lexrag_query_latency_seconds", "法律查询耗时", ["cache_hit"])
WORKFLOW_NODE_LATENCY = Histogram(
    "lexrag_workflow_node_latency_seconds",
    "法律查询工作流节点耗时",
    ["node", "status"],
)
LAW_UPDATE_TOTAL = Counter("lexrag_law_updates_total", "法规更新事件", ["status"])

_WORKFLOW_NODES = frozenset(
    {
        "planning",
        "knowledge_base_routing",
        "routing",
        "statute_retrieval",
        "case_retrieval",
        "evidence_ledger",
        "answer",
        "citation_verifier",
        "repair",
        "finalize",
        "evidence_insufficient",
    }
)
_WORKFLOW_STATUSES = frozenset({"completed", "degraded", "failed", "skipped"})


def record_query_metrics(
    *,
    verification_status: str,
    cache_hit: str,
    latency_ms: int,
    workflow_trace: Iterable[Mapping[str, Any]] | None = None,
) -> None:
    QUERY_TOTAL.labels(verification_status=verification_status, cache_hit=cache_hit).inc()
    QUERY_LATENCY.labels(cache_hit=cache_hit).observe(max(0, latency_ms) / 1000)
    if cache_hit != "none":
        return
    for event in workflow_trace or ():
        node = event.get("node")
        status = event.get("status")
        duration_ms = event.get("duration_ms")
        if (
            node not in _WORKFLOW_NODES
            or status not in _WORKFLOW_STATUSES
            or isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int | float)
            or duration_ms < 0
        ):
            continue
        WORKFLOW_NODE_LATENCY.labels(node=node, status=status).observe(duration_ms / 1000)
