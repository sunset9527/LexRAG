# LexRAG v3.0 Stage 1 execution log

## Goal and outcome

The active `/query` orchestration was migrated from an ordinary sequential Python method to one shared compiled LangGraph `StateGraph` while preserving deterministic routing, current-run evidence isolation, citation verification, one controlled repair, and evidence-insufficient degradation.

Design and planning:

- design commit: `a299698`;
- implementation-plan commit: `eaadfd1`;
- implementation commit: `697a2d8`.

No remote push, history rewrite, paid LLM evaluation, or evaluation-data modification occurred.

## Key decisions

- Preserve `LegalEvidenceWorkflow.query()` as a compatibility adapter; make `invoke()` the active API entry point.
- Compile one stateless graph at module load and pass request-scoped retrievers, LLM-backed callables, verifier, and non-secret identifiers through LangGraph runtime context.
- Keep conversation history separate from the Evidence Ledger.
- Keep the legacy ReAct module for compatibility but label it non-active.
- Expose `ainvoke()` and `astream_events()` for later streaming integration without changing the Stage 1 HTTP response contract.

## TDD evidence

1. Structural tests failed because no compiled graph export or orchestration metadata existed, then passed after the shared graph and synchronous facade were implemented.
2. Async entry-point tests failed because `ainvoke()` and `astream_events()` were absent, then passed after thin graph-backed wrappers were added.
3. The API contract test returned 500 because its workflow double exposed only `invoke()` while `api.py` still called `.query()`, then passed after `/query` switched to the graph entry point and supplied request context.

Existing evidence-workflow tests continued to cover optional case/graph retrieval, safe degradation, one repair, second-failure fallback, and trace privacy.

## Verification

- Ruff over all changed Python files: passed.
- Focused workflow/API/cache/session/evaluation tests: 28 passed, 3 existing dependency warnings.
- Full backend suite: 238 passed, 51 warnings, 67% total coverage.
- Coverage inventory: 6,601 statements, 2,158 misses; `src/workflow/legal_evidence_workflow.py` reached 82%.
- Coverage output remains local and ignored at `reports/quality/stage1-coverage.json`.

The warning set remains dominated by Pydantic class-config deprecations, the `langchain-community` sunset warning, `pkg_resources`/jieba, and unclosed SQLite connections in tests. Stage 1 does not claim warning-free or production-ready status.

## Problems and resolutions

| Problem | Resolution |
|---|---|
| Combined async RED selection did not finish after the first expected failure | Split the tests and added a public-method precondition before event iteration. |
| Two ad-hoc multiline `python -c` diagnostics had PowerShell quoting/syntax errors | Stopped using quoted diagnostic scripts and relied on bounded focused pytest reproduction. |
| Async tests hung before workflow execution | Pytest faulthandler traced the block to Windows event-loop creation in `socket._fallback_socketpair`; even a minimal asyncio command reproduced in the restricted sandbox and passed outside it. Async tests were therefore run with the approved project-Python pytest prefix outside the sandbox. |
| One repository-search regex was malformed after PowerShell quoting | Replaced it with a simpler single-quoted alternation and read the complete focused test file. |
| Ruff found two import-order violations | Applied Ruff's safe import-only fixes and reran the complete changed-file check. |
| The first recursive cleanup of the verified pytest temp directory timed out in permission review | Retried once with explicit approval, the same exact resolved path, and no reusable destructive prefix; cleanup completed. |

## Remaining boundaries

- Stage 2 still owns raw-query logging, SSRF controls, legacy verification persistence/ownership, upload authorization, and public/private route boundaries.
- `astream_events()` is an internal capability; consumer-facing streaming delivery remains Stage 6 work.
- Formal retrieval and human legal-answer evaluation remains Stage 8 work.
