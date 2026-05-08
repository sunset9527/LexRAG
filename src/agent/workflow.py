"""
LangGraph ReAct Agent工作流

使用LangGraph + LangChain Tools实现真正的ReAct Agent
"""

import logging
import uuid
import json
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from .state import WorkflowState, WorkflowStatus, QueryResult, Citation, ReasoningTrace
from .tools import init_tools, get_all_tools
from ..retrieval.intent_router import IntentRouter, IntentType
from ..retrieval.law_retriever import LawRetriever
from ..retrieval.case_retriever import CaseRetriever
from ..retrieval.graph_retriever import GraphRetriever
from ..reasoning.self_verify import SelfVerifier, VerificationStatus

logger = logging.getLogger(__name__)


class LegalRAGWorkflow:
    """
    法律RAG智能体工作流（ReAct版）
    
    使用LangGraph ReAct Agent实现：
    1. Agent自主决策调用4个工具
    2. 工具包含完整的RAG增强管线
    3. 回答后自验证法条引用
    """
    
    SYSTEM_PROMPT = """你是一个专业的法律助手，专门解答民法典相关法律问题。

你可以使用以下工具来回答用户的问题：
1. search_statute - 检索民法典条文（输入法律问题描述）
2. search_case - 检索类似判例（输入案情描述）
3. lookup_article - 精确查阅某条法条全文（输入法条编号如"第712条"）
4. analyze_legal_relation - 分析法律关系（输入案情描述）

回答原则：
- 你只能引用通过工具检索到的法条，不要引用训练数据中记忆的法条
- 每个结论都要引用具体法条，使用【法条编号】格式
- 如果工具未返回某法条，说明知识库中暂时没有，不要自行编造该法条内容
- 先理解问题，再决定调用哪个工具
- 复杂问题可以多次调用不同工具
- 回答要准确、专业、有法条支撑"""

    def __init__(
        self,
        intent_router: IntentRouter,
        law_retriever: LawRetriever,
        case_retriever: Optional[CaseRetriever] = None,
        graph_retriever: Optional[GraphRetriever] = None,
        bm25_retriever=None,
        reranker=None,
        query_rewriter=None,
        context_compressor=None,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        max_verification_retries: int = 2
    ):
        self.max_verification_retries = max_verification_retries
        self.intent_router = intent_router
        self.law_retriever = law_retriever
        
        # 初始化工具注册
        init_tools(
            law_retriever=law_retriever,
            case_retriever=case_retriever,
            bm25_retriever=bm25_retriever,
            graph_retriever=graph_retriever,
            reranker=reranker,
            query_rewriter=query_rewriter,
            context_compressor=context_compressor,
            api_key=api_key,
            base_url=base_url,
            model=model
        )
        
        # 初始化LLM
        self.llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.1,
            request_timeout=30,
            max_retries=1
        )
        
        # 初始化自校验器
        self.self_verifier = SelfVerifier(
            api_key=api_key,
            base_url=base_url,
            model=model
        )
        
        # 初始化查询改写器
        self.query_rewriter = query_rewriter
        
        # 创建ReAct Agent
        self.agent = create_react_agent(
            model=self.llm,
            tools=get_all_tools(),
            prompt=self.SYSTEM_PROMPT
        )
    
    def query(self, question: str, config: Optional[Dict[str, Any]] = None) -> QueryResult:
        """
        执行查询
        
        Args:
            question: 用户问题
            config: 配置参数
            
        Returns:
            QueryResult对象
        """
        logger.info(f"开始处理查询: {question}")
        query_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        
        try:
            reasoning_trace = []
            
            # 1. 查询增强（如果启用）
            enhanced_query = question
            if self.query_rewriter:
                try:
                    rewritten = self.query_rewriter.rewrite(question)
                    enhanced_query = rewritten.rewritten_query
                    reasoning_trace.append(ReasoningTrace(
                        step_type="query_rewriting",
                        description=f"查询改写: {question} → {enhanced_query}",
                        input_data={"original": question},
                        output_data={"rewritten": enhanced_query},
                        confidence=1.0
                    ))
                    logger.info(f"查询改写: {question} -> {enhanced_query}")
                except Exception as e:
                    logger.warning(f"查询改写失败，使用原始查询: {e}")
                    reasoning_trace.append(ReasoningTrace(
                        step_type="query_rewriting",
                        description=f"查询改写失败，使用原始查询: {str(e)}",
                        input_data={"original": question},
                        output_data=None,
                        confidence=0.0
                    ))
            
            # 2. 意图识别
            intent_type = "unknown"
            try:
                intent = self.intent_router.route_query(question, enable_decomposition=False)
                intent_type = intent.intent_type.value
                reasoning_trace.append(ReasoningTrace(
                    step_type="intent_routing",
                    description=f"意图识别: {intent_type} (置信度: {intent.confidence:.2f})",
                    input_data={"query": question},
                    output_data={"intent": intent_type, "confidence": intent.confidence},
                    confidence=intent.confidence
                ))
                logger.info(f"意图识别: {intent_type}, 置信度: {intent.confidence}")
            except Exception as e:
                logger.warning(f"意图识别失败: {e}")
                reasoning_trace.append(ReasoningTrace(
                    step_type="intent_routing",
                    description=f"意图识别失败: {str(e)}",
                    input_data={"query": question},
                    output_data=None,
                    confidence=0.0
                ))
            
            # 3. ReAct Agent执行
            messages = [HumanMessage(content=question)]
            agent_result = self.agent.invoke(
                {"messages": messages},
                config=config or {"configurable": {"thread_id": query_id}}
            )
            
            # 4. 提取Agent回答和推理过程
            answer = ""
            for msg in agent_result.get("messages", []):
                if isinstance(msg, AIMessage):
                    if msg.content:
                        answer = msg.content
                    # 记录工具调用作为推理过程
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        for tc in msg.tool_calls:
                            reasoning_trace.append(ReasoningTrace(
                                step_type="tool_call",
                                description=f"调用工具: {tc.get('name', 'unknown')}",
                                input_data=tc.get('args', {}),
                                output_data=None,
                                confidence=1.0
                            ))
            
            # 记录Tool响应
            from langchain_core.messages import ToolMessage
            for msg in agent_result.get("messages", []):
                if isinstance(msg, ToolMessage):
                    tool_output = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
                    reasoning_trace.append(ReasoningTrace(
                        step_type="tool_response",
                        description=f"工具返回结果",
                        input_data=None,
                        output_data={"preview": tool_output},
                        confidence=1.0
                    ))
            
            if not answer:
                answer = "抱歉，无法生成回答。"
            
            # 5. 自校验
            citations = []
            verification_status = VerificationStatus.CANNOT_VERIFY
            verification_issues = []
            verification_attempts = 0
            
            try:
                verification_result = self.self_verifier.verify(
                    answer,
                    law_retriever_func=lambda aid: self.law_retriever.retrieve_by_article_number(aid)
                )
                
                reasoning_trace.append(ReasoningTrace(
                    step_type="self_verification",
                    description=f"自校验: {verification_result.status.value if hasattr(verification_result.status, 'value') else str(verification_result.status)}",
                    input_data=None,
                    output_data={
                        "status": verification_result.status.value if hasattr(verification_result.status, 'value') else str(verification_result.status),
                        "citations_count": len(verification_result.citations),
                        "issues_count": len(verification_result.issues)
                    },
                    confidence=1.0
                ))
                
                citations = [
                    Citation(
                        article_id=c.article_id,
                        citation_text=c.citation_text,
                        original_text=c.original_text or "",
                        is_verified=c.is_verified
                    )
                    for c in verification_result.citations
                ]
                verification_status = verification_result.status
                verification_issues = verification_result.issues
                
                # 如果验证失败，尝试修正
                if verification_status == VerificationStatus.FAIL and self.max_verification_retries > 0:
                    for attempt in range(self.max_verification_retries):
                        verification_attempts += 1
                        corrected = self.self_verifier.correct(answer, verification_result)
                        if corrected != answer:
                            answer = corrected
                            # 重新验证
                            verification_result = self.self_verifier.verify(
                                answer,
                                law_retriever_func=lambda aid: self.law_retriever.retrieve_by_article_number(aid)
                            )
                            verification_status = verification_result.status
                            if verification_status != VerificationStatus.FAIL:
                                break
            except Exception as e:
                logger.error(f"自校验失败: {e}")
                verification_issues.append(str(e))
            
            # 6. 构建结果
            return QueryResult(
                query=question,
                answer=answer,
                intent=intent_type,
                citations=citations,
                verification_status=verification_status.value if hasattr(verification_status, 'value') else str(verification_status),
                verification_issues=verification_issues,
                reasoning_trace=reasoning_trace,
                sub_questions=[],
                metadata={
                    "query_id": query_id,
                    "created_at": created_at,
                    "verification_attempts": verification_attempts
                }
            )
            
        except Exception as e:
            logger.error(f"查询处理失败: {e}")
            return QueryResult(
                query=question,
                answer=f"处理查询时发生错误: {str(e)}",
                intent="unknown",
                citations=[],
                verification_status="fail",
                verification_issues=[str(e)],
                reasoning_trace=[],
                sub_questions=[]
            )
    
    async def aquery(self, question: str, config: Optional[Dict[str, Any]] = None) -> QueryResult:
        """异步查询"""
        import asyncio
        return await asyncio.to_thread(self.query, question, config)
