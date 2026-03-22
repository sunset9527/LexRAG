"""BM25关键词检索器"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import jieba

logger = logging.getLogger(__name__)

@dataclass
class BM25Result:
    """BM25检索结果"""
    doc_id: str
    content: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)

class BM25Retriever:
    """
    基于rank_bm25的BM25关键词检索器
    
    特点：
    - 使用jieba中文分词
    - 支持元数据关联
    - 精确匹配法条编号和术语
    """
    
    def __init__(self):
        from rank_bm25 import BM25Okapi
        self.bm25 = None
        self.documents: List[Dict[str, Any]] = []
        self.tokenized_corpus: List[List[str]] = []
    
    def build_index(self, documents: List[Dict[str, Any]], content_key: str = "content"):
        """
        构建BM25索引
        
        Args:
            documents: 文档列表，每个文档是包含content和metadata的字典
            content_key: 内容字段名
        """
        self.documents = documents
        self.tokenized_corpus = [list(jieba.cut(doc[content_key])) for doc in documents]
        from rank_bm25 import BM25Okapi
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        logger.info(f"BM25索引构建完成，共 {len(documents)} 个文档")
    
    def retrieve(self, query: str, top_k: int = 5) -> List[BM25Result]:
        """
        检索相关文档
        
        Args:
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            检索结果列表
        """
        if self.bm25 is None:
            logger.error("BM25索引未构建")
            return []
        
        tokenized_query = list(jieba.cut(query))
        scores = self.bm25.get_scores(tokenized_query)
        
        # 获取top_k
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append(BM25Result(
                    doc_id=self.documents[idx].get("doc_id", str(idx)),
                    content=self.documents[idx].get("content", ""),
                    score=float(scores[idx]),
                    metadata=self.documents[idx].get("metadata", {})
                ))
        
        return results
    
    def add_documents(self, documents: List[Dict[str, Any]], content_key: str = "content"):
        """增量添加文档"""
        self.documents.extend(documents)
        self.tokenized_corpus.extend([list(jieba.cut(doc[content_key])) for doc in documents])
        from rank_bm25 import BM25Okapi
        self.bm25 = BM25Okapi(self.tokenized_corpus)
