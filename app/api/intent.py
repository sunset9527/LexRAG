"""Static intent examples used by the query UI."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["查询辅助"])

_EXAMPLES = {
    "law_article": ["民法典第143条规定了什么？", "合同编第520条内容是什么？", "请告诉我第467条的具体内容"],
    "case_query": ["有没有类似的案例？", "这种情况法院一般怎么判？", "能否提供一些相关判例？"],
    "legal_application": ["租房纠纷怎么处理？", "合同违约应该赔偿多少？", "这种情况适用什么法律？"],
    "comparison": ["定金和订金有什么区别？", "情势变更和不可抗力有何不同？", "书面合同和口头合同的法律效力一样吗？"],
    "analysis": ["签订房屋买卖合同需要注意哪些法律问题？", "网购纠纷如何依法维权？", "投资合同中的风险条款有什么法律意义？"],
    "clarification": ["什么是格式条款？", "这条法律怎么理解？", "什么是合同的实质性变更？"],
}


@router.get("/intent/{intent_type}")
def get_intent_examples(intent_type: str) -> dict[str, str | list[str]]:
    return {"intent_type": intent_type, "examples": _EXAMPLES.get(intent_type, [])}
