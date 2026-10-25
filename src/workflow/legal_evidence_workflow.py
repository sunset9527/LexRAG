"""LangGraph 驱动的证据优先法律问答工作流。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from .evidence import CitationVerifier, EvidenceItem, EvidenceLedger, VerifiedCitation

EVIDENCE_INSUFFICIENT_ANSWER = (
    "现有证据不足以支持可靠结论。请补充事实、选择相关知识库，或咨询专业律师。"
)


class QueryCancelled(RuntimeError):
    """调用方已离开或显式取消，工作流应在节点边界停止。"""

WORKFLOW_NODE_NAMES = frozenset(
    {
        "planning",
        "knowledge_base_routing",
        "routing",
        "statute_retrieval",
        "case_retrieval",
        "graph_retrieval",
        "evidence_ledger",
        "answer",
        "citation_verifier",
        "repair",
        "finalize",
        "evidence_insufficient",
    }
)


@dataclass(frozen=True)
class RouteDecision:
    """路由节点输出；法规检索始终执行。"""

    intent: str = "factual"
    include_case: bool = False
    include_graph: bool = False


@dataclass
class EvidenceWorkflowResult:
    query: str
    answer: str
    intent: str
    citations: list[VerifiedCitation]
    verification_status: str
    verification_issues: list[str]
    sub_questions: list[dict[str, str]]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class WorkflowRuntimeContext:
    """一次 Graph 调用使用的依赖和非敏感请求标识。"""

    law_retriever: Any
    answer_generator: Callable[[str, list[EvidenceItem], list[str] | None], str]
    planner: Callable[[str], Any] | None = None
    router: Callable[[str], RouteDecision | dict[str, Any] | str] | None = None
    case_retriever: Any | None = None
    graph_retriever: Any | None = None
    citation_verifier: CitationVerifier | None = None
    user_id: str | int | None = None
    organization_id: str | int | None = None
    session_id: str | None = None
    model_id: str | None = None


class LegalWorkflowState(TypedDict, total=False):
    """单次法律工作流调用的显式状态。"""

    question: str
    knowledge_base_slug: str
    knowledge_base_slugs: list[str]
    knowledge_base_route: dict[str, Any]
    conversation_context: list[dict[str, Any]]
    sub_questions: list[dict[str, str]]
    route_decision: RouteDecision
    statute_evidence: list[EvidenceItem]
    case_evidence: list[EvidenceItem]
    graph_evidence: list[EvidenceItem]
    evidence: list[EvidenceItem]
    answer: str
    citations: list[VerifiedCitation]
    verification_status: str
    verification_issues: list[str]
    verification_attempts: int
    degraded: bool
    degradation_reasons: list[dict[str, str]]
    trace: list[dict[str, Any]]
    cacheable: bool
    case_retriever_available: bool
    graph_retriever_available: bool
    case_retrieval_completed: bool


class QueryEnhancedLawRetriever:
    """复用多候选改写、HyDE 与 RRF 检索，失败时只查原问题。"""

    def __init__(
        self, law_retriever: Any, query_rewriter: Any | None = None, *, enable_hyde: bool = False
    ) -> None:
        self.law_retriever = law_retriever
        self.query_rewriter = query_rewriter
        self.enable_hyde = enable_hyde

    def retrieve(self, question: str, *, top_k: int = 5) -> Any:
        if self.query_rewriter is None:
            return self._retrieve_original(question, top_k=top_k)
        try:
            rewritten = self.query_rewriter.rewrite_candidates(question)
            search_queries = getattr(rewritten, "search_queries", None) or [question]
            hyde_query = self.query_rewriter.generate_hyde(question) if self.enable_hyde else None
            return self.law_retriever.retrieve_multi_query(
                search_queries,
                hyde_query=hyde_query,
                top_k=top_k,
            )
        except Exception:
            return self._retrieve_original(question, top_k=top_k)

    def _retrieve_original(self, question: str, *, top_k: int) -> Any:
        """主检索入口优先走已启用的 BM25 + 向量 RRF，不能静默退回单路。"""
        retrieve_optimized = getattr(self.law_retriever, "retrieve_optimized", None)
        if getattr(self.law_retriever, "enable_optimization", False) and callable(retrieve_optimized):
            results, _, _ = retrieve_optimized(question, top_k=top_k)
            return results
        return self.law_retriever.retrieve(question, top_k=top_k)


def _is_complex(question: str) -> bool:
    return len(question) > 80 or any(
        marker in question for marker in ("并且", "同时", "分别", "流程", "以及")
    )


def _normalize_plan(planned: Any, fallback_question: str) -> list[dict[str, str]]:
    if not isinstance(planned, Iterable) or isinstance(planned, str | bytes | dict):
        return [{"question": fallback_question, "depends_on": ""}]
    items = []
    for item in planned:
        if isinstance(item, str) and item.strip():
            items.append({"question": item.strip(), "depends_on": ""})
        elif isinstance(item, dict) and str(item.get("question", "")).strip():
            items.append(
                {
                    "question": str(item["question"]).strip(),
                    "depends_on": str(item.get("depends_on", "")),
                }
            )
    return items or [{"question": fallback_question, "depends_on": ""}]


def _route(
    router: Callable[[str], RouteDecision | dict[str, Any] | str] | None,
    question: str,
) -> RouteDecision:
    if router is None:
        return RouteDecision()
    result = router(question)
    if isinstance(result, RouteDecision):
        return result
    if isinstance(result, dict):
        return RouteDecision(**result)
    if isinstance(result, str):
        return RouteDecision(intent=result)
    raise TypeError("router must return RouteDecision, dict, or str")


def _to_statute_evidence(result: Any, knowledge_base_slug: str) -> EvidenceItem | None:
    if isinstance(result, EvidenceItem):
        return result
    scoped_slug = str(getattr(result, "knowledge_base_slug", "") or "")
    scoped_result = getattr(result, "result", None)
    if scoped_slug and scoped_result is not None:
        result = scoped_result
    article_id = str(getattr(result, "article_number", "") or getattr(result, "article_id", ""))
    law_name = str(getattr(result, "law_name", ""))
    content = str(getattr(result, "full_content", "") or getattr(result, "content", ""))
    source_id = str(getattr(result, "chunk_id", "") or getattr(result, "article_id", ""))
    if not all((article_id, law_name, content, source_id)):
        return None
    return EvidenceItem(
        source_id=source_id,
        source_type="statute",
        knowledge_base_slug=scoped_slug or knowledge_base_slug,
        law_name=law_name,
        article_id=article_id,
        content=content,
        score=float(getattr(result, "score", 0.0) or 0.0),
        retrieval_path="statute",
        version_id=getattr(result, "metadata", {}).get("version_id"),
        effective_from=getattr(result, "metadata", {}).get("effective_from"),
        effective_to=getattr(result, "metadata", {}).get("effective_to"),
        source_url=getattr(result, "metadata", {}).get("source_url"),
        content_hash=getattr(result, "metadata", {}).get("content_hash"),
    )


def _selected_knowledge_base_slugs(state: LegalWorkflowState) -> list[str]:
    slugs = [slug for slug in state.get("knowledge_base_slugs", []) if slug]
    return slugs or [state["knowledge_base_slug"]]


def _to_case_evidence(result: Any) -> EvidenceItem | None:
    if isinstance(result, EvidenceItem):
        return result
    source_id = str(getattr(result, "case_id", ""))
    content = str(getattr(result, "summary", "") or getattr(result, "judgment_result", "") or "")
    if not source_id or not content:
        return None
    return EvidenceItem(
        source_id=source_id,
        source_type="case",
        knowledge_base_slug="annual-cases",
        law_name="",
        article_id="",
        content=content,
        score=float(getattr(result, "relevance_score", 0.0) or 0.0),
        retrieval_path="case",
    )


def _to_graph_evidence(result: Any, knowledge_base_slug: str) -> EvidenceItem | None:
    if isinstance(result, EvidenceItem):
        return result
    if not isinstance(result, dict):
        return None
    article_id = str(result.get("article_id", ""))
    if not article_id:
        return None
    return EvidenceItem(
        source_id=article_id,
        source_type="graph",
        knowledge_base_slug=knowledge_base_slug,
        law_name=str(result.get("law_name", "")),
        article_id=article_id,
        content=str(result.get("content", "")),
        score=1.0,
        retrieval_path="graph",
    )


def _trace_event(
    node: str,
    status: str,
    started: float,
    *,
    input_count: int = 0,
    output_count: int = 0,
    reason: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "node": node,
        "status": status,
        "duration_ms": round((perf_counter() - started) * 1000, 3),
        "input_count": input_count,
        "output_count": output_count,
    }
    if reason:
        event["reason"] = reason
    return event


def _append_trace(
    state: LegalWorkflowState,
    node: str,
    status: str,
    started: float,
    *,
    input_count: int = 0,
    output_count: int = 0,
    reason: str | None = None,
) -> list[dict[str, Any]]:
    return [
        *state.get("trace", []),
        _trace_event(
            node,
            status,
            started,
            input_count=input_count,
            output_count=output_count,
            reason=reason,
        ),
    ]


def _degrade(
    state: LegalWorkflowState, node: str, exc: Exception
) -> tuple[list[dict[str, str]], str]:
    reason = type(exc).__name__
    return [*state.get("degradation_reasons", []), {"node": node, "reason": reason}], reason


def _planning_node(
    state: LegalWorkflowState, runtime: Runtime[WorkflowRuntimeContext]
) -> dict[str, Any]:
    started = perf_counter()
    question = state["question"]
    planner = runtime.context.planner
    if not _is_complex(question) or planner is None:
        return {
            "sub_questions": [{"question": question, "depends_on": ""}],
            "trace": _append_trace(state, "planning", "skipped", started),
        }
    try:
        sub_questions = _normalize_plan(planner(question), question)
        return {
            "sub_questions": sub_questions,
            "trace": _append_trace(
                state, "planning", "completed", started, output_count=len(sub_questions)
            ),
        }
    except Exception as exc:
        reasons, reason = _degrade(state, "planning", exc)
        return {
            "sub_questions": [{"question": question, "depends_on": ""}],
            "degraded": True,
            "degradation_reasons": reasons,
            "trace": _append_trace(state, "planning", "degraded", started, reason=reason),
        }


def _routing_node(
    state: LegalWorkflowState, runtime: Runtime[WorkflowRuntimeContext]
) -> dict[str, Any]:
    started = perf_counter()
    try:
        decision = _route(runtime.context.router, state["question"])
        return {
            "route_decision": decision,
            "trace": _append_trace(state, "routing", "completed", started, output_count=1),
        }
    except Exception as exc:
        reasons, reason = _degrade(state, "routing", exc)
        return {
            "route_decision": RouteDecision(),
            "degraded": True,
            "degradation_reasons": reasons,
            "trace": _append_trace(state, "routing", "degraded", started, reason=reason),
        }


def _statute_retrieval_once(
    state: LegalWorkflowState, runtime: Runtime[WorkflowRuntimeContext]
) -> dict[str, Any]:
    started = perf_counter()
    try:
        results = runtime.context.law_retriever.retrieve(state["question"], top_k=5)
        evidence = [
            item
            for result in results or []
            if (item := _to_statute_evidence(result, state["knowledge_base_slug"])) is not None
        ]
        return {
            "statute_evidence": evidence,
            "trace": _append_trace(
                state, "statute_retrieval", "completed", started, output_count=len(evidence)
            ),
        }
    except Exception as exc:
        reasons, reason = _degrade(state, "statute_retrieval", exc)
        return {
            "statute_evidence": [],
            "degraded": True,
            "degradation_reasons": reasons,
            "trace": _append_trace(
                state, "statute_retrieval", "degraded", started, reason=reason
            ),
        }


def _statute_retrieval_node(
    state: LegalWorkflowState, runtime: Runtime[WorkflowRuntimeContext]
) -> dict[str, Any]:
    """法规必跑；路由需要案例时与独立案例库并行检索。"""
    decision = state.get("route_decision", RouteDecision())
    if not (decision.include_case and state.get("case_retriever_available", False)):
        return _statute_retrieval_once(state, runtime)

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="lexrag-retrieval") as executor:
        statute_future = executor.submit(_statute_retrieval_once, state, runtime)
        case_future = executor.submit(_case_retrieval_node, state, runtime)
        statute_update = statute_future.result()
        case_update = case_future.result()

    base_trace = state.get("trace", [])
    base_reasons = state.get("degradation_reasons", [])
    result: dict[str, Any] = {
        "statute_evidence": statute_update.get("statute_evidence", []),
        "case_evidence": case_update.get("case_evidence", []),
        "case_retrieval_completed": True,
        "trace": [
            *base_trace,
            *statute_update.get("trace", [])[len(base_trace) :],
            *case_update.get("trace", [])[len(base_trace) :],
        ],
    }
    degradation_reasons = [
        *base_reasons,
        *statute_update.get("degradation_reasons", [])[len(base_reasons) :],
        *case_update.get("degradation_reasons", [])[len(base_reasons) :],
    ]
    if statute_update.get("degraded") or case_update.get("degraded"):
        result["degraded"] = True
        result["degradation_reasons"] = degradation_reasons
    return result


def _case_retrieval_node(
    state: LegalWorkflowState, runtime: Runtime[WorkflowRuntimeContext]
) -> dict[str, Any]:
    started = perf_counter()
    try:
        results = runtime.context.case_retriever.retrieve(state["question"], top_k=3)
        evidence = [
            item
            for result in results or []
            if (item := _to_case_evidence(result)) is not None
        ]
        return {
            "case_evidence": evidence,
            "trace": _append_trace(
                state, "case_retrieval", "completed", started, output_count=len(evidence)
            ),
        }
    except Exception as exc:
        reasons, reason = _degrade(state, "case_retrieval", exc)
        return {
            "case_evidence": [],
            "degraded": True,
            "degradation_reasons": reasons,
            "trace": _append_trace(
                state, "case_retrieval", "degraded", started, reason=reason
            ),
        }


def _graph_retrieval_node(
    state: LegalWorkflowState, runtime: Runtime[WorkflowRuntimeContext]
) -> dict[str, Any]:
    started = perf_counter()
    statute_evidence = state.get("statute_evidence", [])
    try:
        if not statute_evidence:
            return {
                "graph_evidence": [],
                "trace": _append_trace(state, "graph_retrieval", "skipped", started),
            }
        seed = statute_evidence[0]
        graph = runtime.context.graph_retriever.retrieve(
            seed.normalized_article_id, max_hops=1
        )
        results = getattr(graph, "retrieved_articles", []) if graph else []
        evidence = [
            item
            for result in results
            if _graph_result_law_name(result) == seed.law_name
            and (
                item := _to_graph_evidence(result, seed.knowledge_base_slug)
            ) is not None
        ]
        return {
            "graph_evidence": evidence,
            "trace": _append_trace(
                state, "graph_retrieval", "completed", started, output_count=len(evidence)
            ),
        }
    except Exception as exc:
        reasons, reason = _degrade(state, "graph_retrieval", exc)
        return {
            "graph_evidence": [],
            "degraded": True,
            "degradation_reasons": reasons,
            "trace": _append_trace(
                state, "graph_retrieval", "degraded", started, reason=reason
            ),
        }


def _graph_result_law_name(result: Any) -> str:
    if isinstance(result, EvidenceItem):
        return result.law_name
    if isinstance(result, dict):
        return str(result.get("law_name", ""))
    return str(getattr(result, "law_name", ""))


def _evidence_ledger_node(state: LegalWorkflowState) -> dict[str, Any]:
    started = perf_counter()
    ledger = EvidenceLedger()
    for item in [
        *state.get("statute_evidence", []),
        *state.get("case_evidence", []),
        *state.get("graph_evidence", []),
    ]:
        ledger.add(item)
    evidence = ledger.items
    return {
        "evidence": evidence,
        "trace": _append_trace(
            state, "evidence_ledger", "completed", started, output_count=len(evidence)
        ),
    }


def _answer_node(
    state: LegalWorkflowState, runtime: Runtime[WorkflowRuntimeContext]
) -> dict[str, Any]:
    started = perf_counter()
    evidence = state.get("evidence", [])
    answer = runtime.context.answer_generator(state["question"], evidence, None)
    return {
        "answer": answer,
        "trace": _append_trace(
            state, "answer", "completed", started, input_count=len(evidence), output_count=1
        ),
    }


def _citation_verifier_node(
    state: LegalWorkflowState, runtime: Runtime[WorkflowRuntimeContext]
) -> dict[str, Any]:
    started = perf_counter()
    ledger = EvidenceLedger(state.get("evidence", []))
    verifier = runtime.context.citation_verifier or CitationVerifier()
    verification = verifier.verify(
        state.get("answer", ""),
        ledger,
        knowledge_base_slugs=_selected_knowledge_base_slugs(state),
    )
    return {
        "citations": verification.citations,
        "verification_status": verification.status,
        "verification_issues": verification.issues,
        "trace": _append_trace(
            state,
            "citation_verifier",
            "completed" if verification.status == "pass" else "failed",
            started,
            output_count=len(verification.citations),
        ),
    }


def _knowledge_base_routing_node(state: LegalWorkflowState) -> dict[str, Any]:
    """在图内记录已通过权限与版本校验的知识库范围。"""
    started = perf_counter()
    slugs = _selected_knowledge_base_slugs(state)
    return {
        "knowledge_base_route": {"selected_slugs": slugs},
        "trace": _append_trace(
            state, "knowledge_base_routing", "completed", started, output_count=len(slugs)
        ),
    }


def _repair_node(
    state: LegalWorkflowState, runtime: Runtime[WorkflowRuntimeContext]
) -> dict[str, Any]:
    started = perf_counter()
    issues = state.get("verification_issues", [])
    answer = runtime.context.answer_generator(
        state["question"], state.get("evidence", []), issues
    )
    return {
        "answer": answer,
        "verification_attempts": state.get("verification_attempts", 0) + 1,
        "trace": _append_trace(
            state, "repair", "completed", started, input_count=len(issues), output_count=1
        ),
    }


def _finalize_node(state: LegalWorkflowState) -> dict[str, Any]:
    started = perf_counter()
    return {
        "cacheable": True,
        "trace": _append_trace(state, "finalize", "completed", started),
    }


def _evidence_insufficient_node(state: LegalWorkflowState) -> dict[str, Any]:
    started = perf_counter()
    selected_slugs = set(_selected_knowledge_base_slugs(state))
    no_statutes = not any(
        item.source_type == "statute" and item.knowledge_base_slug in selected_slugs
        for item in state.get("evidence", [])
    )
    update: dict[str, Any] = {
        "answer": EVIDENCE_INSUFFICIENT_ANSWER,
        "cacheable": False,
        "trace": _append_trace(state, "evidence_insufficient", "completed", started),
    }
    if no_statutes:
        update.update(
            {
                "citations": [],
                "verification_status": "fail",
                "verification_issues": ["本次检索未获得可引用的法条证据"],
                "degraded": True,
            }
        )
    return update


def _after_statute_retrieval(state: LegalWorkflowState) -> str:
    decision = state.get("route_decision", RouteDecision())
    if (
        decision.include_case
        and state.get("case_retriever_available", False)
        and not state.get("case_retrieval_completed", False)
    ):
        return "case_retrieval"
    if (
        decision.include_graph
        and state.get("graph_retriever_available", False)
        and state.get("statute_evidence")
    ):
        return "graph_retrieval"
    return "evidence_ledger"


def _after_case_retrieval(state: LegalWorkflowState) -> str:
    decision = state.get("route_decision", RouteDecision())
    if (
        decision.include_graph
        and state.get("graph_retriever_available", False)
        and state.get("statute_evidence")
    ):
        return "graph_retrieval"
    return "evidence_ledger"


def _after_evidence_ledger(state: LegalWorkflowState) -> str:
    selected_slugs = set(_selected_knowledge_base_slugs(state))
    has_statute = any(
        item.source_type == "statute" and item.knowledge_base_slug in selected_slugs
        for item in state.get("evidence", [])
    )
    return "answer" if has_statute else "evidence_insufficient"


def _after_verification(state: LegalWorkflowState) -> str:
    if state.get("verification_status") == "pass":
        return "finalize"
    if state.get("verification_attempts", 0) == 0:
        return "repair"
    return "evidence_insufficient"


def _build_legal_evidence_graph() -> CompiledStateGraph:
    builder = StateGraph(LegalWorkflowState, context_schema=WorkflowRuntimeContext)
    builder.add_node("planning", _planning_node)
    builder.add_node("knowledge_base_routing", _knowledge_base_routing_node)
    builder.add_node("routing", _routing_node)
    builder.add_node("statute_retrieval", _statute_retrieval_node)
    builder.add_node("case_retrieval", _case_retrieval_node)
    builder.add_node("graph_retrieval", _graph_retrieval_node)
    builder.add_node("evidence_ledger", _evidence_ledger_node)
    builder.add_node("answer", _answer_node)
    builder.add_node("citation_verifier", _citation_verifier_node)
    builder.add_node("repair", _repair_node)
    builder.add_node("finalize", _finalize_node)
    builder.add_node("evidence_insufficient", _evidence_insufficient_node)

    builder.add_edge(START, "planning")
    builder.add_edge("planning", "knowledge_base_routing")
    builder.add_edge("knowledge_base_routing", "routing")
    builder.add_edge("routing", "statute_retrieval")
    builder.add_conditional_edges(
        "statute_retrieval",
        _after_statute_retrieval,
        {
            "case_retrieval": "case_retrieval",
            "graph_retrieval": "graph_retrieval",
            "evidence_ledger": "evidence_ledger",
        },
    )
    builder.add_conditional_edges(
        "case_retrieval",
        _after_case_retrieval,
        {
            "graph_retrieval": "graph_retrieval",
            "evidence_ledger": "evidence_ledger",
        },
    )
    builder.add_edge("graph_retrieval", "evidence_ledger")
    builder.add_conditional_edges(
        "evidence_ledger",
        _after_evidence_ledger,
        {"answer": "answer", "evidence_insufficient": "evidence_insufficient"},
    )
    builder.add_edge("answer", "citation_verifier")
    builder.add_conditional_edges(
        "citation_verifier",
        _after_verification,
        {
            "finalize": "finalize",
            "repair": "repair",
            "evidence_insufficient": "evidence_insufficient",
        },
    )
    builder.add_edge("repair", "citation_verifier")
    builder.add_edge("finalize", END)
    builder.add_edge("evidence_insufficient", END)
    return builder.compile(name="legal_evidence_workflow")


COMPILED_LEGAL_EVIDENCE_GRAPH = _build_legal_evidence_graph()


class LegalEvidenceWorkflow:
    """为请求级依赖提供兼容接口的 LangGraph 工作流门面。"""

    graph = COMPILED_LEGAL_EVIDENCE_GRAPH

    def __init__(
        self,
        *,
        law_retriever: Any,
        answer_generator: Callable[[str, list[EvidenceItem], list[str] | None], str],
        planner: Callable[[str], Any] | None = None,
        router: Callable[[str], RouteDecision | dict[str, Any] | str] | None = None,
        case_retriever: Any | None = None,
        graph_retriever: Any | None = None,
        citation_verifier: CitationVerifier | None = None,
    ) -> None:
        self.runtime_context = WorkflowRuntimeContext(
            law_retriever=law_retriever,
            answer_generator=answer_generator,
            planner=planner,
            router=router,
            case_retriever=case_retriever,
            graph_retriever=graph_retriever,
            citation_verifier=citation_verifier or CitationVerifier(),
        )

    def invoke(
        self,
        question: str,
        *,
        knowledge_base_slug: str | None = None,
        knowledge_base_slugs: Sequence[str] | None = None,
        conversation_context: Sequence[Mapping[str, Any]] | None = None,
        request_context: Mapping[str, Any] | None = None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
        is_cancel_requested: Callable[[], bool] | None = None,
    ) -> EvidenceWorkflowResult:
        runtime_context = self._runtime_context_for(request_context)
        initial_state = self._initial_state(
            question,
            knowledge_base_slug=knowledge_base_slug,
            knowledge_base_slugs=knowledge_base_slugs,
            conversation_context=conversation_context,
        )
        if event_sink is None:
            if is_cancel_requested and is_cancel_requested():
                raise QueryCancelled()
            final_state = self.graph.invoke(initial_state, context=runtime_context)
            return self._result_from_state(final_state)

        final_state = dict(initial_state)
        for update in self.graph.stream(initial_state, context=runtime_context, stream_mode="updates"):
            for node_update in update.values():
                if not isinstance(node_update, Mapping):
                    continue
                previous_trace = final_state.get("trace", [])
                final_state.update(node_update)
                trace = node_update.get("trace")
                if isinstance(trace, list) and trace:
                    for trace_event in trace[len(previous_trace) :]:
                        if isinstance(trace_event, Mapping):
                            event_sink(dict(trace_event))
            if is_cancel_requested and is_cancel_requested():
                raise QueryCancelled()
        return self._result_from_state(final_state)

    def query(
        self,
        question: str,
        *,
        knowledge_base_slug: str,
        conversation_context: Sequence[Mapping[str, Any]] | None = None,
        request_context: Mapping[str, Any] | None = None,
    ) -> EvidenceWorkflowResult:
        """兼容旧调用方；主编排由共享 LangGraph 执行。"""

        return self.invoke(
            question,
            knowledge_base_slug=knowledge_base_slug,
            conversation_context=conversation_context,
            request_context=request_context,
        )

    async def ainvoke(
        self,
        question: str,
        *,
        knowledge_base_slug: str,
        conversation_context: Sequence[Mapping[str, Any]] | None = None,
        request_context: Mapping[str, Any] | None = None,
    ) -> EvidenceWorkflowResult:
        runtime_context = self._runtime_context_for(request_context)
        final_state = await self.graph.ainvoke(
            self._initial_state(
                question,
                knowledge_base_slug=knowledge_base_slug,
                conversation_context=conversation_context,
            ),
            context=runtime_context,
        )
        return self._result_from_state(final_state)

    async def astream_events(
        self,
        question: str,
        *,
        knowledge_base_slug: str,
        conversation_context: Sequence[Mapping[str, Any]] | None = None,
        request_context: Mapping[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        runtime_context = self._runtime_context_for(request_context)
        started_at: dict[str, float] = {}
        async for raw_event in self.graph.astream_events(
            self._initial_state(
                question,
                knowledge_base_slug=knowledge_base_slug,
                conversation_context=conversation_context,
            ),
            context=runtime_context,
            version="v2",
        ):
            node = raw_event.get("name")
            if node not in WORKFLOW_NODE_NAMES:
                continue

            event_type = raw_event.get("event")
            run_id = str(raw_event.get("run_id", ""))
            if event_type == "on_chain_start":
                started_at[run_id] = perf_counter()
                yield {"event": "node_start", "node": node, "status": "started"}
                continue

            started = started_at.pop(run_id, perf_counter())
            duration_ms = max(round((perf_counter() - started) * 1000, 3), 0.0)
            if event_type == "on_chain_error":
                error = raw_event.get("data", {}).get("error")
                yield {
                    "event": "node_error",
                    "node": node,
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "reason": type(error).__name__,
                }
                continue

            if event_type != "on_chain_end":
                continue

            safe_event: dict[str, Any] = {
                "event": "node_end",
                "node": node,
                "status": "completed",
                "duration_ms": duration_ms,
            }
            data = raw_event.get("data")
            output = data.get("output") if isinstance(data, Mapping) else None
            trace = output.get("trace") if isinstance(output, Mapping) else None
            if isinstance(trace, list):
                node_trace = next(
                    (
                        item
                        for item in reversed(trace)
                        if isinstance(item, Mapping) and item.get("node") == node
                    ),
                    None,
                )
                if node_trace is not None:
                    status = node_trace.get("status")
                    if status in {"completed", "degraded", "failed"}:
                        safe_event["status"] = status
                    for count_key in ("input_count", "output_count"):
                        count = node_trace.get(count_key)
                        if isinstance(count, int) and count >= 0:
                            safe_event[count_key] = count
                    reason = node_trace.get("reason")
                    if isinstance(reason, str) and reason.isidentifier():
                        safe_event["reason"] = reason
            yield safe_event

    def _runtime_context_for(
        self, request_context: Mapping[str, Any] | None
    ) -> WorkflowRuntimeContext:
        request_context = request_context or {}
        return WorkflowRuntimeContext(
            law_retriever=self.runtime_context.law_retriever,
            answer_generator=self.runtime_context.answer_generator,
            planner=self.runtime_context.planner,
            router=self.runtime_context.router,
            case_retriever=self.runtime_context.case_retriever,
            graph_retriever=self.runtime_context.graph_retriever,
            citation_verifier=self.runtime_context.citation_verifier,
            user_id=request_context.get("user_id"),
            organization_id=request_context.get("organization_id"),
            session_id=request_context.get("session_id"),
            model_id=request_context.get("model_id"),
        )

    def _initial_state(
        self,
        question: str,
        *,
        knowledge_base_slug: str | None,
        knowledge_base_slugs: Sequence[str] | None = None,
        conversation_context: Sequence[Mapping[str, Any]] | None,
    ) -> LegalWorkflowState:
        slugs = list(dict.fromkeys(slug for slug in (knowledge_base_slugs or []) if slug))
        if knowledge_base_slug and knowledge_base_slug not in slugs:
            slugs.insert(0, knowledge_base_slug)
        if not slugs:
            raise ValueError("至少需要一个知识库")
        return {
            "question": question,
            "knowledge_base_slug": slugs[0],
            "knowledge_base_slugs": slugs,
            "knowledge_base_route": {"selected_slugs": slugs},
            "conversation_context": [dict(turn) for turn in conversation_context or []],
            "sub_questions": [{"question": question, "depends_on": ""}],
            "route_decision": RouteDecision(),
            "statute_evidence": [],
            "case_evidence": [],
            "graph_evidence": [],
            "evidence": [],
            "answer": "",
            "citations": [],
            "verification_status": "fail",
            "verification_issues": [],
            "verification_attempts": 0,
            "degraded": False,
            "degradation_reasons": [],
            "trace": [],
            "cacheable": False,
            "case_retriever_available": self.runtime_context.case_retriever is not None,
            "graph_retriever_available": self.runtime_context.graph_retriever is not None,
            "case_retrieval_completed": False,
        }

    @staticmethod
    def _result_from_state(state: LegalWorkflowState) -> EvidenceWorkflowResult:
        return EvidenceWorkflowResult(
            query=state["question"],
            answer=state.get("answer", ""),
            intent=state.get("route_decision", RouteDecision()).intent,
            citations=state.get("citations", []),
            verification_status=state.get("verification_status", "fail"),
            verification_issues=state.get("verification_issues", []),
            sub_questions=state.get("sub_questions", []),
            metadata={
                "workflow_version": "evidence-v3.0",
                "orchestration_engine": "langgraph-stategraph",
                "workflow_status": "degraded" if state.get("degraded") else "completed",
                "verification_attempts": state.get("verification_attempts", 0),
                "evidence_count": len(state.get("evidence", [])),
                "verification_summary": state.get("verification_status", "fail"),
                "workflow_trace": state.get("trace", []),
                "degradation_reasons": state.get("degradation_reasons", []),
                "cacheable": state.get("cacheable", False),
            },
        )
