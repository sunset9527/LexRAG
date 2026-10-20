# LexRAG Stage 0/1 Closure Completion Plan

**Design:** `docs/superpowers/specs/2026-10-19-stage-0-1-closure-completion-design.md`

**Implementation:** `32ad4ed` (`fix(workflow): close stage 1 acceptance gaps`)

**Goal:** Close the remaining Stage 0/1 engineering-acceptance gaps, excluding résumé wording, without changing retrieval or legal-answer semantics.

## Task 1: Complete workflow branch acceptance tests

### Tests first

Extend `tests/test_evidence_workflow.py` one behavior at a time and observe each intended failure:

- complex planning normalizes and preserves planner output;
- planner failure falls back to the original question and records only a safe exception type;
- empty statute results terminate before answer generation and are non-cacheable;
- a statute retriever exception terminates safely and records no exception message;
- conversation history never appears in evidence, answer-generator evidence, result metadata, or the safe trace.

### Minimal implementation

Change graph code only if a new test reveals a behavioral defect. Existing passing behavior should be documented by the new regression test without unnecessary production edits.

Run after each test:

```powershell
python -m pytest tests/test_evidence_workflow.py -q
```

## Task 2: Replace the raw LangGraph event stream

### Tests first

Replace the existing raw-event smoke assertion with an explicit safe-contract test. It must fail while `astream_events()` forwards raw LangGraph dictionaries. Assert that:

- only allowlisted keys are present;
- only known workflow nodes are emitted;
- start and terminal lifecycle events remain observable;
- question and history sentinels never appear in serialized events;
- raw `data`, `input`, `output`, and `metadata` keys never appear.

### Minimal implementation

In `src/workflow/legal_evidence_workflow.py`, translate raw node events into normalized structural events. Filter graph-level and unknown events. Track node start times by run identifier so completion events can include non-negative duration. Derive degraded status and safe reason only from the node's structural trace update; never forward raw state or exception messages.

Run the workflow suite until green, then refactor duplicated constants or translation helpers without widening the contract.

## Task 3: Align the active workflow marker

Add a focused source or initialization assertion only if an existing API contract can exercise the marker without brittle implementation inspection. Change the internal readiness marker in `api.py` from `evidence-v2.1` to `evidence-v3.0` and update the adjacent comment to describe the Stage 1 StateGraph facade.

Run the relevant API initialization and health tests.

## Task 4: Run focused engineering gates

Run:

```powershell
python -m ruff check src/workflow/legal_evidence_workflow.py api.py tests/test_evidence_workflow.py
python -m pytest tests/test_evidence_workflow.py -q
python -m pytest tests/test_api_query_workflow.py tests/test_api_cache.py tests/test_session_memory.py tests/test_workflow_evaluation.py -q
```

If paths differ, select the existing Stage 1 focused tests by repository search and record the exact command used. Fix only regressions caused by this closure.

## Task 5: Reconcile documentation

After the focused checks pass:

- update `RAG法律.md` current capability matrix, v2.1 section, version table, timeline, footer status, and update date;
- preserve dated Stage 0 descriptions as historical facts while making their temporal boundary explicit;
- update `docs/status/v3.0-closure-baseline.md`, `docs/status/feature-ledger.md`, and Stage 1 completion evidence where needed;
- state that the safe iterator is not yet the Stage 6 HTTP streaming endpoint;
- retain the Stage 8 evaluation disclaimer;
- do not edit any résumé.

Search for stale active-status claims and distinguish legitimate historical design text from current documentation.

## Task 6: Full verification and commits

Run:

```powershell
python -m pytest -q
git diff --check
git status --short
```

Record exact pass counts, warnings, and coverage reported by the existing suite. Review the diff for secrets, private sentinel text, evaluation-data changes, and résumé modifications.

Create cohesive local commits for:

1. tests and event-stream/API implementation;
2. Stage 0/1 documentation reconciliation.

Do not push, rewrite history, run formal Stage 8 evaluation, or claim production readiness.

## Completion evidence

- Changed-file Ruff: passed.
- Workflow regression: 21 passed.
- Workflow/API/cache/session/evaluation focused regression: 35 passed with 3 warnings.
- Full backend regression with repository-local `--basetemp`: 243 passed, 68% coverage, 50 warnings.
- No résumé, evaluation data, labels, retrieval algorithm, or Prompt was modified.
- Formal legal-effect evaluation remains reserved for Stage 8.
