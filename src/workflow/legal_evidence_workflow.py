"""固定节点的 v2.1 证据驱动法律工作流。"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Iterable

from .evidence import CitationVerifier, EvidenceItem, EvidenceLedger, VerifiedCitation


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


class QueryEnhancedLawRetriever:
    """复用 v2.0 的多候选改写、HyDE 与 RRF 检索，失败时只查原问题。"""

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


class LegalEvidenceWorkflow:
    """以固定节点替代 ReAct 自主工具调用的法律问答工作流。"""

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
        self.law_retriever = law_retriever
        self.answer_generator = answer_generator
        self.planner = planner
        self.router = router
        self.case_retriever = case_retriever
        self.graph_retriever = graph_retriever
        self.citation_verifier = citation_verifier or CitationVerifier()

    def query(self, question: str, *, knowledge_base_slug: str) -> EvidenceWorkflowResult:
        trace: list[dict[str, Any]] = []
        degraded = False
        sub_questions = [{"question": question, "depends_on": ""}]

        if self._is_complex(question) and self.planner is not None:
            started = perf_counter()
            try:
                planned = self.planner(question)
                sub_questions = self._normalize_plan(planned, question)
                self._add_trace(
                    trace,
                    "planning",
                    "completed",
                    started,
                    output_count=len(sub_questions),
                )
            except Exception as exc:
                degraded = True
                self._add_trace(trace, "planning", "degraded", started, reason=type(exc).__name__)
        else:
            started = perf_counter()
            self._add_trace(trace, "planning", "skipped", started)

        started = perf_counter()
        try:
            decision = self._route(question)
            self._add_trace(trace, "routing", "completed", started, output_count=1)
        except Exception as exc:
            degraded = True
            decision = RouteDecision()
            self._add_trace(trace, "routing", "degraded", started, reason=type(exc).__name__)

        ledger = EvidenceLedger()
        started = perf_counter()
        try:
            law_results = self.law_retriever.retrieve(question, top_k=5)
            for result in law_results or []:
                item = self._to_statute_evidence(result, knowledge_base_slug)
                if item is not None:
                    ledger.add(item)
            self._add_trace(
                trace,
                "statute_retrieval",
                "completed",
                started,
                output_count=len(ledger.statutes_for(knowledge_base_slug)),
            )
        except Exception as exc:
            degraded = True
            self._add_trace(trace, "statute_retrieval", "degraded", started, reason=type(exc).__name__)

        if decision.include_case and self.case_retriever is not None:
            started = perf_counter()
            try:
                cases = self.case_retriever.retrieve(question, top_k=3)
                case_count = 0
                for case in cases or []:
                    item = self._to_case_evidence(case)
                    if item is not None and ledger.add(item):
                        case_count += 1
                self._add_trace(trace, "case_retrieval", "completed", started, output_count=case_count)
            except Exception as exc:
                degraded = True
                self._add_trace(trace, "case_retrieval", "degraded", started, reason=type(exc).__name__)

        if decision.include_graph and self.graph_retriever is not None and ledger.items:
            started = perf_counter()
            try:
                graph = self.graph_retriever.retrieve(ledger.items[0].normalized_article_id)
                graph_items = getattr(graph, "retrieved_articles", []) if graph else []
                graph_count = 0
                for graph_item in graph_items:
                    item = self._to_graph_evidence(graph_item, knowledge_base_slug)
                    if item is not None and ledger.add(item):
                        graph_count += 1
                self._add_trace(trace, "graph_retrieval", "completed", started, output_count=graph_count)
            except Exception as exc:
                degraded = True
                self._add_trace(trace, "graph_retrieval", "degraded", started, reason=type(exc).__name__)

        started = perf_counter()
        evidence = ledger.items
        self._add_trace(trace, "evidence_ledger", "completed", started, output_count=len(evidence))

        statutes = ledger.statutes_for(knowledge_base_slug)
        if not statutes:
            return self._result(
                question=question,
                answer="现有证据不足以支持可靠结论。请补充事实、选择相关知识库，或咨询专业律师。",
                intent=decision.intent,
                citations=[],
                verification_status="fail",
                verification_issues=["本次检索未获得可引用的法条证据"],
                sub_questions=sub_questions,
                trace=trace,
                evidence_count=len(evidence),
                verification_attempts=0,
                degraded=True,
                cacheable=False,
            )

        started = perf_counter()
        answer = self.answer_generator(question, evidence, None)
        self._add_trace(trace, "answer", "completed", started, input_count=len(evidence), output_count=1)

        started = perf_counter()
        verification = self.citation_verifier.verify(
            answer,
            ledger,
            knowledge_base_slug=knowledge_base_slug,
        )
        self._add_trace(
            trace,
            "citation_verifier",
            "completed" if verification.status == "pass" else "failed",
            started,
            output_count=len(verification.citations),
        )

        verification_attempts = 0
        if verification.status != "pass":
            verification_attempts = 1
            started = perf_counter()
            answer = self.answer_generator(question, evidence, verification.issues)
            self._add_trace(trace, "repair", "completed", started, input_count=len(verification.issues), output_count=1)

            started = perf_counter()
            verification = self.citation_verifier.verify(
                answer,
                ledger,
                knowledge_base_slug=knowledge_base_slug,
            )
            self._add_trace(
                trace,
                "citation_verifier",
                "completed" if verification.status == "pass" else "failed",
                started,
                output_count=len(verification.citations),
            )

        if verification.status != "pass":
            answer = "现有证据不足以支持可靠结论。请补充事实、选择相关知识库，或咨询专业律师。"

        return self._result(
            question=question,
            answer=answer,
            intent=decision.intent,
            citations=verification.citations,
            verification_status=verification.status,
            verification_issues=verification.issues,
            sub_questions=sub_questions,
            trace=trace,
            evidence_count=len(evidence),
            verification_attempts=verification_attempts,
            degraded=degraded,
            cacheable=verification.status == "pass",
        )

    def _route(self, question: str) -> RouteDecision:
        if self.router is None:
            return RouteDecision()
        result = self.router(question)
        if isinstance(result, RouteDecision):
            return result
        if isinstance(result, dict):
            return RouteDecision(**result)
        if isinstance(result, str):
            return RouteDecision(intent=result)
        raise TypeError("router must return RouteDecision, dict, or str")

    @staticmethod
    def _is_complex(question: str) -> bool:
        return len(question) > 80 or any(marker in question for marker in ("并且", "同时", "分别", "流程", "以及"))

    @staticmethod
    def _normalize_plan(planned: Any, fallback_question: str) -> list[dict[str, str]]:
        if not isinstance(planned, Iterable) or isinstance(planned, (str, bytes, dict)):
            return [{"question": fallback_question, "depends_on": ""}]
        items = []
        for item in planned:
            if isinstance(item, str) and item.strip():
                items.append({"question": item.strip(), "depends_on": ""})
            elif isinstance(item, dict) and str(item.get("question", "")).strip():
                items.append({
                    "question": str(item["question"]).strip(),
                    "depends_on": str(item.get("depends_on", "")),
                })
        return items or [{"question": fallback_question, "depends_on": ""}]

    @staticmethod
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

    @staticmethod
    def _to_case_evidence(result: Any) -> EvidenceItem | None:
        if isinstance(result, EvidenceItem):
            return result
        source_id = str(getattr(result, "case_id", ""))
        content = str(
            getattr(result, "summary", "")
            or getattr(result, "judgment_result", "")
            or ""
        )
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

    @staticmethod
    def _to_graph_evidence(result: Any, knowledge_base_slug: str) -> EvidenceItem | None:
        if isinstance(result, EvidenceItem):
            return result
        if not isinstance(result, dict):
            return None
        article_id = str(result.get("article_id", ""))
        content = str(result.get("content", ""))
        if not article_id:
            return None
        return EvidenceItem(
            source_id=article_id,
            source_type="graph",
            knowledge_base_slug=knowledge_base_slug,
            law_name=str(result.get("law_name", "")),
            article_id=article_id,
            content=content,
            score=1.0,
            retrieval_path="graph",
        )

    @staticmethod
    def _add_trace(
        trace: list[dict[str, Any]],
        node: str,
        status: str,
        started: float,
        *,
        input_count: int = 0,
        output_count: int = 0,
        reason: str | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "node": node,
            "status": status,
            "duration_ms": round((perf_counter() - started) * 1000, 3),
            "input_count": input_count,
            "output_count": output_count,
        }
        if reason:
            event["reason"] = reason
        trace.append(event)

    @staticmethod
    def _result(
        *,
        question: str,
        answer: str,
        intent: str,
        citations: list[VerifiedCitation],
        verification_status: str,
        verification_issues: list[str],
        sub_questions: list[dict[str, str]],
        trace: list[dict[str, Any]],
        evidence_count: int,
        verification_attempts: int,
        degraded: bool,
        cacheable: bool,
    ) -> EvidenceWorkflowResult:
        return EvidenceWorkflowResult(
            query=question,
            answer=answer,
            intent=intent,
            citations=citations,
            verification_status=verification_status,
            verification_issues=verification_issues,
            sub_questions=sub_questions,
            metadata={
                "workflow_version": "evidence-v2.1",
                "workflow_status": "degraded" if degraded else "completed",
                "verification_attempts": verification_attempts,
                "evidence_count": evidence_count,
                "verification_summary": verification_status,
                "workflow_trace": trace,
                "cacheable": cacheable,
            },
        )
