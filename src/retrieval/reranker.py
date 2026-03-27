"""Cross-Encoder重排序"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RerankedResult:
    """重排序结果"""
    doc_id: str
    score: float
    content: str
    metadata: Dict[str, Any]

class CrossEncoderReranker:
    """
    基于Cross-Encoder的重排序器
    
    使用BGE-Reranker对检索结果精排
    """
    
    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        """
        初始化重排序器
        
        Args:
            model_name: 模型名称
        """
        self.model_name = model_name
        self._model = None
    
    def _load_model(self):
        """懒加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
                logger.info(f"Reranker模型加载完成: {self.model_name}")
            except Exception as e:
                logger.error(f"Reranker模型加载失败: {e}")
                self._model = None
    
    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 5,
        content_key: str = "content"
    ) -> List[RerankedResult]:
        """
        对文档重排序
        
        Args:
            query: 查询文本
            documents: 文档列表
            top_k: 返回数量
            content_key: 内容字段名
            
        Returns:
            重排序后的结果列表
        """
        if not documents:
            return []
        
        self._load_model()
        
        if self._model is None:
            # 模型加载失败，返回原始顺序
            logger.warning("Reranker模型不可用，返回原始顺序")
            return [
                RerankedResult(
                    doc_id=doc.get("doc_id", str(i)),
                    score=doc.get("score", 0.0),
                    content=doc.get(content_key, ""),
                    metadata=doc.get("metadata", {})
                )
                for i, doc in enumerate(documents[:top_k])
            ]
        
        try:
            pairs = [[query, doc.get(content_key, "")] for doc in documents]
            scores = self._model.predict(pairs)
            
            # 按分数排序
            scored_docs = list(zip(documents, scores))
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            
            return [
                RerankedResult(
                    doc_id=doc.get("doc_id", str(i)),
                    score=float(score),
                    content=doc.get(content_key, ""),
                    metadata=doc.get("metadata", {})
                )
                for i, (doc, score) in enumerate(scored_docs[:top_k])
            ]
        except Exception as e:
            logger.error(f"重排序失败: {e}")
            return [
                RerankedResult(
                    doc_id=doc.get("doc_id", str(i)),
                    score=doc.get("score", 0.0),
                    content=doc.get(content_key, ""),
                    metadata=doc.get("metadata", {})
                )
                for i, doc in enumerate(documents[:top_k])
            ]
