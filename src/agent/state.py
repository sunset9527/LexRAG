"""
工作流状态定义

定义LangGraph工作流的状态结构
"""

from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass, field
from enum import Enum
from pydantic import BaseModel, Field

from ..retrieval.intent_router import QueryIntent, IntentType
from ..reasoning.self_verify import VerificationStatus


class WorkflowStatus(str, Enum):
    """工作流状态"""
    IDLE = "idle"
    ROUTING = "routing"
    RETRIEVING = "retrieving"
    REASONING = "reasoning"
    GENERATING = "generating"
    VERIFYING = "verifying"
    CORRECTING = "correcting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class RetrievalContext:
    """检索上下文"""
    law_results: List[Dict[str, Any]] = field(default_factory=list)
    case_results: List[Dict[str, Any]] = field(default_factory=list)
    graph_results: List[Dict[str, Any]] = field(default_factory=list)
    context_text: str = ""


@dataclass
class ReasoningTrace:
    """推理追踪"""
    step_type: str
    description: str
    input_data: Any
    output_data: Any
    confidence: float = 1.0


@dataclass
class Citation:
    """法条引用"""
    article_id: str
    citation_text: str
    original_text: str
    is_verified: bool = False
    verification_result: Optional[str] = None


@dataclass
class QueryResult:
    """查询结果"""
    query: str
    answer: str
    intent: str
    citations: List[Citation]
    verification_status: str
    verification_issues: List[str]
    reasoning_trace: List[ReasoningTrace]
    sub_questions: List[Dict[str, str]]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "intent": self.intent,
            "citations": [
                {
                    "article_id": c.article_id,
                    "citation_text": c.citation_text,
                    "original_text": c.original_text,
                    "is_verified": c.is_verified
                }
                for c in self.citations
            ],
            "verification_status": self.verification_status,
            "verification_issues": self.verification_issues,
            "reasoning_trace": [
                {
                    "step_type": r.step_type,
                    "description": r.description,
                    "confidence": r.confidence
                }
                for r in self.reasoning_trace
            ],
            "sub_questions": self.sub_questions,
            "metadata": self.metadata
        }


class WorkflowState(BaseModel):
    """LangGraph工作流状态"""
    
    # 基础信息
    query_id: str = Field(default="")
    query: str = Field(default="")
    status: WorkflowStatus = Field(default=WorkflowStatus.IDLE)
    
    # 意图识别
    intent: Optional[QueryIntent] = Field(default=None)
    intent_type: Optional[str] = Field(default=None)
    
    # 检索结果
    retrieval_context: RetrievalContext = Field(default_factory=RetrievalContext)
    retrieved_documents: List[Dict[str, Any]] = Field(default_factory=list)
    
    # 推理
    sub_questions: List[str] = Field(default_factory=list)
    sub_answers: Dict[str, str] = Field(default_factory=dict)
    reasoning_trace: List[ReasoningTrace] = Field(default_factory=list)
    
    # 生成
    answer: str = Field(default="")
    raw_answer: str = Field(default="")
    
    # 校验
    citations: List[Citation] = Field(default_factory=list)
    verification_status: VerificationStatus = Field(default=VerificationStatus.PASS)
    verification_issues: List[str] = Field(default_factory=list)
    verification_attempts: int = Field(default=0)
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = Field(default=None)
    
    # 路由决策
    next_action: Optional[str] = Field(default=None)
    should_correct: bool = Field(default=False)
    should_retry: bool = Field(default=False)
    
    class Config:
        arbitrary_types_allowed = True
    
    def add_reasoning_step(
        self,
        step_type: str,
        description: str,
        input_data: Any,
        output_data: Any
    ):
        """添加推理步骤"""
        self.reasoning_trace.append(ReasoningTrace(
            step_type=step_type,
            description=description,
            input_data=input_data,
            output_data=output_data
        ))
    
    def get_retrieval_text(self) -> str:
        """获取检索文本用于生成"""
        parts = []
        
        if self.retrieval_context.context_text:
            parts.append(self.retrieval_context.context_text)
        
        for doc in self.retrieved_documents[:5]:
            article_id = doc.get("article_id", "")
            content = doc.get("full_content", doc.get("content", ""))
            if content:
                parts.append(f"【{article_id}】\n{content}")
        
        return "\n\n".join(parts)
    
    def get_citations_for_display(self) -> List[Dict[str, Any]]:
        """获取用于显示的引用"""
        return [
            {
                "article_id": c.article_id,
                "citation_text": c.citation_text,
                "original_text": c.original_text,
                "status": "verified" if c.is_verified else "pending"
            }
            for c in self.citations
        ]
