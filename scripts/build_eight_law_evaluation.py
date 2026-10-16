"""将经项目负责人确认的候选样本组装为正式 100 条评测集。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.eight_law_dataset import build_approved_eight_law_dataset
from src.evaluation.retrieval_evaluation import EvaluationDatasetError, load_labels


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """以 UTF-8 JSONL 格式写出正式评测数据集。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="组装八部法律正式 100 条检索评测集")
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--reviewed-at", required=True, help="项目负责人完成逐条核验的日期")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        baseline = load_labels(args.baseline)
        draft = load_labels(args.draft)
        official = build_approved_eight_law_dataset(
            baseline,
            draft,
            reviewed_at=args.reviewed_at,
        )
        write_jsonl(args.output, official)
        return 0
    except (OSError, EvaluationDatasetError, ValueError, json.JSONDecodeError) as exc:
        print(f"构建失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
