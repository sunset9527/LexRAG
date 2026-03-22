"""
检索模块
"""

from .intent_router import IntentRouter, IntentType, QueryIntent
from .law_retriever import LawRetriever, RetrievalResult

# 可选模块：依赖未安装时降级
try:
    from .case_retriever import CaseRetriever, CaseRetrievalResult
except ImportError:
    CaseRetriever = None
    CaseRetrievalResult = None

try:
    from .graph_retriever import GraphRetriever, GraphRetrievalResult
except ImportError:
    GraphRetriever = None
    GraphRetrievalResult = None

try:
    from .bm25_retriever import BM25Retriever, BM25Result
except ImportError:
    BM25Retriever = None
    BM25Result = None

try:
    from .fusion import reciprocal_rank_fusion, FusedResult
except ImportError:
    reciprocal_rank_fusion = None
    FusedResult = None

try:
    from .reranker import CrossEncoderReranker, RerankedResult
except ImportError:
    CrossEncoderReranker = None
    RerankedResult = None

try:
    from .query_rewriter import QueryRewriter, RewrittenQuery
except ImportError:
    QueryRewriter = None
    RewrittenQuery = None

try:
    from .context_compressor import ContextCompressor
except ImportError:
    ContextCompressor = None

__all__ = [
    "IntentRouter",
    "IntentType",
    "QueryIntent",
    "LawRetriever",
    "RetrievalResult",
    "CaseRetriever",
    "CaseRetrievalResult",
    "GraphRetriever",
    "GraphRetrievalResult",
    "BM25Retriever",
    "BM25Result",
    "reciprocal_rank_fusion",
    "FusedResult",
    "CrossEncoderReranker",
    "RerankedResult",
    "QueryRewriter",
    "RewrittenQuery",
    "ContextCompressor",
]
