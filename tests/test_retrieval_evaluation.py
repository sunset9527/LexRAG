"""检索评测 CLI 的数据契约与指标回归测试。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.evaluation.retrieval_evaluation import (
    EvaluationDatasetError,
    evaluate_labels,
    evaluate_labels_by_knowledge_base,
    load_labels,
)

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


def test_evaluation_cli_documents_live_collection_mode():
    """评测 CLI 必须提供直接读取 Chroma collection 的模式。"""
    completed = subprocess.run(
        [sys.executable, "scripts/evaluate_retrieval.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--live-collection" in completed.stdout


def test_load_labels_rejects_pending_samples_for_official_evaluation(tmp_path):
    """正式评测只能使用已由人工核验的样本，不能混入待审草稿。"""
    dataset = tmp_path / "labels.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "labor-draft-001",
                "query": "劳动关系何时建立？",
                "knowledge_base_slug": "labor-contract-law",
                "relevant_article_ids": ["中华人民共和国劳动合同法第7条"],
                "source": "本地法条原文候选",
                "reviewed_at": "",
                "review_status": "pending",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(EvaluationDatasetError, match="人工核验"):
        load_labels(dataset, require_reviewed=True)


def test_grouped_evaluation_reports_overall_and_per_knowledge_base():
    """跨库指标必须保留分库明细，不能只用总分掩盖单库短板。"""
    labels = [
        {
            "id": "civil-001",
            "query": "成年人的年龄规定",
            "knowledge_base_slug": "civil-code",
            "relevant_article_ids": ["中华人民共和国民法典第17条"],
            "source": "人工核验",
            "reviewed_at": "2026-10-05",
        },
        {
            "id": "criminal-001",
            "query": "正当防卫的规定",
            "knowledge_base_slug": "criminal-law",
            "relevant_article_ids": ["中华人民共和国刑法第20条"],
            "source": "人工核验",
            "reviewed_at": "2026-10-05",
        },
    ]

    report = evaluate_labels_by_knowledge_base(
        labels,
        lambda label: (
            ["中华人民共和国民法典第17条"]
            if label["knowledge_base_slug"] == "civil-code"
            else ["中华人民共和国刑法第1条"]
        ),
        top_k=5,
    )

    assert report["overall"]["sample_count"] == 2
    assert report["overall"]["metrics"]["recall_at_k"] == 0.5
    assert report["by_knowledge_base"]["civil-code"]["sample_count"] == 1
    assert report["by_knowledge_base"]["civil-code"]["metrics"]["mrr_at_k"] == 1.0
    assert report["by_knowledge_base"]["criminal-law"]["metrics"]["recall_at_k"] == 0.0


def test_evaluation_deduplicates_repeated_article_candidates_before_scoring():
    """同一法条的多个分块不能重复占据排序位置或抬高 NDCG。"""
    labels = [
        {
            "id": "civil-duplicate",
            "query": "成年人年龄",
            "knowledge_base_slug": "civil-code",
            "relevant_article_ids": ["中华人民共和国民法典第17条"],
            "source": "人工核验",
            "reviewed_at": "2026-10-06",
        }
    ]

    report = evaluate_labels(
        labels,
        lambda _label: [
            "中华人民共和国民法典第17条",
            "中华人民共和国民法典第17条",
            "中华人民共和国民法典第18条",
        ],
        top_k=3,
    )

    assert report["metrics"] == {
        "recall_at_k": 1.0,
        "mrr_at_k": 1.0,
        "ndcg_at_k": 1.0,
    }
    assert report["items"][0]["ranked_article_ids"] == [
        "中华人民共和国民法典第17条",
        "中华人民共和国民法典第18条",
    ]


def test_evaluation_normalizes_equivalent_article_subsection_notation():
    labels = [
        {
            "id": "criminal-17-1",
            "query": "第十七条之一",
            "knowledge_base_slug": "criminal-law",
            "relevant_article_ids": ["中华人民共和国刑法第17-1条"],
            "source": "人工核验",
            "reviewed_at": "2026-10-25",
        }
    ]

    report = evaluate_labels(
        labels,
        lambda _label: ["中华人民共和国刑法第17条之1"],
        top_k=5,
    )

    assert report["metrics"]["recall_at_k"] == 1.0
    assert report["items"][0]["ranked_article_ids"] == ["中华人民共和国刑法第17-1条"]
