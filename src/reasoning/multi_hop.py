"""
多跳法律推理

复杂问题拆解为子问题，独立检索后合并
"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


class ReasoningStepType(str, Enum):
    """推理步骤类型"""
    DECOMPOSE = "decompose"       # 问题分解
    RETRIEVE = "retrieve"         # 检索
    SYNTHESIZE = "synthesize"     # 综合
    INFER = "infer"               # 推理
    VERIFY = "verify"             # 验证


@dataclass
class ReasoningStep:
    """推理步骤"""
    step_id: int
    step_type: ReasoningStepType
    description: str
    input_data: Any
    output_data: Any
    confidence: float = 1.0


@dataclass
class SubQuestion:
    """子问题"""
    question_id: str
    question_text: str
    reasoning_needed: List[str]  # 需要用到的法条
    retrieved_content: Optional[str] = None
    answer: Optional[str] = None
    confidence: float = 0.0


class MultiHopReasoner:
    """
    多跳法律推理器
    
    功能：
    1. 将复杂法律问题拆解为多个子问题
    2. 对每个子问题独立检索相关法条
    3. 综合多个子问题的答案形成最终回答
    4. 追踪完整的推理链
    """
    
    # 问题拆解提示词
    DECOMPOSITION_PROMPT = """你是一个专业的法律助手，需要将复杂的法律问题拆解为简单的子问题。

用户问题：{query}

请将这个问题拆解为2-5个可以独立回答的子问题。每个子问题应该：
1. 聚焦一个具体的法律问题
2. 可以通过检索相关法条来回答
3. 按逻辑顺序排列

同时，为每个子问题标注可能需要用到的法律知识领域。

输出JSON格式：
{
    "sub_questions": [
        {
            "id": "q1",
            "question": "子问题1",
            "reasoning_needed": ["需要的法理或知识领域"]
        },
        ...
    ],
    "reasoning_chain": ["推理步骤说明"]
}

只输出JSON，不要有其他内容。"""
    
    # 子问题回答提示词
    SUB_QUESTION_ANSWER_PROMPT = """你是一个专业的法律助手，需要根据检索到的法条回答子问题。

子问题：{question}

检索到的相关法条：
{retrieved_content}

请基于以上法条，回答这个子问题。注意：
1. 必须引用法条的具体条文
2. 如果法条不足以回答，说明需要补充什么信息
3. 保持回答简洁准确

只输出回答内容。"""
    
    # 综合回答提示词
    SYNTHESIS_PROMPT = """你是一个专业的法律助手，需要综合多个子问题的答案，形成完整的法律回答。

用户原始问题：{original_query}

子问题及答案：
{sub_answers}

检索到的法条：
{retrieved_laws}

请综合以上信息，形成一个完整、连贯的回答。
- 回答应该有清晰的逻辑结构
- 每个结论都要有法条支撑
- 如果子问题之间有逻辑关联，应该体现出来
- 引用法条时使用【法条编号】的格式

只输出回答内容。"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat"
    ):
        """
        初始化推理器
        
        Args:
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
        """
        self.llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.1
        )
        self.reasoning_steps: List[ReasoningStep] = []
        self.sub_questions: List[SubQuestion] = []
    
    def decompose(self, query: str) -> List[SubQuestion]:
        """
        将问题分解为子问题
        
        Args:
            query: 原始问题
            
        Returns:
            子问题列表
        """
        try:
            prompt = self.DECOMPOSITION_PROMPT.format(query=query)
            response = self.llm.invoke(prompt)
            content = response.content.strip().replace("```json", "").replace("```", "").strip()
            result = json.loads(content)
            
            sub_questions = []
            for sq in result.get("sub_questions", []):
                sub_questions.append(SubQuestion(
                    question_id=sq["id"],
                    question_text=sq["question"],
                    reasoning_needed=sq.get("reasoning_needed", [])
                ))
            
            self.sub_questions = sub_questions
            self._add_step(ReasoningStepType.DECOMPOSE, query, sub_questions)
            
            logger.info(f"问题分解完成，共{len(sub_questions)}个子问题")
            return sub_questions
            
        except Exception as e:
            logger.error(f"问题分解失败: {e}")
            return [SubQuestion("q1", query, [])]
    
    def answer_sub_question(
        self,
        sub_question: SubQuestion,
        retrieved_content: str
    ) -> str:
        """
        回答单个子问题
        
        Args:
            sub_question: 子问题
            retrieved_content: 检索到的内容
            
        Returns:
            回答
        """
        try:
            prompt = self.SUB_QUESTION_ANSWER_PROMPT.format(
                question=sub_question.question_text,
                retrieved_content=retrieved_content
            )
            response = self.llm.invoke(prompt)
            sub_question.retrieved_content = retrieved_content
            sub_question.answer = response.content
            return response.content
        except Exception as e:
            logger.error(f"子问题回答失败: {e}")
            return "无法回答该子问题"
    
    def synthesize(
        self,
        original_query: str,
        sub_questions: List[SubQuestion]
    ) -> str:
        """
        综合子问题答案形成最终回答
        
        Args:
            original_query: 原始问题
            sub_questions: 子问题列表
            
        Returns:
            综合后的回答
        """
        try:
            # 构建子问题答案文本
            sub_answers_text = "\n".join([
                f"问题{ sq.question_id}: {sq.question_text}\n回答: {sq.answer or '未回答'}"
                for sq in sub_questions
            ])
            
            # 构建检索到的法条文本
            retrieved_laws_text = "\n".join([
                sq.retrieved_content or ""
                for sq in sub_questions
                if sq.retrieved_content
            ])
            
            prompt = self.SYNTHESIS_PROMPT.format(
                original_query=original_query,
                sub_answers=sub_answers_text,
                retrieved_laws=retrieved_laws_text
            )
            
            response = self.llm.invoke(prompt)
            
            self._add_step(
                ReasoningStepType.SYNTHESIZE,
                {"sub_questions": sub_answers_text},
                response.content
            )
            
            return response.content
            
        except Exception as e:
            logger.error(f"综合回答失败: {e}")
            return "综合回答失败"
    
    def reason(
        self,
        query: str,
        retrieval_func,
        max_hops: int = 3
    ) -> Dict[str, Any]:
        """
        执行完整的多跳推理流程
        
        Args:
            query: 用户问题
            retrieval_func: 检索函数，接收子问题文本，返回检索结果
            max_hops: 最大推理跳数
            
        Returns:
            推理结果字典
        """
        self.reasoning_steps = []
        self.sub_questions = []
        
        # 1. 问题分解
        sub_questions = self.decompose(query)
        
        # 2. 子问题独立检索和回答
        for sq in sub_questions:
            retrieved = retrieval_func(sq.question_text)
            self.answer_sub_question(sq, retrieved)
        
        # 3. 综合回答
        final_answer = self.synthesize(query, sub_questions)
        
        # 4. 构建结果
        return {
            "original_query": query,
            "sub_questions": [
                {
                    "id": sq.question_id,
                    "question": sq.question_text,
                    "answer": sq.answer,
                    "retrieved_content": sq.retrieved_content
                }
                for sq in sub_questions
            ],
            "final_answer": final_answer,
            "reasoning_steps": [
                {
                    "step_type": step.step_type.value,
                    "description": step.description,
                    "confidence": step.confidence
                }
                for step in self.reasoning_steps
            ]
        }
    
    def _add_step(
        self,
        step_type: ReasoningStepType,
        input_data: Any,
        output_data: Any
    ):
        """添加推理步骤"""
        step = ReasoningStep(
            step_id=len(self.reasoning_steps) + 1,
            step_type=step_type,
            description=f"{step_type.value} - 步骤 {len(self.reasoning_steps) + 1}",
            input_data=input_data,
            output_data=output_data
        )
        self.reasoning_steps.append(step)
    
    def get_reasoning_trace(self) -> List[Dict[str, Any]]:
        """获取推理追踪"""
        return [
            {
                "step_id": step.step_id,
                "step_type": step.step_type.value,
                "description": step.description,
                "confidence": step.confidence
            }
            for step in self.reasoning_steps
        ]
