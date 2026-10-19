# LexRAG v3.0 Stage 1: LangGraph Main Workflow Design

**Date:** 2026-10-18

**Status:** Implemented in `697a2d8`

## 1. Objective

Replace the active deterministic Python orchestration inside `LegalEvidenceWorkflow` with a real LangGraph `StateGraph` while preserving the existing evidence-first business semantics and the public `/query` response contract.

The migration must make the implementation, runtime trace, and documentation agree that the main legal-query path uses LangGraph. It must not reintroduce autonomous ReAct tool selection, multi-agent conversation, or unrelated changes to retrieval, prompts, datasets, authorization, or legal-answer evaluation.

## 2. Current state

`POST /query` currently creates request-scoped retrieval and LLM components, constructs `LegalEvidenceWorkflow`, and calls its ordinary Python `query()` method. That method performs planning, routing, retrieval, evidence normalization, answer generation, citation verification, and one repair attempt through sequential control flow.

The code under `src/agent/` uses `create_react_agent`, but it is a legacy path and does not serve the active `/query` endpoint. Its existence is not evidence that the main path uses LangGraph.

The installed baseline contains LangGraph 1.2.7 and LangChain 1.3.11. Stage 1 targets the typed `StateGraph(state_schema, context_schema=...)` and per-run `context` APIs present in that environment.

## 3. Scope and compatibility

### In scope

- a typed `LegalWorkflowState` for per-invocation data;
- a typed `WorkflowRuntimeContext` for request-scoped dependencies and identifiers;
- independently testable graph nodes and explicit conditional edges;
- one module-level compiled graph reused across workflow instances;
- synchronous, asynchronous, and event-stream graph entry points;
- switching `/query` to an explicit graph invocation path;
- structural and behavioral tests for the graph and API integration;
- truthful Stage 1 documentation after verification.

### Out of scope

- changing retrieval algorithms, prompts, chunking, embeddings, ranking, or evaluation datasets;
- adding a second repair attempt or changing citation-verification rules;
- changing authorization, SSRF controls, logging policy, upload protection, or persistent query ownership, which belong to Stage 2;
- introducing checkpoint persistence, human-in-the-loop interrupts, or cross-request graph memory;
- performing paid LLM evaluation or publishing legal-answer quality claims;
- restoring the legacy ReAct workflow to the active path.

`LegalEvidenceWorkflow.query()` remains available as a compatibility adapter. Existing response fields keep their meanings. Trace entries may add the explicit terminal node `finalize` or `evidence_insufficient`, and metadata will identify the orchestration engine as `langgraph-stategraph`.

## 4. Selected architecture

Compile one stateless graph at module load and pass all request-scoped collaborators through LangGraph runtime context:

```text
POST /query
  -> construct request-scoped retrievers and LLM-backed callables
  -> construct WorkflowRuntimeContext
  -> LegalEvidenceWorkflow.invoke(...)
  -> shared CompiledStateGraph.invoke(state, context=runtime_context)
  -> EvidenceWorkflowResult
```

This avoids compiling a graph for each API request and avoids caching graphs by knowledge base or model configuration. It also prevents mutable module-level registries from carrying API keys, knowledge-base selection, user identity, or request state across concurrent requests.

The compiled graph contains node functions only. Nodes read dependencies from the current `Runtime[WorkflowRuntimeContext]` and return state updates. They do not close over a workflow instance.

## 5. State and runtime context

### `LegalWorkflowState`

The graph state contains only data for one invocation:

- `question` and `knowledge_base_slug`;
- `conversation_context`, used only as non-evidence context and never inserted into the evidence ledger;
- `sub_questions` and normalized `RouteDecision`;
- statute, case, and graph retrieval candidates;
- normalized evidence items representing the current-run ledger;
- `answer`, verified citations, verification status, and verification issues;
- `verification_attempts`, limited to zero or one;
- `degraded` and structured degradation reasons;
- safe node trace entries containing node name, status, duration, input/output counts, and exception type where applicable;
- terminal result metadata.

The state does not contain API keys, prompts, model chain-of-thought, or a persistent cross-request registry. The question is necessary for node execution but must never be copied into trace events.

### `WorkflowRuntimeContext`

The per-run context contains:

- law, case, and graph retrievers;
- planner, router, answer generator, and citation verifier;
- non-secret request identifiers such as user, organization, and session IDs when supplied;
- a non-secret runtime model identifier;
- optional invocation metadata required by the API adapter.

The API key and custom Base URL stay encapsulated in the already-constructed request-scoped LLM/retriever objects. They are not duplicated into state, trace, result metadata, or module-level variables.

## 6. Graph topology

```text
START
  -> planning
  -> routing
  -> statute_retrieval
  -> optional case_retrieval
  -> optional graph_retrieval
  -> evidence_ledger
       | no valid statute
       v
     evidence_insufficient -> END

       | valid statute
       v
     answer
       -> citation_verifier
            | pass
            v
          finalize -> END

            | fail and verification_attempts == 0
            v
          repair -> citation_verifier

            | fail and verification_attempts == 1
            v
          evidence_insufficient -> END
```

Statute retrieval is mandatory. Conditional edges determine whether the case and graph nodes execute. If both are requested, case retrieval runs before graph retrieval to preserve deterministic ordering. Graph retrieval may use the first valid statute evidence item, matching the current behavior.

The repair edge can be traversed at most once. The graph has no edge from `evidence_insufficient` back to generation or retrieval.

## 7. Node contracts

### Planning

For a simple question or absent planner, emit a `skipped` trace and preserve the original question as the sole sub-question. For a complex question, normalize planner output through the existing rules. Planner failure marks the run degraded, records only the exception type, and falls back to the original question.

### Routing

Normalize existing `RouteDecision`, dictionary, and string outputs. Router failure marks the run degraded and falls back to factual, statute-only routing.

### Retrieval nodes

The statute node always calls the scoped law retriever and converts results through the existing evidence conversion rules. Case and graph nodes run only when selected and available. Retrieval failures mark the run degraded and return an empty update for that source rather than exposing exception messages or query text.

### Evidence ledger

Create a fresh `EvidenceLedger` for the invocation, add the current node outputs, and emit its normalized items and counts. Conversation history must not be added. If the selected knowledge base has no valid statute evidence, route directly to `evidence_insufficient` before answer generation.

### Answer and repair

The answer node calls the existing answer generator with no verification issues. The repair node calls the same generator with the first verifier issue list and increments `verification_attempts` to one. Both use the exact same current-run evidence items.

### Citation verifier

Reconstruct or consume the current-run ledger and apply the existing `CitationVerifier`. It emits verification status, verified citations, issue strings, and a safe trace event. It does not retrieve new evidence.

### Finalize and evidence-insufficient

`finalize` marks a verified result cacheable and records completion. `evidence_insufficient` sets the existing fixed user-facing fallback, marks the result non-cacheable, and preserves the verifier status/issues or the no-statute issue that caused the terminal route.

## 8. Public interfaces

`LegalEvidenceWorkflow` remains the dependency-assembly facade and exposes:

- `invoke(question, *, knowledge_base_slug, conversation_context=None, request_context=None)` as the primary synchronous graph path;
- `ainvoke(...)` as the asynchronous equivalent;
- `astream_events(...)` as a thin event-stream wrapper for Stage 6 consumers;
- `query(...)` as a compatibility alias that delegates to `invoke(...)`.

All methods build fresh initial state and runtime context. The compiled graph object is shared and immutable after construction.

`POST /query` will call `invoke()` explicitly so source inspection and runtime tests both prove that the endpoint enters the compiled graph. It will pass conversation history separately from evidence and pass non-secret request identifiers. Existing response construction, session persistence, cache reads/writes, and observability remain outside the graph.

## 9. Error and degradation behavior

- Planning, routing, case retrieval, and graph retrieval errors degrade safely and continue when statute evidence permits.
- A statute-retrieval error becomes an empty statute result and therefore terminates as evidence-insufficient.
- Unexpected answer-generator or verifier exceptions continue to propagate to the existing API boundary; Stage 1 does not silently redefine API error behavior.
- Exactly one citation repair is permitted.
- A second verification failure always terminates as evidence-insufficient and is never cacheable.
- Trace events contain exception class names only, never exception messages, questions, prompts, document text, credentials, or chain-of-thought.

## 10. Test strategy

Implementation follows red-green-refactor cycles. Tests are added before production changes and must be observed failing for the intended missing behavior.

Structural tests must prove:

- the exported object is a compiled LangGraph graph;
- the expected named nodes and conditional topology exist;
- multiple workflow facade instances share the same compiled graph;
- `query()` delegates to the graph-backed invocation path;
- metadata identifies `langgraph-stategraph`.

Behavioral tests must cover:

- a simple verified statute-only path;
- complex planning and safe planner degradation;
- route-selected case and graph retrieval;
- routing and optional-retrieval failures;
- empty or failed statute retrieval;
- first verification failure followed by successful repair;
- second verification failure followed by evidence-insufficient output;
- safe trace content that does not contain the supplied private question;
- conversation context remaining outside the evidence ledger;
- `ainvoke()` parity and an event-stream smoke contract.

API tests must prove that `/query` uses the graph entry point and preserves cache, session, response, and failure-to-cache behavior.

Final verification consists of Ruff, the focused workflow/API tests, and the complete backend suite. Stage 1 does not run the formal legal-quality evaluation reserved for Stage 8.

## 11. Documentation and legacy handling

After verification, README, the Stage 0 baseline follow-up, feature ledger, and external roadmap may state that `/query` uses a LangGraph `StateGraph`, citing the Stage 1 commit and test evidence.

The legacy `src/agent/` ReAct implementation will not be deleted during this migration unless repository-wide reference checks prove it has no callers and deletion is separately tested. At minimum, its module documentation and public project documentation must continue to label it as non-active legacy code.

## 12. Acceptance criteria

Stage 1 is complete only when all of the following hold:

- `/query` reaches an exported compiled LangGraph `StateGraph` through `invoke()`;
- the graph contains explicit planning, routing, statute retrieval, optional case/graph retrieval, ledger, answer, verifier, repair, finalize, and evidence-insufficient nodes;
- statutes remain mandatory, optional sources remain conditional, and repair remains limited to one attempt;
- current-run evidence is the only source of verifiable citations;
- conversation history cannot enter the evidence ledger;
- failed verification and missing statute evidence remain non-cacheable;
- request-scoped dependencies and identifiers do not leak through module-level mutable state;
- traces remain structural and privacy-safe;
- focused and full automated verification pass;
- documentation makes no Stage 8 quality claim and accurately names the active orchestration engine.
