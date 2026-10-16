"""
法条引用自校验

提取回答中的法条引用，检索原文验证一致性
"""

import json
import logging
import re
from dataclasses import dataclass
from enum import StrEnum

# v1.7: Langfuse 可观测工厂
from app.services.langfuse_helper import create_llm

logger = logging.getLogger(__name__)


class VerificationStatus(StrEnum):
    """校验状态"""

    PASS = "pass"  # 通过
    FAIL = "fail"  # 不通过
    PARTIAL = "partial"  # 部分通过
    CANNOT_VERIFY = "cannot_verify"  # 无法校验


@dataclass
class Citation:
    """法条引用"""

    article_id: str  # 法条编号
    citation_text: str  # 引用的原文片段
    position: tuple[int, int]  # 在回答中的位置
    is_verified: bool = False
    verification_result: str | None = None
    original_text: str | None = None


@dataclass
class VerificationResult:
    """校验结果"""

    status: VerificationStatus
    citations: list[Citation]
    overall_consistency: float  # 整体一致性评分 0-1
    issues: list[str]  # 发现的问题
    suggestions: list[str]  # 修正建议
    verified_answer: str | None = None


class SelfVerifier:
    """
    法条引用自校验器

    功能：
    1. 从回答中提取法条引用
    2. 检索法条原文
    3. 验证引用是否与原文一致
    4. 对不一致的内容提出修正建议
    """

    # 法条引用正则表达式
    # 注意：根据/依据 分支的字符类排除【】，否则会截胡【第X条】引用（贪婪吃到【...】
    CITATION_PATTERN = re.compile(
        r"【([^】]+)】|依据([^，,。\s【】]+)[条款项]|根据([^，,。\s【】]+)[条款项]|"
        r"第([零一二三四五六七八九十百千\d]+)条|"
        r"(?:《([^》]+)》第([零一二三四五六七八九十百千\d]+)条)"
    )

    # 从「第188条」/「民法典第188条」中提取纯数字条号（兼容 metadata.article_number 存储格式）
    NUMBER_PATTERN = re.compile(r"(\d+)")

    @staticmethod
    def _normalize_article_id(article_id: str) -> str:
        """把『第188条』/『民法典第188条』规范化为纯数字『188』"""
        m = SelfVerifier.NUMBER_PATTERN.search(article_id)
        if m:
            return m.group(1)
        return article_id

    # 验证提示词
    VERIFICATION_PROMPT = """你是一个法律专家，需要验证回答中的法条引用是否正确。

回答内容：
{answer}

法条原文：
{law_text}

请验证：
1. 回答中引用的法条内容是否与原文一致？
2. 引用是否准确？有无断章取义或曲解？
3. 引用是否完整？是否遗漏了重要的条件或限制？

输出JSON格式：
{{
    "is_consistent": true/false,
    "consistency_score": 0.0-1.0,
    "issues": ["发现的问题列表"],
    "suggestions": ["修正建议列表"],
    "verification_details": [
        {{
            "cited_text": "回答中引用的内容",
            "original_text": "法条原文",
            "is_match": true/false,
            "issue": "如果不匹配，说明问题"
        }}
    ]
}}

只输出JSON，不要有其他内容。"""

    # 修正提示词
    CORRECTION_PROMPT = """你是一个法律专家，需要修正回答中的法条引用错误。

原始回答：
{answer}

正确的法条原文：
{law_text}

发现的问题：
{issues}

请修正回答中的错误，确保所有法条引用都准确无误。
- 保持原回答的逻辑结构
- 只修正法条引用相关的错误
- 修正后的回答仍需保持专业和准确

只输出修正后的回答，不要有其他说明。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
    ):
        """
        初始化校验器

        Args:
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
        """
        self.llm = create_llm(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.0,
        )

    def extract_citations(self, answer: str) -> list[Citation]:
        """
        从回答中提取法条引用

        Args:
            answer: 回答文本

        Returns:
            引用列表
        """
        citations = []

        # 使用正则表达式提取
        for match in self.CITATION_PATTERN.finditer(answer):
            groups = match.groups()

            # 解析匹配到的内容
            article_id = None
            citation_text = match.group(0)

            if groups[0]:  # 【法条编号】
                article_id = groups[0]
            elif groups[1]:  # 依据...条
                article_id = f"第{self._convert_number(groups[1])}条"
            elif groups[2]:  # 根据...条
                article_id = f"第{self._convert_number(groups[2])}条"
            elif groups[3]:  # 第...条
                article_id = f"第{self._convert_number(groups[3])}条"
            elif groups[4] and groups[5]:  # 《法律名》第...条
                article_id = f"{groups[4]}第{self._convert_number(groups[5])}条"

            if article_id:
                # 规范化为纯数字条号（匹配 metadata.article_number 存储格式），
                # 否则 retrieve_by_article_number 永远查不到 -> 全部 cannot_verify
                article_id = self._normalize_article_id(article_id)
                citations.append(
                    Citation(
                        article_id=article_id,
                        citation_text=citation_text,
                        position=(match.start(), match.end()),
                    )
                )

        # 去重
        seen = set()
        unique_citations = []
        for c in citations:
            if c.article_id not in seen:
                seen.add(c.article_id)
                unique_citations.append(c)

        logger.info(f"提取到 {len(unique_citations)} 个法条引用")
        return unique_citations

    def verify_citation(self, citation: Citation, law_retriever_func) -> tuple[bool, str | None]:
        """
        校验单个法条引用

        Args:
            citation: 引用对象
            law_retriever_func: 法条检索函数

        Returns:
            (是否一致, 法条原文)
        """
        try:
            # 检索法条原文
            original_result = law_retriever_func(citation.article_id)

            if not original_result:
                # 法条不在数据库中，标记为"未收录"而非"失败"
                logger.info(f"法条未收录: {citation.article_id}")
                citation.is_verified = False
                citation.original_text = "[该法条暂未收录到知识库中]"
                citation.verification_result = {"is_consistent": None, "note": "article_not_found"}
                return True, citation.original_text  # 返回True避免计入fail

            original_text = original_result.full_content

            # 使用LLM进行详细验证
            prompt = self.VERIFICATION_PROMPT.format(
                answer=f"引用: {citation.citation_text}", law_text=original_text
            )

            response = self.llm.invoke(prompt)
            content = response.content.strip()
            # 健壮 JSON 提取：LLM 输出可能带 ```json 围栏/前后说明文字，
            # 直接 json.loads 会因前导换行或杂文本抛异常 -> 软通过(校验失效)
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if not m:
                raise ValueError(f"回答中未找到 JSON 对象: {content[:100]}")
            result = json.loads(m.group(0))

            is_consistent = result.get("is_consistent", False)
            citation.is_verified = is_consistent
            citation.original_text = original_text
            citation.verification_result = result

            return is_consistent, original_text

        except Exception as e:
            logger.error(f"法条校验失败: {e}")
            citation.is_verified = False
            citation.original_text = f"[校验出错: {str(e)}]"
            return True, citation.original_text  # 软失败，不阻断流程

    def verify(self, answer: str, law_retriever_func) -> VerificationResult:
        """
        验证回答中的所有法条引用

        Args:
            answer: 回答文本
            law_retriever_func: 法条检索函数

        Returns:
            校验结果
        """
        # 1. 提取引用
        citations = self.extract_citations(answer)

        if not citations:
            logger.info("回答中未发现法条引用")
            return VerificationResult(
                status=VerificationStatus.CANNOT_VERIFY,
                citations=[],
                overall_consistency=0.0,
                issues=["回答中未包含法条引用"],
                suggestions=["建议在回答中添加法条引用以增强可信度"],
            )

        # 2. 验证每个引用
        all_consistent = True
        all_issues = []
        all_suggestions = []
        not_found_count = 0

        for citation in citations:
            is_consistent, original_text = self.verify_citation(citation, law_retriever_func)

            if original_text and original_text.startswith("[该法条暂未收录"):
                not_found_count += 1
                # 未收录不算校验失败
            elif not is_consistent:
                all_consistent = False
                all_issues.append(f"法条 {citation.article_id} 引用可能不准确")
                all_suggestions.append(f"建议核实 {citation.article_id} 的具体内容")

        # 3. 计算整体一致性（排除未收录的法条）
        verifiable = [
            c
            for c in citations
            if not (c.original_text and c.original_text.startswith("[该法条暂未收录"))
        ]
        verified_count = sum(1 for c in verifiable if c.is_verified)
        overall_consistency = verified_count / len(verifiable) if verifiable else 1.0

        # 添加未收录提示
        if not_found_count > 0:
            all_issues.append(f"有 {not_found_count} 个引用法条暂未收录到知识库")

        # 4. 确定状态
        if not verifiable:
            # 所有引用都未收录，标记为无法校验
            status = VerificationStatus.CANNOT_VERIFY
        elif all_consistent:
            status = VerificationStatus.PASS
        elif verified_count > 0:
            status = VerificationStatus.PARTIAL
        else:
            status = VerificationStatus.FAIL

        return VerificationResult(
            status=status,
            citations=citations,
            overall_consistency=overall_consistency,
            issues=all_issues,
            suggestions=all_suggestions,
        )

    def correct(self, answer: str, verification_result: VerificationResult) -> str:
        """
        修正回答中的错误

        Args:
            answer: 原始回答
            verification_result: 校验结果

        Returns:
            修正后的回答
        """
        if verification_result.status == VerificationStatus.PASS:
            return answer

        try:
            # 收集所有正确的法条原文
            law_texts = []
            for citation in verification_result.citations:
                if citation.original_text:
                    law_texts.append(f"【{citation.article_id}】\n{citation.original_text}")

            prompt = self.CORRECTION_PROMPT.format(
                answer=answer,
                law_text="\n\n".join(law_texts),
                issues="\n".join(verification_result.issues),
            )

            response = self.llm.invoke(prompt)
            return response.content

        except Exception as e:
            logger.error(f"修正回答失败: {e}")
            return answer

    def _convert_number(self, num_str: str) -> str:
        """将中文数字转换为阿拉伯数字"""
        chinese_map = {
            "零": "0",
            "一": "1",
            "二": "2",
            "三": "3",
            "四": "4",
            "五": "5",
            "六": "6",
            "七": "7",
            "八": "8",
            "九": "9",
            "十": "10",
        }

        try:
            return str(int(num_str))
        except ValueError:
            pass

        result = 0
        temp = 0
        for char in num_str:
            if char in chinese_map:
                val = int(chinese_map[char])
                if val >= 10:
                    temp = temp * val if temp else val
                else:
                    temp += val
        result += temp
        return str(result) if result else num_str

    def format_citations_for_display(self, citations: list[Citation]) -> str:
        """格式化引用用于显示"""
        parts = []
        for c in citations:
            status = "✓" if c.is_verified else "?"
            parts.append(f"{status} {c.article_id}: {c.citation_text}")
        return "\n".join(parts)
