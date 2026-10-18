"""LangGraph 驱动的证据优先法律问答工作流。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
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


class QueryEnhancedLawRetriever:
    """复用多候选改写、HyDE 与 RRF 检索，失败时只查原问题。"""

    def __init__(self, law_retriever: Any, query_rewriter: Any | None = None) -> None:
        self.law_retriever = law_retriever
        self.query_rewriter = query_rewriter

    def retrieve(self, question: str, *, top_k: int = 5) -> Any:
        if self.query_rewriter is None:
            return self.law_retriever.retrieve(question, top_k=top_k)
        try:
            rewritten = self.query_rewriter.rewrite_candidates(question)
            search_queries = getattr(rewritten, "search_queries", None) or [question]
            hyde_query = self.query_rewriter.generate_hyde(question)
            return self.law_retriever.retrieve_multi_query(
                search_queries,
                hyde_query=hyde_query,
                top_k=top_k,
            )
        except Exception:
            return self.law_retriever.retrieve(question, top_k=top_k)


def _is_complex(question: str) -> bool:
    return len(question) > 80 or any(
        marker in question for marker in ("并且", "同时", "分别", "流程", "以及")
    )


def _normalize_plan(planned: Any, fallback_question: str) -> list[dict[str, str]]:
    if not isinstance(planned, Iterable) or isinstance(planned, (str, bytes, dict)):
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
    article_id = str(getattr(result, "article_number", "") or getattr(result, "article_id", ""))
    law_name = str(getattr(result, "law_name", ""))
    content = str(getattr(result, "full_content", "") or getattr(result, "content", ""))
    source_id = str(getattr(result, "chunk_id", "") or getattr(result, "article_id", ""))
    if not all((article_id, law_name, content, source_id)):
        return None
    return EvidenceItem(
        source_id=source_id,
        source_type="statute",
        knowledge_base_slug=knowledge_base_slug,
        law_name=law_name,
        article_id=article_id,
        content=content,
        score=float(getattr(result, "score", 0.0) or 0.0),
        retrieval_path="statute",
    )


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


def _statute_retrieval_node(
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
        graph = runtime.context.graph_retriever.retrieve(
            statute_evidence[0].normalized_article_id
        )
        results = getattr(graph, "retrieved_articles", []) if graph else []
        evidence = [
            item
            for result in results
            if (item := _to_graph_evidence(result, state["knowledge_base_slug"])) is not None
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
        knowledge_base_slug=state["knowledge_base_slug"],
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
    no_statutes = not any(
        item.source_type == "statute"
        and item.knowledge_base_slug == state["knowledge_base_slug"]
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
    if decision.include_case and state.get("case_retriever_available", False):
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
    has_statute = any(
        item.source_type == "statute"
        and item.knowledge_base_slug == state["knowledge_base_slug"]
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
    builder.add_edge("planning", "routing")
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
        knowledge_base_slug: str,
        conversation_context: Sequence[Mapping[str, Any]] | None = None,
        request_context: Mapping[str, Any] | None = None,
    ) -> EvidenceWorkflowResult:
        runtime_context = self._runtime_context_for(request_context)
        final_state = self.graph.invoke(
            self._initial_state(
                question,
                knowledge_base_slug=knowledge_base_slug,
                conversation_context=conversation_context,
            ),
            context=runtime_context,
        )
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
        async for event in self.graph.astream_events(
            self._initial_state(
                question,
                knowledge_base_slug=knowledge_base_slug,
                conversation_context=conversation_context,
            ),
            context=runtime_context,
            version="v2",
        ):
            yield event

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
        knowledge_base_slug: str,
        conversation_context: Sequence[Mapping[str, Any]] | None,
    ) -> LegalWorkflowState:
        return {
            "question": question,
            "knowledge_base_slug": knowledge_base_slug,
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
