# LexRAG Stage 0/1 Closure Completion Design

**Date:** 2026-10-19

**Status:** Implemented in `32ad4ed`; documentation verification completed 2026-10-20

## 1. Objective

Close every identified Stage 0 and Stage 1 engineering gap except résumé wording. The result must make the active code, automated evidence, API metadata, repository documentation, and the external roadmap agree that production `/query` uses the compiled LangGraph `StateGraph`.

This work is an engineering-acceptance closure. It does not run or claim the Stage 8 legal-quality evaluation.

## 2. Scope

### In scope

- add the missing Stage 1 behavioral acceptance tests;
- make `LegalEvidenceWorkflow.astream_events()` privacy-safe by exposing only an allowlisted structural event contract;
- replace the stale `evidence-v2.1` readiness marker with the current workflow version;
- update all current-status statements in the external roadmap that still say the active main chain is a plain Python workflow or awaits StateGraph migration;
- update Stage 0/1 verification records after the final checks pass;
- run focused and complete regression gates.

### Out of scope

- editing or validating any résumé;
- changing retrieval, ranking, prompts, embeddings, datasets, or legal-answer behavior;
- building the Stage 6 HTTP streaming endpoint or frontend streaming UI;
- running paid-model, Docker, security, retrieval-quality, or human legal review reserved for later stages;
- rewriting historical design documents merely because they accurately describe the state at their original date.

## 3. Selected approach

Use a narrow acceptance-closure change rather than a broader streaming or workflow refactor.

The compiled graph, its topology, and the synchronous and asynchronous result contracts remain unchanged. Missing acceptance cases are captured as tests first. Production code changes are limited to the event-stream privacy boundary and the stale internal workflow marker. Documentation is then reconciled with the verified implementation.

This approach prevents Stage 1 cleanup from expanding into Stage 6 while still satisfying the Stage 1 rule that traces must not expose user text, prompts, credentials, document content, or model reasoning.

## 4. Safe event-stream contract

`LegalEvidenceWorkflow.astream_events()` must not return raw LangGraph event dictionaries. Raw events can contain graph inputs, state snapshots, question text, conversation history, retrieved document text, and callable output.

The public workflow event stream will emit only allowlisted structural fields:

- `event`: normalized lifecycle event, limited to node start, node completion, or node error;
- `node`: one of the known workflow node names;
- `status`: `started`, `completed`, `degraded`, or `failed`;
- `duration_ms`: non-negative duration when completion timing is available;
- `input_count` and `output_count`: non-negative structural counts when available;
- `reason`: an exception class name or predefined degradation code when applicable.

Unknown LangGraph events and graph-level payload events are not emitted. No raw `data`, `input`, `output`, metadata object, question, conversation history, prompt, evidence content, document text, API key, base URL, or chain-of-thought field crosses this boundary.

The Stage 1 event stream remains an internal Python iterator for future Stage 6 consumers. This change defines its safe contract without adding an HTTP streaming transport.

## 5. Acceptance tests

All behavioral changes follow red-green-refactor. Each new test must be observed failing for the intended missing guarantee before the minimal implementation or documentation change is applied.

The focused workflow suite will add explicit cases for:

1. a complex question using normalized planner output;
2. planner failure degrading to the original question without exposing exception text or the private question in the workflow trace;
3. empty statute retrieval terminating as evidence-insufficient without calling the answer generator and remaining non-cacheable;
4. failed statute retrieval recording only the exception type, terminating as evidence-insufficient, and remaining non-cacheable;
5. conversation context remaining absent from Evidence Ledger items, answer-generator evidence, result metadata, and workflow trace;
6. `astream_events()` emitting only the allowlisted structural schema and containing neither the private question nor private history.

Existing tests continue to prove graph topology, simple statute-only execution, optional case and graph retrieval, routing and optional-retrieval degradation, one repair attempt, second-failure refusal, `ainvoke()` parity, and `/query` graph integration.

## 6. Version and documentation consistency

The API initialization readiness marker changes from `evidence-v2.1` to `evidence-v3.0`. It remains an internal truthy readiness marker; the health response continues to expose only `ready` or `not_ready`.

The external roadmap is updated wherever a current-status statement still claims that `/query` is a plain Python workflow or that LangGraph migration remains pending. Historical descriptions are handled as follows:

- dated Stage 0 execution notes remain intact and are explicitly historical where necessary;
- the v2.1 history section preserves historical metrics but states that the StateGraph migration was completed in Stage 1;
- the current capability matrix, version summary, execution timeline, footer status, and update date reflect the active StateGraph path;
- no Stage 8 result, production-readiness claim, or new quality metric is introduced.

The Stage 1 design document may retain its original “current state” section because it describes the pre-implementation baseline and is already marked implemented. Superseding status records must point to the verified implementation commit and final test results.

## 7. Verification and evidence

After implementation, run these gates in order:

1. the new workflow tests during each TDD cycle;
2. Ruff on changed Python files;
3. the focused Stage 1 workflow and API tests;
4. the complete backend test suite;
5. repository-wide searches for stale current-status StateGraph claims, `evidence-v2.1`, and accidental private sentinel strings;
6. `git diff --check` and a final worktree review.

The final status update records exact commands, pass counts, warnings, coverage when produced by the existing suite, and the tested commit or worktree state. Pre-existing warnings remain disclosed rather than relabeled as success.

## 8. Completion criteria

This closure is complete only when:

- all six missing behavioral guarantees have dedicated passing tests;
- the event stream exposes no raw LangGraph payload and passes the privacy sentinel test;
- the active API marker and all non-historical repository and roadmap statements use the current Stage 1 wording;
- focused and full automated checks pass;
- the worktree contains only intentional changes;
- documentation clearly separates engineering acceptance from Stage 8 legal-effect validation;
- no résumé file has been modified.
