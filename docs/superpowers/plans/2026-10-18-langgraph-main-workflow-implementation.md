# LexRAG v3.0 Stage 1 LangGraph Implementation Plan

**Design:** `docs/superpowers/specs/2026-10-18-langgraph-main-workflow-design.md`

**Goal:** Replace the active sequential workflow orchestration with one reusable compiled LangGraph `StateGraph` without changing retrieval, prompt, evidence, verification, cache, or response semantics.

## Task 1: Establish the graph structure contract

### Tests first

Extend `tests/test_evidence_workflow.py` with focused assertions that:

- an exported `COMPILED_LEGAL_EVIDENCE_GRAPH` is a LangGraph `CompiledStateGraph`;
- its graph contains the approved named nodes;
- multiple `LegalEvidenceWorkflow` instances reference the same compiled graph;
- a verified run reports `orchestration_engine=langgraph-stategraph` and reaches `finalize`.

Run only these tests and confirm they fail because the graph export, node topology, and metadata do not yet exist.

### Minimal implementation

In `src/workflow/legal_evidence_workflow.py`:

- define typed `LegalWorkflowState` and `WorkflowRuntimeContext` contracts;
- add node functions and conditional-routing functions;
- build and compile the module-level graph once;
- expose the shared graph through the workflow facade;
- implement `invoke()` and make `query()` delegate to it;
- convert final state back to the existing `EvidenceWorkflowResult`.

Run the focused tests until green, then run all existing evidence-workflow tests to catch semantic drift.

## Task 2: Prove all deterministic branches

### Tests first

Add or refine one behavior test at a time for:

- planning success and planning degradation;
- router-selected case and graph paths;
- router and optional-retriever degradation;
- empty and failed statute retrieval terminating before answer generation;
- one failed verification followed by successful repair;
- a second verification failure terminating as evidence-insufficient;
- a private question never appearing in the workflow trace;
- conversation context never becoming an evidence item.

Each new test must be run and observed failing for the intended missing or incorrect graph behavior before production changes.

### Minimal implementation

Adjust only the node/state transitions required by the failing test. Preserve existing evidence conversion helpers, `CitationVerifier`, `EvidenceLedger`, answer text, and response dataclasses.

After each green cycle, rerun `tests/test_evidence_workflow.py`.

## Task 3: Add async and event-stream graph entry points

### Tests first

Add tests that:

- `ainvoke()` returns the same result contract as `invoke()`;
- `astream_events()` yields LangGraph events containing the approved graph/node names;
- neither interface exposes request secrets through result metadata or the safe workflow trace.

Confirm failure because these facade methods do not exist.

### Minimal implementation

Add thin `ainvoke()` and `astream_events()` wrappers around the shared compiled graph. Reuse the same initial-state and runtime-context builders as synchronous invocation; do not duplicate orchestration.

## Task 4: Switch the active API path

### Tests first

Update or add an API contract test using a complete workflow test double that exposes `invoke()`. Assert that `/query` calls `invoke()` with:

- the selected knowledge-base slug;
- session conversation context;
- non-secret user, organization, session, and model identifiers.

Assert that existing cache-hit behavior does not invoke the graph and that failed verification remains non-cacheable. Observe the active-path test fail while `api.py` still calls `query()`.

### Minimal implementation

Change the cache-miss path in `api.py` to call `workflow.invoke(...)`. Keep response conversion, cache storage, session persistence, and observability outside the graph. Do not place API keys or custom Base URLs in graph state or result metadata.

Run query, cache, session, and evidence-workflow focused tests.

## Task 5: Dependency and compatibility cleanup

### Tests first

Add a dependency-contract assertion only if repository tooling already tests requirement bounds. Otherwise validate imports and installed APIs through the focused suite rather than adding a brittle text test.

### Implementation

- tighten the LangGraph requirement to the supported major/minor API needed by `context_schema` and per-run context;
- keep the legacy ReAct module clearly marked non-active unless reference inspection and tests justify deletion;
- remove obsolete comments that describe the active path as ordinary Python orchestration.

## Task 6: Verification and truthful documentation

Run, in order:

1. Ruff over changed Python files.
2. `tests/test_evidence_workflow.py`.
3. Query/cache/session/workflow evaluation focused tests.
4. Full backend test suite with an explicit repository-local pytest temp directory.

Record exact pass counts, warnings, and failures. Do not run or cite formal legal-quality evaluation.

After tests pass:

- update README architecture and quality facts;
- update `docs/status/v3.0-closure-baseline.md` as historical Stage 0 context plus Stage 1 follow-up;
- update `docs/status/feature-ledger.md`;
- update the external `RAG法律.md` Stage 1 execution status;
- archive Stage 1 planning files and remove them from the repository root;
- run `git diff --check`, inspect the final diff, commit cohesive code/tests and documentation locally, and verify a clean worktree.

## Non-negotiable checks

- No production code is written before its failing test.
- No API key, Base URL, prompt, question text, or document content enters the workflow trace.
- No graph or dependency cache is keyed by mutable credentials.
- No second repair edge exists.
- No evaluation data or labels are changed.
- No remote push or history rewrite occurs.
