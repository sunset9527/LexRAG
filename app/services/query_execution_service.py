"""Pure query-execution helpers independent of FastAPI transport."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.session_service import ConversationTurn
from src.workflow.legal_evidence_workflow import RouteDecision

logger = logging.getLogger(__name__)


def is_cacheable_query_result(payload: dict[str, Any]) -> bool:
    return (
        payload.get("verification_status") == "pass"
        and payload.get("metadata", {}).get("cacheable", True) is True
    )


def record_query_observability(
    *,
    event_id: str,
    organization_id: int,
    current_user_id: int,
    question: str,
    answer: str,
    verification_status: str,
    metadata: dict[str, Any],
    latency_ms: int,
    audit_service: Any,
    usage_service: Any,
    metrics_recorder: Any,
) -> None:
    """Record optional observability data without affecting a legal answer."""

    metrics_recorder(
        verification_status=verification_status,
        cache_hit=str(metadata.get("cache_hit", "none")),
        latency_ms=latency_ms,
        workflow_trace=metadata.get("workflow_trace"),
    )
    if audit_service is None or usage_service is None:
        return
    try:
        created = audit_service.append_query(
            event_id=event_id,
            organization_id=organization_id,
            actor_user_id=current_user_id,
            request_id=event_id,
            question=question,
            answer=answer,
            verification_status=verification_status,
            metadata={
                "cache_hit": metadata.get("cache_hit", "none"),
                "law_area": metadata.get("law_area"),
                "knowledge_base": metadata.get("knowledge_base_slug"),
                "citation_count": len(metadata.get("citations", [])),
            },
        )
        if created:
            usage_service.record_query(
                event_id=event_id,
                organization_id=organization_id,
                actor_user_id=current_user_id,
                latency_ms=latency_ms,
                estimated_tokens=int(metadata.get("estimated_tokens") or 0),
            )
    except Exception as exc:
        logger.warning("查询审计或统计写入失败，已旁路: %s", exc)


def load_or_create_session(
    session_service: Any,
    *,
    user_id: int,
    organization_id: int,
    requested_session_id: str | None,
    question: str,
) -> tuple[str, Any]:
    if requested_session_id:
        session_payload = session_service.get_for_user(
            user_id=user_id,
            session_id=requested_session_id,
            organization_id=organization_id,
        )
    else:
        session_payload = session_service.create(
            user_id=user_id,
            initial_question=question,
            organization_id=organization_id,
        )
    session_id = session_payload["id"]
    memory_turns = session_service.load_memory(
        user_id=user_id,
        session_id=session_id,
        organization_id=organization_id,
    )
    return session_id, memory_turns


def resolve_collections(
    *,
    knowledge_base_service: Any,
    query_version_service: Any,
    selected_slugs: list[str],
    organization_id: int,
    case_date: Any,
) -> tuple[Any, dict[str, Any], dict[str, str]]:
    """Resolve version-aware collections, with a legacy READY-collection fallback."""

    version_selections: dict[str, Any] = {}
    collection_names: dict[str, str] = {}
    if query_version_service is not None:
        for slug in selected_slugs:
            selection = query_version_service.resolve(
                slug,
                organization_id=organization_id,
                case_date=case_date,
            )
            version_selections[slug] = selection
            collection_names[slug] = selection.collection_name
        return version_selections[selected_slugs[0]], version_selections, collection_names
    for slug in selected_slugs:
        collection_names[slug] = knowledge_base_service.get_ready_collection_name_for_organization(
            slug,
            organization_id=organization_id,
        )
    return None, version_selections, collection_names


def build_cache_scope(
    *,
    user_id: int,
    session_id: str,
    selected_slugs: list[str],
    base_url: str,
    model: str,
    retrieval_version: str,
    case_date: Any,
    version_selections: dict[str, Any],
) -> dict[str, str]:
    """Build a cache key scope without credentials or authorization tokens."""

    return {
        "user_scope": f"user:{user_id}",
        "session_id": session_id,
        "knowledge_base_slug": "|".join(sorted(selected_slugs)),
        "base_url": base_url,
        "model": model,
        "prompt_version": "runtime-v1",
        "retrieval_version": retrieval_version,
        "case_date": case_date.isoformat() if case_date else "",
        "version_id": "|".join(
            f"{slug}:{selection.provenance['version_id']}"
            for slug, selection in sorted(version_selections.items())
        ),
    }


def build_evidence_answer_generator(
    llm: Any,
    *,
    memory_turns: list[ConversationTurn] | None = None,
    repair_llm: Any | None = None,
):
    memory_sections = []
    for turn in memory_turns or []:
        citations = "、".join(turn.verified_citations) or "（无已验证引用）"
        memory_sections.append(
            f"用户：{turn.question}\n助手：{turn.answer}\n已验证历史引用：{citations}"
        )
    memory_text = "\n\n".join(memory_sections) or "（本会话尚无历史）"

    def generate(question: str, evidence: list[Any], issues: list[str] | None = None) -> str:
        statutes = [item for item in evidence if item.source_type == "statute"]
        evidence_text = "\n\n".join(
            f"【{item.law_name}第{item.normalized_article_id}条】\n{item.content}"
            for item in statutes
        )
        repair_instruction = ""
        if issues:
            repair_instruction = (
                "\n上一次回答未通过引用校验，问题如下：\n- "
                + "\n- ".join(issues)
                + "\n请只使用下列证据重写回答。"
            )
        prompt = f"""你是法律信息助手。请仅依据下面的本次检索证据回答用户问题。

用户问题：{question}

历史上下文（仅帮助理解，不构成本轮证据）：
{memory_text}

可引用证据：
{evidence_text}

要求：
1. 每个法律结论必须有且只能有一个来自证据的法条引用，格式严格为【法律名称第N条】。
2. 不得引用未出现在证据中的法律、条号或案例；证据不足时明确说明限制。
3. 新法律结论和引用只能来自本轮检索证据，历史中的法条不得作为本轮引用。
4. 不构成法律建议，提示用户在需要时咨询专业律师。{repair_instruction}
"""
        selected_llm = repair_llm if issues and repair_llm is not None else llm
        return selected_llm.invoke(prompt).content.strip()

    return generate


def build_evidence_planner(llm: Any):
    def plan(question: str) -> list[dict[str, str]]:
        prompt = f"""将以下法律问题拆成最多 4 个互不重复的检索子问题。
只输出 JSON 数组，每项格式为 {{"question": "...", "depends_on": ""}}。
问题：{question}"""
        content = llm.invoke(prompt).content.strip().replace("```json", "").replace("```", "")
        result = json.loads(content)
        if not isinstance(result, list):
            raise ValueError("planning output must be a JSON array")
        return result

    return plan


def route_evidence_workflow(question: str) -> RouteDecision:
    normalized = question.lower()
    comparative = any(word in normalized for word in ("区别", "对比", "不同", "分别"))
    procedural = any(word in normalized for word in ("怎么办", "流程", "仲裁", "起诉", "维权"))
    include_case = any(word in normalized for word in ("案例", "判例", "法院怎么判"))
    include_graph = comparative or any(word in normalized for word in ("依据", "关联", "适用"))
    intent = (
        "comparative"
        if comparative
        else "procedural"
        if procedural
        else "analytical"
        if include_case
        else "factual"
    )
    return RouteDecision(intent=intent, include_case=include_case, include_graph=include_graph)
