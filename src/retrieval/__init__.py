"""
检索模块
"""

from .intent_router import IntentRouter, IntentType, QueryIntent
from .law_retriever import LawRetriever, RetrievalResult

# 可选模块：依赖未安装时降级
try:
    from .case_retriever import CaseRetrievalResult, CaseRetriever
except ImportError:
    CaseRetriever = None
    CaseRetrievalResult = None

try:
    from .graph_retriever import GraphRetrievalResult, GraphRetriever
except ImportError:
    GraphRetriever = None
    GraphRetrievalResult = None

try:
    from .bm25_retriever import BM25Result, BM25Retriever
except ImportError:
    BM25Retriever = None
    BM25Result = None

try:
    from .fusion import FusedResult, reciprocal_rank_fusion
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
