"""
工作流节点定义

定义LangGraph工作流的各个节点
"""

import logging
import uuid
from datetime import datetime
from typing import Any

# v1.7: Langfuse 可观测工厂
from app.services.langfuse_helper import create_llm

from ..reasoning.multi_hop import MultiHopReasoner
from ..reasoning.self_verify import SelfVerifier, VerificationStatus
from ..retrieval.case_retriever import CaseRetriever
from ..retrieval.graph_retriever import GraphRetriever
from ..retrieval.intent_router import IntentRouter, IntentType
from ..retrieval.law_retriever import LawRetriever
from .state import WorkflowState, WorkflowStatus

logger = logging.getLogger(__name__)


class WorkflowNodes:
    """
    工作流节点集合

    包含所有工作流节点的实现
    """

    # 生成回答的提示词
    ANSWER_GENERATION_PROMPT = """你是一个专业的法律助手，需要根据检索到的法条回答用户的法律问题。

用户问题：{query}

检索到的相关法条：
{context}

请根据以上法条，提供一个准确、专业的法律回答。注意：
1. 每个结论都要引用具体的法条，使用【法条编号】的格式
2. 回答要完整，包含法条的适用条件和结论
3. 如果涉及多个法条，要说明它们之间的关系
4. 保持语言简洁明了，便于理解
5. 如果法条内容不足以完全回答问题，要明确说明

回答："""

    def __init__(
        self,
        intent_router: IntentRouter,
        law_retriever: LawRetriever,
        case_retriever: CaseRetriever | None = None,
        graph_retriever: GraphRetriever | None = None,
        multi_hop_reasoner: MultiHopReasoner | None = None,
        self_verifier: SelfVerifier | None = None,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
    ):
        """
        初始化节点集合

        Args:
            intent_router: 意图路由器
            law_retriever: 法条检索器
            case_retriever: 案例检索器（可选）
            graph_retriever: 图谱检索器（可选）
            multi_hop_reasoner: 多跳推理器（可选）
            self_verifier: 自校验器（可选）
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
        """
        self.intent_router = intent_router
        self.law_retriever = law_retriever
        self.case_retriever = case_retriever
        self.graph_retriever = graph_retriever
        self.multi_hop_reasoner = multi_hop_reasoner or MultiHopReasoner(
            api_key=api_key, base_url=base_url, model=model
        )
        self.self_verifier = self_verifier or SelfVerifier(
            api_key=api_key, base_url=base_url, model=model
        )
        self.llm = create_llm(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.1,
        )

    def initialize_state(self, state: WorkflowState) -> dict[str, Any]:
        """初始化状态"""
        state.query_id = str(uuid.uuid4())
        state.status = WorkflowStatus.ROUTING
        state.created_at = datetime.now().isoformat()

        return {"query_id": state.query_id, "status": state.status.value}

    def intent_routing_node(self, state: WorkflowState) -> dict[str, Any]:
        """
        意图路由节点

        识别用户查询意图，决定后续检索路径
        """
        try:
            logger.info(f"开始意图识别: {state.query}")
            intent = self.intent_router.route_query(state.query)

            state.intent = intent
            state.intent_type = intent.intent_type.value
            state.status = WorkflowStatus.RETRIEVING

            # 添加推理步骤
            state.add_reasoning_step(
                "intent_routing",
                f"识别意图类型: {intent.intent_type.value}",
                state.query,
                {"intent_type": intent.intent_type.value, "confidence": intent.confidence},
            )

            logger.info(f"意图识别完成: {intent.intent_type.value}, 置信度: {intent.confidence}")
            return {
                "intent": intent,
                "intent_type": intent.intent_type.value,
                "status": state.status.value,
            }

        except Exception as e:
            logger.error(f"意图识别失败: {e}")
            state.error = str(e)
            state.status = WorkflowStatus.FAILED
            return {"error": str(e), "status": WorkflowStatus.FAILED.value}

    def retrieve_node(self, state: WorkflowState) -> dict[str, Any]:
        """
        检索节点

        根据意图类型执行相应的检索
        """
        try:
            logger.info(f"开始检索: {state.query}")

            intent = state.intent
            retrieved_docs = []

            if intent.intent_type == IntentType.CASE_QUERY:
                # 案例检索
                if self.case_retriever:
                    case_results = self.case_retriever.retrieve(state.query, top_k=5)
                    state.retrieval_context.case_results = [r.to_dict() for r in case_results]
                    retrieved_docs.extend(
                        [{"content": r.summary, "type": "case"} for r in case_results]
                    )

            elif intent.intent_type == IntentType.ANALYSIS:
                # 使用图谱检索进行多跳推理
                if self.graph_retriever and intent.key_entities:
                    # 从关键实体中提取法条ID
                    for entity in intent.key_entities[:3]:
                        if "第" in entity and "条" in entity:
                            result = self.graph_retriever.retrieve(entity, max_hops=2)
                            state.retrieval_context.graph_results = result.retrieved_articles

            # 默认使用法条检索（v2.0 优化模式：加权RRF + 条号置顶 + 条款组聚合）
            law_results, grouped_context, _ = self.law_retriever.retrieve_optimized(
                state.query, top_k=5, intent=intent
            )

            state.retrieval_context.law_results = [r.to_dict() for r in law_results]

            # 构建检索上下文：优先使用聚合后的章节窗口上下文（覆盖整套规则，
            # 解决单条切片对跨条款综合题召回不全的问题）
            if grouped_context:
                context_parts = [grouped_context]
            else:
                context_parts = []
                for r in law_results:
                    context_parts.append(f"【{r.article_id}】\n{r.full_content}")
            state.retrieval_context.context_text = "\n\n".join(context_parts)

            retrieved_docs.extend([r.to_dict() for r in law_results])

            state.retrieved_documents = retrieved_docs
            state.status = WorkflowStatus.REASONING

            state.add_reasoning_step(
                "retrieval",
                f"检索到 {len(retrieved_docs)} 个相关文档",
                state.query,
                {"doc_count": len(retrieved_docs)},
            )

            logger.info(f"检索完成: {len(retrieved_docs)} 个文档")
            return {
                "retrieval_context": state.retrieval_context,
                "retrieved_documents": retrieved_docs,
                "status": state.status.value,
            }

        except Exception as e:
            logger.error(f"检索失败: {e}")
            state.error = str(e)
            state.status = WorkflowStatus.FAILED
            return {"error": str(e), "status": WorkflowStatus.FAILED.value}

    def multi_hop_reasoning_node(self, state: WorkflowState) -> dict[str, Any]:
        """
        多跳推理节点

        复杂问题拆解为子问题进行推理
        """
        try:
            intent = state.intent

            # 检查是否需要多跳推理
            if intent.intent_type in [IntentType.ANALYSIS, IntentType.LEGAL_APPLICATION]:
                # 使用多跳推理器
                result = self.multi_hop_reasoner.reason(
                    state.query, retrieval_func=lambda q: self.law_retriever.retrieve(q, top_k=3)
                )

                state.sub_questions = [
                    {"id": sq["id"], "question": sq["question"], "answer": sq["answer"]}
                    for sq in result.get("sub_questions", [])
                ]
                state.sub_answers = {
                    sq["id"]: sq["answer"] for sq in result.get("sub_questions", [])
                }

                state.add_reasoning_step(
                    "multi_hop_reasoning",
                    f"多跳推理完成，拆分为 {len(state.sub_questions)} 个子问题",
                    state.query,
                    {"sub_questions": state.sub_questions},
                )

                logger.info(f"多跳推理完成: {len(state.sub_questions)} 个子问题")
            else:
                # 单跳直接检索
                state.sub_questions = [{"id": "main", "question": state.query, "answer": ""}]

            return {"sub_questions": state.sub_questions, "status": state.status.value}

        except Exception as e:
            logger.error(f"多跳推理失败: {e}")
            state.error = str(e)
            return {"error": str(e)}

    def generate_answer_node(self, state: WorkflowState) -> dict[str, Any]:
        """
        生成回答节点

        基于检索结果生成最终回答
        """
        try:
            logger.info("开始生成回答")

            context = state.get_retrieval_text()

            if not context:
                state.answer = "抱歉，未找到与您问题相关的法律条文。"
                state.raw_answer = state.answer
                state.status = WorkflowStatus.COMPLETED
                return {"answer": state.answer, "status": state.status.value}

            prompt = self.ANSWER_GENERATION_PROMPT.format(query=state.query, context=context)

            response = self.llm.invoke(prompt)
            state.raw_answer = response.content
            state.answer = response.content
            state.status = WorkflowStatus.VERIFYING

            state.add_reasoning_step(
                "generate_answer",
                "回答生成完成",
                {"context_length": len(context)},
                {"answer_length": len(response.content)},
            )

            logger.info("回答生成完成")
            return {
                "answer": state.answer,
                "raw_answer": state.raw_answer,
                "status": state.status.value,
            }

        except Exception as e:
            logger.error(f"生成回答失败: {e}")
            state.error = str(e)
            state.status = WorkflowStatus.FAILED
            return {"error": str(e), "status": WorkflowStatus.FAILED.value}

    def verify_node(self, state: WorkflowState) -> dict[str, Any]:
        """
        校验节点

        验证回答中的法条引用是否正确
        """
        try:
            logger.info("开始校验")

            # 提取引用
            citations = self.self_verifier.extract_citations(state.answer)

            if not citations:
                state.verification_status = VerificationStatus.CANNOT_VERIFY
                state.status = WorkflowStatus.COMPLETED
                return {
                    "verification_status": state.verification_status.value,
                    "citations": [],
                    "status": state.status.value,
                }

            # 验证每个引用
            verified_citations = []
            for citation in citations:
                result = self.law_retriever.retrieve_by_article_number(citation.article_id)
                if result:
                    citation.original_text = result.full_content
                    # 简单验证：检查引用是否在原文附近
                    citation.is_verified = True
                    verified_citations.append(citation)

            state.citations = verified_citations
            state.verification_status = VerificationStatus.PASS
            state.status = WorkflowStatus.COMPLETED

            state.add_reasoning_step(
                "verify",
                f"校验完成，{len(verified_citations)} 个引用",
                {"citation_count": len(citations)},
                {"verified_count": len(verified_citations)},
            )

            logger.info(f"校验完成: {len(verified_citations)}/{len(citations)}")
            return {
                "citations": verified_citations,
                "verification_status": state.verification_status.value,
                "status": state.status.value,
            }

        except Exception as e:
            logger.error(f"校验失败: {e}")
            state.verification_status = VerificationStatus.FAIL
            state.verification_issues.append(str(e))
            return {
                "verification_status": state.verification_status.value,
                "verification_issues": state.verification_issues,
            }

    def correct_node(self, state: WorkflowState) -> dict[str, Any]:
        """
        修正节点

        修正回答中的错误
        """
        try:
            logger.info("开始修正")

            state.verification_attempts += 1

            # 使用校验器修正
            verification_result = type(
                "obj",
                (object,),
                {
                    "status": state.verification_status,
                    "citations": state.citations,
                    "issues": state.verification_issues,
                },
            )()

            corrected_answer = self.self_verifier.correct(state.answer, verification_result)

            state.answer = corrected_answer
            state.should_correct = False
            state.status = WorkflowStatus.VERIFYING

            state.add_reasoning_step(
                "correct",
                f"修正完成（第 {state.verification_attempts} 次）",
                state.raw_answer,
                corrected_answer,
            )

            logger.info("修正完成")
            return {"answer": state.answer, "status": state.status.value}

        except Exception as e:
            logger.error(f"修正失败: {e}")
            state.error = str(e)
            return {"error": str(e)}

    def decide_next_action(self, state: WorkflowState) -> str:
        """
        决定下一步动作

        Returns:
            下一个节点的名称
        """
        if state.error:
            return "failed"

        if state.status == WorkflowStatus.ROUTING:
            return "intent_routing"
        elif state.status == WorkflowStatus.RETRIEVING:
            return "retrieve"
        elif state.status == WorkflowStatus.REASONING:
            return "multi_hop_reasoning"
        elif state.status == WorkflowStatus.GENERATING:
            return "generate_answer"
        elif state.status == WorkflowStatus.VERIFYING:
            # 检查是否需要修正
            if state.verification_status == VerificationStatus.FAIL:
                if state.verification_attempts < 2:
                    return "correct"
                else:
                    return "failed"
            elif state.verification_status == VerificationStatus.PASS:
                return "completed"
            else:
                return "completed"
        elif state.status == WorkflowStatus.CORRECTING:
            return "verify"
        elif state.status == WorkflowStatus.COMPLETED:
            return "END"
        elif state.status == WorkflowStatus.FAILED:
            return "END"

        return "END"
