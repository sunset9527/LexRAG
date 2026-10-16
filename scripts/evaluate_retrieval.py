"""对人工标注的法律检索集计算可复现指标。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.retrieval_evaluation import EvaluationDatasetError, evaluate_labels, load_labels


def main() -> int:
    parser = argparse.ArgumentParser(description="计算检索 Recall@K、MRR@K 和 NDCG@K")
    parser.add_argument("--dataset", required=True, type=Path, help="人工核验的 JSONL 标注集")
    input_mode = parser.add_mutually_exclusive_group(required=True)
    input_mode.add_argument("--candidates", type=Path, help="按样本 ID 保存的候选法条 JSON")
    input_mode.add_argument("--live-collection", help="直接读取的 Chroma collection 名称")
    parser.add_argument(
        "--persist-directory", type=Path, default=Path("data/chroma_db"), help="Chroma 持久化目录"
    )
    parser.add_argument("--top-k", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        labels = load_labels(args.dataset)
        if args.candidates:
            candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
            if not isinstance(candidates, dict):
                raise EvaluationDatasetError("候选结果必须是以样本 ID 为键的 JSON 对象")

            def retrieve(label: dict) -> list[str]:
                if label["id"] not in candidates:
                    raise EvaluationDatasetError(f"样本 {label['id']} 没有候选法条，无法完成评测")
                ranked = candidates[label["id"]]
                if not isinstance(ranked, list) or not all(
                    isinstance(value, str) for value in ranked
                ):
                    raise EvaluationDatasetError(f"样本 {label['id']} 的候选法条格式无效")
                return ranked
        else:
            from src.ingestion.indexer import LawIndexer
            from src.retrieval.law_retriever import LawRetriever

            indexer = LawIndexer(
                persist_directory=str(args.persist_directory),
                collection_name=args.live_collection,
            )
            retriever = LawRetriever(vectorstore=indexer.vectorstore)

            def retrieve(label: dict) -> list[str]:
                return [
                    result.article_id
                    for result in retriever.retrieve(label["query"], top_k=args.top_k)
                ]

        report = evaluate_labels(labels, retrieve, top_k=args.top_k)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except (OSError, EvaluationDatasetError, ValueError, json.JSONDecodeError) as exc:
        print(f"评测失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
