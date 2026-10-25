"""对阶段 5 跨法规库检索样本运行 vector、BM25 或 RRF 回归。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.multikb_retrieval import evaluate_multi_knowledge_base
from src.evaluation.retrieval_evaluation import EvaluationDatasetError, load_labels
from src.ingestion.indexer import LawIndexer
from src.retrieval.law_retriever import LawRetriever


def _parse_collection(value: str) -> tuple[str, str]:
    try:
        slug, collection_name = value.split("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("collection 格式必须为 slug=collection_name") from exc
    if not slug or not collection_name:
        raise argparse.ArgumentTypeError("collection 格式必须为 slug=collection_name")
    return slug, collection_name


def main() -> int:
    parser = argparse.ArgumentParser(description="按知识库路由运行法规检索回归")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--collection", type=_parse_collection, action="append", required=True)
    parser.add_argument("--mode", choices=("vector", "bm25", "rrf"), required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--persist-directory", type=Path, default=Path("data/chroma_db"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        labels = load_labels(args.dataset, require_reviewed=False)
        collections = dict(args.collection)
        missing = sorted({label["knowledge_base_slug"] for label in labels} - set(collections))
        if missing:
            raise EvaluationDatasetError(f"缺少知识库 collection 映射: {', '.join(missing)}")
        retrievers = {
            slug: LawRetriever(
                vectorstore=LawIndexer(
                    persist_directory=str(args.persist_directory), collection_name=collection_name
                ).vectorstore
            )
            for slug, collection_name in collections.items()
        }
        law_names = {label["knowledge_base_slug"]: label.get("law_name", "") for label in labels}
        report = evaluate_multi_knowledge_base(
            labels,
            lambda slug: retrievers[slug],
            mode=args.mode,
            top_k=args.top_k,
            law_name_for_slug=lambda slug: law_names[slug],
        )
        report.update(
            {
                "mode": args.mode,
                "dataset": str(args.dataset),
                "evaluation_tier": "engineering_regression",
                "formal_metric": False,
                "notice": "样本待逐条人工审核；本报告仅用于检索回归，不能作为对外效果指标。",
            }
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except (EvaluationDatasetError, OSError, ValueError) as exc:
        print(f"评测失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
