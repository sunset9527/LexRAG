"""
案例检索器

检索相似判例和典型案例
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json

# v1.7: Langfuse 可观测工厂
from app.services.langfuse_helper import create_llm

logger = logging.getLogger(__name__)


@dataclass
class CaseRetrievalResult:
    """案例检索结果"""
    case_id: str
    case_name: str
    case_type: str
    court_level: str          # 法院级别
    case_number: str           # 案号
    judgment_date: str         # 裁判日期
    summary: str               # 案件摘要
    key_facts: str            # 关键事实
    legal_basis: List[str]     # 法律依据
    judgment_result: str       # 裁判结果
    relevance_score: float     # 相关性分数
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_name": self.case_name,
            "case_type": self.case_type,
            "court_level": self.court_level,
            "case_number": self.case_number,
            "judgment_date": self.judgment_date,
            "summary": self.summary,
            "key_facts": self.key_facts,
            "legal_basis": self.legal_basis,
            "judgment_result": self.judgment_result,
            "relevance_score": self.relevance_score,
        }


class CaseRetriever:
    """
    案例检索器
    
    特点：
    - 基于向量相似度检索相似案例
    - 支持案例类型、法院级别等过滤
    - 返回结构化的案例信息
    - 支持案例与法条的关联
    """
    
    def __init__(
        self,
        case_vectorstore,
        law_retriever=None,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat"
    ):
        """
        初始化案例检索器
        
        Args:
            case_vectorstore: 案例向量存储
            law_retriever: 法律条文检索器（用于关联法条）
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
        """
        self.case_vectorstore = case_vectorstore
        self.law_retriever = law_retriever
        self.llm = create_llm(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.0,
        )
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        case_type: Optional[str] = None,
        court_level: Optional[str] = None,
        date_range: Optional[tuple] = None
    ) -> List[CaseRetrievalResult]:
        """
        检索相似案例
        
        Args:
            query: 查询文本
            top_k: 返回数量
            case_type: 案例类型过滤
            court_level: 法院级别过滤
            date_range: 日期范围 (起始日期, 结束日期)
            
        Returns:
            案例检索结果列表
        """
        # 构建过滤条件
        filter_dict = {}
        if case_type:
            filter_dict["case_type"] = case_type
        if court_level:
            filter_dict["court_level"] = court_level
        
        # 执行检索
        try:
            if filter_dict:
                results = self.case_vectorstore.similarity_search_with_score(
                    query, k=top_k * 2, filter=filter_dict
                )
            else:
                results = self.case_vectorstore.similarity_search_with_score(
                    query, k=top_k * 2
                )
        except Exception as e:
            logger.error(f"案例检索失败: {e}")
            return []
        
        # 解析结果
        case_results = []
        for doc, score in results[:top_k]:
            case_result = self._parse_case_document(doc, score)
            if case_result:
                case_results.append(case_result)
        
        return case_results
    
    def _parse_case_document(
        self, 
        doc, 
        score: float
    ) -> Optional[CaseRetrievalResult]:
        """解析案例文档"""
        try:
            metadata = doc.metadata
            
            # 尝试从页面内容中提取信息
            content = doc.page_content
            
            return CaseRetrievalResult(
                case_id=metadata.get("case_id", ""),
                case_name=metadata.get("case_name", "未知案例"),
                case_type=metadata.get("case_type", ""),
                court_level=metadata.get("court_level", ""),
                case_number=metadata.get("case_number", ""),
                judgment_date=metadata.get("judgment_date", ""),
                summary=content[:500],  # 取前500字符作为摘要
                key_facts=metadata.get("key_facts", ""),
                legal_basis=json.loads(metadata.get("legal_basis", "[]")),
                judgment_result=metadata.get("judgment_result", ""),
                relevance_score=score
            )
        except Exception as e:
            logger.error(f"解析案例文档失败: {e}")
            return None
    
    def retrieve_by_legal_issues(
        self, 
        legal_issues: List[str],
        top_k: int = 3
    ) -> List[CaseRetrievalResult]:
        """
        根据法律问题检索案例
        
        Args:
            legal_issues: 法律问题列表
            top_k: 每类问题的案例数
            
        Returns:
            案例检索结果列表
        """
        all_results = []
        
        for issue in legal_issues:
            results = self.retrieve(issue, top_k=top_k)
            all_results.extend(results)
        
        # 去重
        seen_ids = set()
        unique_results = []
        for result in all_results:
            if result.case_id not in seen_ids:
                seen_ids.add(result.case_id)
                unique_results.append(result)
        
        return unique_results[:top_k * 2]
    
    def enhance_with_law_articles(
        self, 
        cases: List[CaseRetrievalResult]
    ) -> List[Dict[str, Any]]:
        """
        为案例关联法律条文
        
        Args:
            cases: 案例列表
            
        Returns:
            增强后的案例列表
        """
        if not self.law_retriever:
            return [c.to_dict() for c in cases]
        
        enhanced_cases = []
        for case in cases:
            case_dict = case.to_dict()
            
            # 检索相关法条
            relevant_laws = []
            for law_ref in case.legal_basis:
                result = self.law_retriever.retrieve_by_article_number(law_ref)
                if result:
                    relevant_laws.append(result.to_dict())
            
            case_dict["relevant_laws"] = relevant_laws
            enhanced_cases.append(case_dict)
        
        return enhanced_cases
    
    def get_case_summary(self, case: CaseRetrievalResult) -> str:
        """
        生成案例摘要
        
        Args:
            case: 案例对象
            
        Returns:
            案例摘要文本
        """
        summary_parts = [
            f"【案例名称】{case.case_name}",
            f"【案号】{case.case_number}",
            f"【法院】{case.court_level}",
            f"【裁判日期】{case.judgment_date}",
            f"【案件类型】{case.case_type}",
            f"【案件事实】{case.key_facts}",
            f"【裁判结果】{case.judgment_result}",
        ]
        
        if case.legal_basis:
            summary_parts.append(f"【法律依据】{', '.join(case.legal_basis)}")
        
        return "\n".join(summary_parts)
