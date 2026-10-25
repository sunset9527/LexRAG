"""阶段 6 查询性能指标契约。"""

import api
from app.services import metrics


class FakeCounter:
    def __init__(self):
        self.calls = []

    def labels(self, **labels):
        self.calls.append(labels)
        return self

    def inc(self):
        return None


class FakeHistogram:
    def __init__(self):
        self.calls = []

    def labels(self, **labels):
        self.calls.append({"labels": labels})
        return self

    def observe(self, value):
        self.calls[-1]["value"] = value


def test_query_metrics_records_only_safe_workflow_node_durations(monkeypatch):
    query_total = FakeCounter()
    query_latency = FakeHistogram()
    node_latency = FakeHistogram()
    monkeypatch.setattr(metrics, "QUERY_TOTAL", query_total)
    monkeypatch.setattr(metrics, "QUERY_LATENCY", query_latency)
    monkeypatch.setattr(metrics, "WORKFLOW_NODE_LATENCY", node_latency)

    metrics.record_query_metrics(
        verification_status="pass",
        cache_hit="none",
        latency_ms=500,
        workflow_trace=[
            {"node": "planning", "status": "completed", "duration_ms": 125},
            {"node": "untrusted-label", "status": "completed", "duration_ms": 10},
            {"node": "routing", "status": "unknown", "duration_ms": 10},
            {"node": "answer", "status": "completed", "duration_ms": -1},
        ],
    )

    assert query_total.calls == [{"verification_status": "pass", "cache_hit": "none"}]
    assert query_latency.calls == [{"labels": {"cache_hit": "none"}, "value": 0.5}]
    assert node_latency.calls == [
        {
            "labels": {"node": "planning", "status": "completed"},
            "value": 0.125,
        }
    ]


def test_cached_result_does_not_reobserve_historical_workflow_trace(monkeypatch):
    monkeypatch.setattr(metrics, "QUERY_TOTAL", FakeCounter())
    monkeypatch.setattr(metrics, "QUERY_LATENCY", FakeHistogram())
    node_latency = FakeHistogram()
    monkeypatch.setattr(metrics, "WORKFLOW_NODE_LATENCY", node_latency)

    metrics.record_query_metrics(
        verification_status="pass",
        cache_hit="exact",
        latency_ms=5,
        workflow_trace=[{"node": "answer", "status": "completed", "duration_ms": 300}],
    )

    assert node_latency.calls == []


def test_query_observability_passes_the_workflow_trace_to_metrics(monkeypatch):
    captured = {}
    monkeypatch.setattr(api, "components", {})
    monkeypatch.setattr(api, "record_query_metrics", lambda **kwargs: captured.update(kwargs))

    api.record_query_observability(
        event_id="request-123",
        organization_id=9,
        current_user_id=7,
        question="成年人多大",
        answer="年满十八周岁的自然人为成年人。",
        verification_status="pass",
        metadata={"workflow_trace": [{"node": "answer", "duration_ms": 1}]},
        latency_ms=2,
    )

    assert captured["workflow_trace"] == [{"node": "answer", "duration_ms": 1}]
