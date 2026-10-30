# Task Plan: Stage 8 formal retrieval and routing evaluation

## Goal

Implement a reproducible evaluator for the reviewed 280-row Stage 8 dataset that reports oracle retrieval and automatic-routing results without changing historical engineering-regression tooling.

## Current Phase

Completed — Stage 8 evidence was merged locally into `main` on 2026-10-30.

## Phases

### Phase 1: Metric contract and tests

- [x] Add failing tests for formal records, composite law/article identities, grouping, abstention exclusion, and routing metrics.
- **Status:** complete

### Phase 2: Pure evaluation implementation

- [x] Implement strict formal retrieval/routing evaluation functions.
- [x] Keep legacy evaluator and data loader unchanged.
- **Status:** complete

### Phase 3: Real-run CLI

- [x] Add a separate CLI with explicit verified collection mappings.
- [x] Emit auditable JSON with run manifest and explicit execution errors.
- **Status:** complete

### Phase 4: Verification and delivery

- [x] Run focused tests, compile check, and a real local dry run where dependencies permit.
- [x] Rebuild and validate HNSW segments in a new isolated evaluation copy.
- [x] Re-run BM25, Vector and RRF formal reports against the immutable runtime payload; earlier persistent-HNSW reports are retained only as diagnostics.
- [x] Record results in the immutable report set.
- [x] Create the final scoped release commit after all acceptance gates have evidence (`6f5f8be`).
- **Status:** complete for the user-approved local integration scope.

### Phase 5: Full-answer review preparation

- [x] Materialize a deterministic 100-row human-answer review sample.
- [x] Implement and test the local-only authenticated answer-review runner.
- [x] Reconcile payload-mode version readiness with the immutable runtime manifest and prevent non-transient request retries.
- [x] Run the selected rows through a real authenticated workflow and collect responses (15 initial successes + 85 successful resume rows; 100/100 covered).
- [x] Merge the two successful answer-review runs into one manifest-bound 100-row review file.
- [x] Complete the evidence-located human answer review (97 approved, 3 rejected).
- [x] Calibrate diagnostic Judge/Ragas outputs against the completed human review.
- **Status:** complete; Judge/Ragas remain secondary diagnostics rather than legal-quality authority.

### Phase 6: Knowledge-graph removal

- [x] Remove graph dependencies, artifacts, startup/bootstrap paths and database configuration.
- [x] Remove graph API, workflow branch, legacy agent branch, frontend entry/page and docs.
- [x] Verify retained metadata-based reference expansion, backend contracts, frontend build and Stage 8 evaluator.
- [ ] Run the Alembic migration against a disposable MySQL database and rerun full asynchronous backend suite in an environment that exits cleanly.
- **Status:** implementation complete; final environment acceptance pending

## Decisions Made

| Decision | Rationale |
|---|---|
| Preserve legacy eight-law runner | It remains an engineering-regression record and uses a different data contract. |
| Use `(slug, article_id)` labels | Same-numbered articles in different laws must never become false hits. |
| Score 260 answerable rows for ranking/routing | The 20 abstention rows require an answer-level decision and remain visible but outside retrieval denominators. |
| Report oracle retrieval and automatic routing separately | Correct-collection retrieval does not measure routing quality. |
| Remove knowledge graph completely | User approved the hard-delete specification in `docs/superpowers/specs/2026-10-29-remove-knowledge-graph-design.md`; keep only metadata-based reference expansion. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Planning-file patch context mismatch | 1 | Read current file and applied a smaller status-only patch. |
| CLI accepted approved subsets | 1 | Add frozen-manifest hash/count binding and enforce the 280/260/20 contract. |
| Run manifest lacked dependency versions | 1 | Add an optional validated dependency-version mapping and populate it for formal runs. |
| Chroma client could not open the original index | 1 | Copy the 133.44 MiB verified index to a writable evaluation-only directory; original remains untouched. |
| CLI rejected Stage 4 legacy collection metadata | 1 | Reuse the Stage 4 chunk-level provenance fallback while retaining fail-closed checks. |
| Vector HNSW segments unavailable for some frozen collections | 1 | BM25 completes from validated chunk text; Vector/RRF await physical-index repair and revalidation. |
| Physical-vector repair scope | 1 | User approved a new-copy rebuild from stored payloads; do not write the original or prior evaluation copy. |
| Chroma returns stored embeddings as NumPy arrays | 1 | Normalize with `tolist()` before validating/reinserting; regression test added. |
| RRF reconstructed inserted article identities | 1 | Preserve authoritative metadata `article_id`; regression test covers “第17条之一”. |
| Repaired HNSW failed after restart | 1 | Do not release-evaluate or serve a reopened Windows persistent HNSW directory; export a snapshot-bound payload and query an ephemeral mirror. |
| Candidate-local virtual environment absent | 1 | Use the existing verified project virtual environment explicitly; never create or modify dependencies until the diagnostic dependency contract is defined. |
| Windows asyncio socket-pair blocks before query-run service code | 1 | Registry-only contracts pass; retain service/API and browser flow as local/Docker acceptance gates and do not record an SSE pass. |
| Ragas dependency resolution exceeds isolated command lifetime | 3 | Do not claim the package is installed. Keep the dedicated evaluation virtual environment separate and complete the pinned install from the user's normal PowerShell terminal. |

### Phase 7: Gate A Judge/Ragas diagnostic calibration

- [x] Define a strict, manifest-bound loader for the completed 100-row human review.
- [x] Add test-first calibration reduction that preserves evaluator failures in the denominator.
- [x] Add a credential-free CLI/report contract with redacted configuration provenance.
- [x] Add an optional OpenAI-compatible Judge adapter without making it a production runtime requirement.
- [x] Add a Ragas adapter pinned to the dedicated `ragas==0.3.9` environment; it preserves per-sample provider failures and never serializes credentials.
- [x] Verify the user-managed dedicated environment imports `ragas==0.3.9` and passes `pip check` after the compatible LangChain pins are installed.
- [x] Materialize 100 completed answer reviews into truthful Ragas records without fabricating reference answers.
- [x] Bind supported/unsupported metric decisions to the actual Stage 8 input contract.
- [x] Run the supported real Ragas diagnostics with a process-local `STAGE8_RAGAS_API_KEY`; the final hash-bound artifact has 100/100 completed rows and no execution errors.
- [x] Run a separate blind Judge-vs-human calibration with `STAGE8_JUDGE_API_KEY`; retain the first 100-call provider failure artifact and a separate 100/100 recovery artifact.
- **Status:** complete; Ragas and Judge diagnostics are both complete, but neither replaces the human legal review. Judge accepted all three human-rejected rows, so its negative-case sensitivity is explicitly limited.

### Phase 8: Gate B local SSE and browser acceptance

- [x] Re-run the runtime-registry contract suite in the verified Windows virtual environment.
- [x] Re-run query-run service/API suites in the local Windows PowerShell environment (11/11 passed).
- [x] Run the existing Playwright browser-entry smoke test against the local frontend stack (Chromium login render passed 1/1).
- [ ] Extend and run real-stack browser E2E for the remaining documented workflows: authenticated login, query progress/citations, session/favorites, upload/task entry, and RBAC/cross-organization rejection.
- **Status:** complete for scoped local acceptance; backend SSE/cancellation contracts and the deterministic browser entry path are accepted locally. Full real-stack browser workflows remain a non-blocking follow-up, not a completed release claim.

### Phase 9: Gate C isolated Docker acceptance

- [x] Generate a git-ignored, fresh isolated Docker environment with a read-only local BGE-M3 mount and project-named volumes.
- [x] Verify Compose configuration, image build, migration, bootstrap, and API readiness on the isolated project.
- [x] Verify gateway login, authenticated identity, version-chain read health, and an asynchronous document-upload task against the isolated stack.
- [x] Preserve the named volumes across a service restart and re-check readiness.
- [x] Repair and regression-test the observed Web gateway stale-upstream `502` following API recreation.
- [ ] Run a real authenticated runtime query with a process-local LLM credential supplied at execution time; do not store the key in `.env.docker.stage8`.
- **Status:** complete for scoped local acceptance; cold start, upload, and gateway/API recovery are evidenced. A credentialed Docker runtime query remains a non-blocking follow-up and is not claimed as complete.

### Scoped local integration and close (2026-10-30)

- [x] Commit the scoped Stage 8 implementation and evidence as `6f5f8be`.
- [x] Fast-forward the original repository's local `main` branch to that commit.
- [x] Re-run the merged-main Stage 8 core suite: 43 passed (one third-party deprecation warning).
- [x] Preserve the pre-existing root-level Stage 7 planning files and keep Stage 8 planning files under `docs/status/`.
- [x] Recreate the dedicated Ragas 0.3.9 environment inside the main repository as `.venv-stage8-ragas`; it imports successfully and `pip check` reports no broken requirements.
- [ ] Push to a remote repository or claim a production deployment (not requested).
- [ ] Run the full real-stack browser workflow or an authenticated Docker runtime query (not required by the approved local close).
- **Close status:** complete in the approved local scope. Outstanding checks above remain explicitly unexecuted rather than silently treated as passes.
