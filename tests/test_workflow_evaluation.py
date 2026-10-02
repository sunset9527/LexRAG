import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.workflow_evaluation import evaluate_workflow_responses  # noqa: E402


def test_workflow_evaluation_reports_only_observable_metrics_and_flags_missing_human_review():
    report = evaluate_workflow_responses(
        [
            {"id": "q1", "relevant_article_ids": ["中华人民共和国民法典第1254条"]},
            {"id": "q2", "relevant_article_ids": ["中华人民共和国民法典第577条"]},
        ],
        {
            "q1": {
                "verification_status": "pass",
                "citations": [
                    {"article_id": "1254", "is_verified": True}
                ],
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
