# Stage 8 release acceptance design

**Date:** 2026-10-30  
**Status:** proposed  
**Scope:** the isolated candidate at `E:\个人发展\002职业\Legal_RAG_Agent-stage8-freeze` only.

## Purpose

Close the remaining Stage 8 release gates without changing the frozen evaluation
set, rewriting human-review decisions, or combining evidence from different
candidate revisions. The target is an auditable release-readiness result. A
missing or failed gate remains visible and makes the candidate non-releasable.

## Baseline and invariants

- The frozen formal set remains 280 records: 260 answerable and 20 abstention
  records. Its manifest, legal-source versions, runtime payload, and retrieval
  reports remain immutable inputs.
- The merged 100-row workflow result and its completed single-reviewer record
  (97 approved, 3 rejected) remain immutable diagnostic inputs. The three
  rejected rows must remain in all follow-up summaries.
- Judge and Ragas are diagnostic tools. They cannot replace human legal review
  or be reported as legal-correctness findings.
- All output reports bind the candidate Git revision, input SHA-256 values,
  command, environment, dependency versions, time, sample count, explicit
  execution errors, and known limitations.
- No stage-8 evidence is copied into the primary repository until the user
  deliberately reviews the final candidate and requests integration.

## Approach

Acceptance proceeds gate by gate, in dependency order. Each gate has isolated
inputs and a durable report. If a gate requires a production-code change, tests
are added first and the affected gate plus all downstream gates are rerun from
the revised candidate. Results from a prior revision are retained as historical
diagnostics, never merged into the final pass report.

## Gate A — Judge/Ragas diagnostic calibration

### Inputs

- The SHA-bound merged 100-row Stage 8 answer-review JSONL and manifest.
- Process-local model credentials only; no key, prompt contents, or raw secrets
  are written to reports.
- A versioned evaluation configuration containing model identity, temperature,
  retry policy, prompts/templates by hash or repository-relative version, and
  dependency versions.

### Components

1. A strict loader validates the 100 unique IDs, workflow responses, source
   manifest hashes, reviewer fields, and completed boolean human decisions.
2. A runner materializes one diagnostic record per accepted input row. A failed
   evaluator invocation produces an explicit execution-error row, never a
   quality score or silently removed denominator.
3. A calibration reducer compares limited Judge dimensions—evidence fidelity,
   question coverage, abstention appropriateness, and clarity—against the
   existing human decision. It reports evaluable count, agreement rate,
   confusion matrix, false-positive/false-negative counts, and representative
   disagreement IDs.
4. Ragas output, when the configured version supports the required Chinese
   inputs, records Context Precision, Context Recall, Faithfulness, Answer
   Relevancy, and Answer Correctness per row plus failures. It is summarized
   separately from human review and annotated as diagnostic only.

### Failure behavior

Missing credentials, unsupported dependency versions, malformed inputs, or
individual evaluator failures stop publication of a passing calibration report.
The reducer can still write a bounded diagnostic report that clearly separates
successes from execution errors. No synthetic score is generated.

## Gate B — local SSE and browser acceptance

### SSE acceptance

Run the existing query-run API, service, and runtime-registry tests in the
normal Windows project terminal, where Python can create event-loop socket
pairs. The evidence report records the exact command and runtime result. It
must cover event ordering, replay, cancellation, terminal events, cleanup, and
no raw prompt or credential leakage.

### Browser acceptance

Run the existing Playwright suite against a locally started, configured
frontend/backend stack. The run must exercise authenticated login, query
progress, citation source access, automatic knowledge-base routing, session
restoration, favorites, document upload, scenario task entry, RBAC, and a
cross-organization rejection. Failures are captured with traces/screenshots
only after confirming they contain no user documents or credentials.

## Gate C — isolated Docker cold-start and recovery

Use a unique Compose project name and newly created named volumes. Before any
container starts, verify the actual non-secret environment file, readonly BGE
model mount, Docker availability, and that the selected volumes are dedicated
to this acceptance run. The procedure must:

1. Build images and run migrations/bootstrap on empty volumes.
2. Check API readiness, MySQL, Redis, Worker, Beat, and web health.
3. Perform authenticated login, a query, an upload/async document path, and a
   version-update health check.
4. Restart relevant services while preserving volumes and verify readiness and
   a minimal post-restart query path.
5. Produce redacted command output, image identifiers, volume names, timestamps,
   and observed results.

No destructive volume action is allowed without a separate exact-target check
and the user’s authorization. A Compose syntax check is not a cold-start pass.

## Gate D — final quality and release decision

After A–C, run the repository quality suite (Ruff, backend tests/coverage,
frontend tests, type check, and production build) at the same Git revision.
Generate one release-readiness report linking all Stage 8 reports. It may say
`READY_FOR_REVIEW` only if every required gate passes and no P0 issue remains;
otherwise it says `NOT_READY` and lists the blocking gates. It does not create a
tag, GitHub Release, or merge the candidate.

## Testing strategy

New report/configuration logic is developed test first:

- malformed manifests and incomplete human reviews fail closed;
- evaluator runtime errors remain counted errors;
- calibration computations preserve the denominator and exact confusion counts;
- redaction prevents credentials from entering artifacts;
- a passing report requires immutable input bindings and explicit configuration;
- a final decision cannot become ready while a mandatory gate is absent or
  failed.

Existing SSE, Playwright, Compose, and quality tests are acceptance evidence;
they are not rewritten to paper over environment failures.

## Out of scope

- Editing frozen questions, labels, expected citations, or human verdicts to
  improve metrics.
- Claiming dual-review agreement, Ragas/Judge legal correctness, performance,
  security, recovery, or E2E success without the corresponding real-run record.
- Main-repository integration, release tagging, publishing, production rollout,
  or deletion of any existing data/volumes.

## Self-review

- No placeholder requirement remains: each gate specifies inputs, outputs and
  failure treatment.
- The gate order matches dependencies: diagnostic data first, local acceptance,
  isolated deployment acceptance, then final report.
- The design preserves the documented frozen-data and review-result boundaries.
- Every environment-dependent step explicitly requires a real run and records
  limitations instead of inferring a pass.
