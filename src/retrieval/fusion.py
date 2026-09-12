"""多路检索结果融合"""
import logging
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class FusedResult:
    """融合结果"""
    doc_id: str
    score: float
    source: str  # 来自哪个检索器
    content: str
    metadata: Dict[str, Any]

def reciprocal_rank_fusion(
    results_list: List[List[Dict[str, Any]]],
    id_key: str = "doc_id",
    score_key: str = "score",
    content_key: str = "content",
    metadata_key: str = "metadata",
    k: int = 60,
    weights: Optional[List[float]] = None
) -> List[FusedResult]:
    """
    RRF (Reciprocal Rank Fusion) 融合多路检索结果

    Args:
        results_list: 多路检索结果列表，每路是一个结果列表
        id_key: 文档ID字段名
        score_key: 分数字段名
        content_key: 内容字段名
        metadata_key: 元数据字段名
        k: RRF常数（默认60）
        weights: 每路检索的权重（如 [1.4, 0.6] 表示 BM25 路权重 1.4、向量路 0.6）。
                 缺省为等权 1.0。用于按 query 意图动态加权（见 retrieval_optimizer.rrf_weights）

    Returns:
        融合后的结果列表，按分数降序排列
    """
    fused_scores: Dict[str, float] = {}
    doc_info: Dict[str, Dict[str, Any]] = {}
    
    for retriever_idx, results in enumerate(results_list):
        w = weights[retriever_idx] if weights and retriever_idx < len(weights) else 1.0
        for rank, result in enumerate(results, 1):
            doc_id = result.get(id_key, f"doc_{rank}")
            rrf_score = w * 1.0 / (k + rank)
            fused_scores[doc_id] = fused_scores.get(doc_id, 0) + rrf_score
            
            if doc_id not in doc_info:
                doc_info[doc_id] = {
                    "content": result.get(content_key, ""),
                    "metadata": result.get(metadata_key, {}),
                    "source": f"retriever_{retriever_idx}"
                }
    
    # 按融合分数排序
    sorted_results = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    
    return [
        FusedResult(
            doc_id=doc_id,
            score=score,
            source=doc_info[doc_id]["source"],
            content=doc_info[doc_id]["content"],
            metadata=doc_info[doc_id]["metadata"]
        )
        for doc_id, score in sorted_results
    ]
