"""检索评测 CLI 的数据契约与指标回归测试。"""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_evaluation_cli_reports_metrics_for_human_reviewed_labels(tmp_path):
    """有效人工标注经确定性候选结果可产出可审计的三项指标。"""
    dataset = tmp_path / "labels.jsonl"
    dataset.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "civil-001",
                        "query": "成年人的年龄规定",
                        "knowledge_base_slug": "civil-code",
                        "relevant_article_ids": ["中华人民共和国民法典第17条"],
                        "source": "人工核验",
                        "reviewed_at": "2026-09-30",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "id": "civil-002",
                        "query": "未成年人的年龄规定",
                        "knowledge_base_slug": "civil-code",
                        "relevant_article_ids": ["中华人民共和国民法典第18条"],
                        "source": "人工核验",
                        "reviewed_at": "2026-09-30",
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps(
            {
                "civil-001": ["中华人民共和国民法典第17条", "中华人民共和国民法典第18条"],
                "civil-002": ["中华人民共和国民法典第17条", "中华人民共和国民法典第18条"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_retrieval.py",
            "--dataset",
            str(dataset),
            "--candidates",
            str(candidates),
            "--top-k",
            "2",
            "--output",
            str(report_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["sample_count"] == 2
    assert report["metrics"] == {
        "recall_at_k": 1.0,
        "mrr_at_k": 0.75,
        "ndcg_at_k": 0.815465,
    }
    assert report["items"][1]["ranked_article_ids"] == [
        "中华人民共和国民法典第17条",
        "中华人民共和国民法典第18条",
    ]


def test_evaluation_cli_rejects_a_label_without_retrieval_candidates(tmp_path):
    """候选缺失是检索执行失败，不能被伪装成 0 分评测。"""
    dataset = tmp_path / "labels.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "civil-missing",
                "query": "成年人的年龄规定",
                "knowledge_base_slug": "civil-code",
                "relevant_article_ids": ["中华人民共和国民法典第17条"],
                "source": "人工核验",
                "reviewed_at": "2026-09-30",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    candidates = tmp_path / "candidates.json"
    candidates.write_text("{}", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_retrieval.py",
            "--dataset",
            str(dataset),
            "--candidates",
            str(candidates),
            "--top-k",
            "2",
            "--output",
            str(tmp_path / "report.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "没有候选" in completed.stderr
