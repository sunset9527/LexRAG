import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.evaluate_workflow import build_request_headers, request_with_retries
from src.evaluation.workflow_evaluation import evaluate_workflow_responses  # noqa: E402


def test_workflow_evaluation_headers_include_bearer_token_without_replacing_llm_key():
    """真实 /query 评测必须同时携带 LLM Key 与当前 API 所需的 JWT。"""
    headers = build_request_headers(
        api_key="test-llm-key",
        bearer_token="test-jwt-token",
        base_url="https://api.example.com/v1",
        model="test-model",
    )

    assert headers == {
        "X-API-Key": "test-llm-key",
        "X-Base-URL": "https://api.example.com/v1",
        "X-Model": "test-model",
        "Authorization": "Bearer test-jwt-token",
    }


def test_request_with_retries_recovers_from_a_transient_server_error():
    attempts = 0

    def request() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            response = httpx.Response(500, request=httpx.Request("POST", "https://api.test"))
            raise httpx.HTTPStatusError("temporary failure", request=response.request, response=response)
        return "ok"

    result, observed_attempts = request_with_retries(
        request, max_attempts=2, sleep_seconds=0
    )

    assert result == "ok"
    assert observed_attempts == 2


def test_workflow_evaluation_reports_only_observable_metrics_and_flags_missing_human_review():
    report = evaluate_workflow_responses(
        [
            {"id": "q1", "relevant_article_ids": ["中华人民共和国民法典第1254条"]},
            {"id": "q2", "relevant_article_ids": ["中华人民共和国民法典第577条"]},
        ],
        {
            "q1": {
                "verification_status": "pass",
                "citations": [{"article_id": "1254", "is_verified": True}],
                "metadata": {"verification_attempts": 1},
                "latency_ms": 120.0,
            },
            "q2": {
                "verification_status": "fail",
                "citations": [],
                "metadata": {"verification_attempts": 1},
                "latency_ms": 80.0,
            },
        },
    )

    assert report["sample_count"] == 2
    assert report["metrics"]["verification_pass_rate"] == 0.5
    assert report["metrics"]["expected_citation_coverage"] == 0.5
    assert report["metrics"]["repair_trigger_rate"] == 1.0
    assert report["metrics"]["repair_success_rate"] == 0.5
    assert report["metrics"]["cache_hit_count"] == 0
    assert report["human_review"]["assertion_support_rate"] is None
    assert report["human_review"]["missing_review_ids"] == ["q1", "q2"]
