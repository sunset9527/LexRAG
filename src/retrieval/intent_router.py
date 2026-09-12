"""
查询意图识别与路由

使用LLM分类用户意图，路由到不同检索器
"""

import logging
import json
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass
from pydantic import BaseModel, Field

# v1.7: Langfuse 可观测工厂
from app.services.langfuse_helper import create_llm

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    """查询意图类型枚举"""
    LAW_ARTICLE = "law_article"           # 法条查询：直接问某个法条内容
    CASE_QUERY = "case_query"             # 案例查询：查找类似案例
    LEGAL_APPLICATION = "legal_application"  # 法律适用：某情况应适用什么法条
    COMPARISON = "comparison"             # 对比分析：比较不同法条/规定
    ANALYSIS = "analysis"                 # 综合分析：需要多法条联合分析
    CLARIFICATION = "clarification"       # 释义咨询：法条含义解释
    UNKNOWN = "unknown"                   # 未知意图


class QueryIntent(BaseModel):
    """查询意图结构"""
    intent_type: IntentType = Field(description="意图类型")
    confidence: float = Field(description="置信度 0-1")
    key_entities: List[str] = Field(default_factory=list, description="关键实体")
    sub_questions: List[str] = Field(default_factory=list, description="拆分的子问题")
    search_keywords: List[str] = Field(default_factory=list, description="搜索关键词")
    reasoning_chain: List[str] = Field(default_factory=list, description="推理链")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="其他元数据")


class IntentRouter:
    """
    查询意图路由器
    
    使用LLM进行意图识别，识别用户的查询类型并路由到不同的检索器
    
    意图类型：
    1. 法条查询 (law_article): 用户直接询问某个具体法条的内容
    2. 案例查询 (case_query): 用户查找类似案例
    3. 法律适用 (legal_application): 询问某种情况下应适用什么法律
    4. 对比分析 (comparison): 比较不同法律条款
    5. 综合分析 (analysis): 需要多个法条联合分析
    6. 释义咨询 (clarification): 询问法条的含义
    """
    
    # 意图识别提示词模板
    INTENT_CLASSIFICATION_PROMPT = """你是一个法律助手，需要分析用户的法律问题并识别其意图类型。

用户问题：{query}

请分析这个问题，判断其意图类型：

1. **法条查询 (law_article)**: 用户直接询问某个具体法条的内容
   - 例："民法典第143条规定了什么？"、"合同编第520条内容是什么？"

2. **案例查询 (case_query)**: 用户想查找类似的判例
   - 例："有没有类似的案例？"、"这种情况法院一般怎么判？"

3. **法律适用 (legal_application)**: 询问某种情况应适用什么法律
   - 例："租房纠纷怎么处理？"、"合同违约应该赔偿多少？"

4. **对比分析 (comparison)**: 比较不同法条或规定的区别
   - 例："定金和订金有什么区别？"、"情势变更和不可抗力有何不同？"

5. **综合分析 (analysis)**: 需要多个法条联合分析
   - 例："房屋买卖合同需要注意哪些法律问题？"

6. **释义咨询 (clarification)**: 询问法条的含义
   - 例："什么是格式条款？"、"这条怎么理解？"

请输出JSON格式的意图分析结果：
{{
    "intent_type": "意图类型",
    "confidence": 0.0-1.0的置信度,
    "key_entities": ["识别出的关键实体，如法条编号、法律术语等"],
    "sub_questions": ["如果问题复杂，拆分的子问题"],
    "search_keywords": ["用于检索的关键词"],
    "reasoning_chain": ["意图识别的简要推理过程"],
    "metadata": {{"additional_info": "其他元信息"}}
}}

只输出JSON，不要有其他内容。"""
    
    # 问题拆解提示词
    PROBLEM_DECOMPOSITION_PROMPT = """你是一个法律助手，需要将复杂的法律问题拆解为子问题。

用户问题：{query}

请将这个问题拆解为可独立检索的子问题。每个子问题应该：
1. 聚焦一个具体问题
2. 可以通过单个法条或简单检索回答
3. 按逻辑顺序排列

输出JSON格式：
{{
    "sub_questions": ["子问题1", "子问题2", ...],
    "reasoning": "拆解逻辑说明"
}}

请严格按照JSON格式返回，不要包含markdown代码块标记或其他内容。"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat"
    ):
        """
        初始化意图路由器
        
        Args:
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
        """
        self.llm = create_llm(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.1,
        )
    
    def classify_intent(self, query: str) -> QueryIntent:
        """
        分类用户查询意图
        
        Args:
            query: 用户查询文本
            
        Returns:
            QueryIntent对象
        """
        try:
            prompt = self.INTENT_CLASSIFICATION_PROMPT.format(query=query)
            response = self.llm.invoke(prompt)
            content = response.content.strip().replace('```json', '').replace('```', '').strip()
            result = json.loads(content)
            
            intent_type = IntentType(result.get("intent_type", "unknown"))
            confidence = float(result.get("confidence", 0.5))
            
            return QueryIntent(
                intent_type=intent_type,
                confidence=confidence,
                key_entities=result.get("key_entities", []),
                sub_questions=result.get("sub_questions", []),
                search_keywords=result.get("search_keywords", []),
                reasoning_chain=result.get("reasoning_chain", []),
                metadata=result.get("metadata", {})
            )
        except json.JSONDecodeError as e:
            logger.error(f"意图分类JSON解析失败: {e}")
            return self._create_unknown_intent(query)
        except Exception as e:
            logger.error(f"意图分类失败: {e}")
            return self._create_unknown_intent(query)
    
    def decompose_problem(self, query: str) -> List[str]:
        """
        将复杂问题拆解为子问题
        
        Args:
            query: 用户查询
            
        Returns:
            子问题列表
        """
        try:
            prompt = self.PROBLEM_DECOMPOSITION_PROMPT.format(query=query)
            response = self.llm.invoke(prompt)
            content = response.content.strip().replace('```json', '').replace('```', '').strip()
            result = json.loads(content)
            return result.get("sub_questions", [])
        except Exception as e:
            logger.error(f"问题拆解失败: {e}")
            return [query]  # 返回原问题作为单一子问题
    
    def route_query(
        self, 
        query: str, 
        enable_decomposition: bool = True
    ) -> QueryIntent:
        """
        路由用户查询
        
        Args:
            query: 用户查询
            enable_decomposition: 是否启用问题拆解
            
        Returns:
            QueryIntent对象
        """
        intent = self.classify_intent(query)
        
        # 如果置信度低或问题复杂，进行问题拆解
        if intent.confidence < 0.7 or enable_decomposition:
            if not intent.sub_questions:
                intent.sub_questions = self.decompose_problem(query)
        
        # 根据意图类型设置搜索关键词
        if not intent.search_keywords:
            intent.search_keywords = self._generate_search_keywords(query, intent)
        
        logger.info(f"意图分类结果: {intent.intent_type.value}, 置信度: {intent.confidence}")
        return intent
    
    def _generate_search_keywords(
        self, 
        query: str, 
        intent: QueryIntent
    ) -> List[str]:
        """生成搜索关键词"""
        keywords = []
        
        # 从查询中提取法律术语
        legal_terms = [
            "合同", "法", "条", "责任", "义务", "权利",
            "规定", "情形", "情况", "行为", "事项"
        ]
        
        for term in legal_terms:
            if term in query:
                keywords.append(term)
        
        # 从key_entities获取
        keywords.extend(intent.key_entities[:3])
        
        return list(set(keywords)) if keywords else [query]
    
    def _create_unknown_intent(self, query: str) -> QueryIntent:
        """创建未知意图"""
        return QueryIntent(
            intent_type=IntentType.UNKNOWN,
            confidence=0.0,
            key_entities=[],
            sub_questions=[query],
            search_keywords=[query],
            reasoning_chain=["无法确定意图类型，返回原始查询"],
            metadata={}
        )
    
    def get_retriever_type(self, intent: QueryIntent) -> str:
        """
        根据意图类型返回应使用的检索器类型
        
        Args:
            intent: 查询意图
            
        Returns:
            检索器类型标识
        """
        mapping = {
            IntentType.LAW_ARTICLE: "law_retriever",
            IntentType.CASE_QUERY: "case_retriever",
            IntentType.LEGAL_APPLICATION: "law_retriever",
            IntentType.COMPARISON: "law_retriever",
            IntentType.ANALYSIS: "graph_retriever",
            IntentType.CLARIFICATION: "law_retriever",
            IntentType.UNKNOWN: "law_retriever",
        }
        return mapping.get(intent.intent_type, "law_retriever")
