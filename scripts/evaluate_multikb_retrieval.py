"""在多个法律知识库上运行经人工核验的检索评测。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.evaluation.multikb_retrieval import evaluate_multi_knowledge_base
from src.evaluation.retrieval_evaluation import EvaluationDatasetError, load_labels


def default_collection_name(slug: str) -> str:
    """知识库 slug 到项目默认 Chroma collection 名称。"""
    return f"kb_{slug.replace('-', '_')}"


def main() -> int:
    parser = argparse.ArgumentParser(description="按知识库路由，评测向量、BM25 或 RRF 检索")
    parser.add_argument("--dataset", required=True, type=Path, help="全部人工核验的 JSONL 数据集")
    parser.add_argument(
        "--mode", required=True, choices=["vector", "bm25", "rrf"], help="待评测的检索路线"
    )
    parser.add_argument("--top-k", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--persist-directory", type=Path, default=Path("data/chroma_db"))
    args = parser.parse_args()

    try:
        labels = load_labels(args.dataset, require_reviewed=True)
        from src.ingestion.indexer import LawIndexer
        from src.retrieval.law_retriever import LawRetriever

        retrievers: dict[str, LawRetriever] = {}

        def retriever_for_slug(slug: str) -> LawRetriever:
            if slug not in retrievers:
                indexer = LawIndexer(
                    persist_directory=str(args.persist_directory),
                    collection_name=default_collection_name(slug),
                )
                retrievers[slug] = LawRetriever(vectorstore=indexer.vectorstore)
            return retrievers[slug]

        def law_name_for_slug(slug: str) -> str:
            collection = retriever_for_slug(slug).vectorstore._collection
            metadata = collection.get(limit=1, include=["metadatas"])["metadatas"]
            law_name = str(metadata[0].get("law_name", "")) if metadata else ""
            if not law_name:
                raise RuntimeError(f"知识库 {slug} 缺少 law_name 元数据")
            return law_name

        report = evaluate_multi_knowledge_base(
            labels,
            retriever_for_slug,
            mode=args.mode,
            top_k=args.top_k,
            law_name_for_slug=law_name_for_slug if args.mode == "rrf" else None,
        )
        report["run"] = {
            "mode": args.mode,
            "persist_directory": str(args.persist_directory),
            "collections": {
                slug: default_collection_name(slug)
                for slug in sorted({label["knowledge_base_slug"] for label in labels})
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except (OSError, EvaluationDatasetError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"评测失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
