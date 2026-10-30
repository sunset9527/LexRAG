# Progress Log

## Session: 2026-10-28

### Phase 1–2: Metric contract and pure evaluator

- **Status:** complete
- Actions taken:
  - Confirmed the formal Stage 8 design and committed it as `d2bbb87`.
  - Audited legacy retrieval/routing evaluators and identified their single-law data-contract boundary.
  - Created persistent implementation plan and findings records.
  - Confirmed the Stage 4 snapshot provides explicit verified collection identities for all eight laws.
  - Added and committed `src/evaluation/stage8_retrieval_evaluation.py` plus 15 test-first cases in `1372bff`.
  - Passed independent spec-compliance and code-quality reviews.
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
  - `src/evaluation/stage8_retrieval_evaluation.py`
  - `tests/test_stage8_retrieval_evaluation.py`

### Phase 3: Real-run CLI

- **Status:** complete
- Actions taken:
  - Started integration design for verified Stage 4 collection mappings and run-manifest output.
  - Initial CLI review found two integrity gaps: it admitted formal subsets and the shared run manifest lacked dependency versions. A test-first follow-up is in progress before the CLI can be accepted.
  - Follow-up fixed both review gaps and passed review; final focused regression reached 234 passed.
  - First live Vector run exposed a read-only Chroma SQLite write requirement; copied the verified 133.44 MiB source index into a writable evaluation-only directory without changing the source.
  - Second live preflight exposed that the accepted legacy collections have no collection-level source hash. A fail-closed chunk-level provenance fallback is now under test-first repair.
  - Added and reviewed the legacy fallback in `93f624e`; 106 focused tests passed.

### Phase 4: Verification and live evaluation

- **Status:** in_progress
- Actions taken:
  - Ran 234 focused Stage 8/manifest tests: all passed; one pre-existing `pkg_resources` deprecation warning.
  - Ran Ruff, formatting and compilation checks: passed.
  - BM25 formal run completed with 260/260 answerable rows scored, 20 abstention rows excluded, and zero execution errors. Overall Recall@5=0.5234615385, MRR@5=0.5205769231, NDCG@5=0.4736784779; routing Top-1=0.8181818182 and candidate recall=0.8019230769.
  - Vector runs produced explicit nonzero execution errors and are not valid metrics. Direct diagnostics found missing HNSW segment readers (`Nothing found on disk`) for some snapshot collections; Vector and RRF await physical-index repair/revalidation.
  - Added test-first isolated repair tooling: it exports each snapshot-bound collection's stored payload, recreates HNSW segments in a brand-new copy, verifies payload equality/provenance and makes a vector-query smoke check mandatory. Unit/CLI tests: 4 passed.
  - Rebuilt and independently verified all eight collections in `data/chroma_stage8_eval_repaired_20261028_v2`; original source index was not written. Re-ran all retrieval modes at commit `0cb2f81`: BM25 (R@5 .5235 / MRR@5 .5206 / NDCG@5 .4737), Vector (.6237 / .6311 / .5798), and RRF (.6319 / .6326 / .5762), all 260 scored with zero execution errors.
  - Corrected RRF's inserted-article identity handling so stored `article_id` is preserved rather than rebuilding “第17条之一” as “第17-1条”. Post-repair focused suite: 60 passed, 1 third-party deprecation warning.
  - Restart diagnostics later disproved the repaired directory's durability: an HNSW collection could be queried in its construction process but failed after reopening, and the same persistent read failed after local BGE-M3 initialization. The old Vector/RRF reports are therefore historical diagnostics, not release evidence.
  - Exported a verified eight-collection runtime payload (`stage8_runtime_payload_20261028.json.gz`) from an untouched source copy before loading BGE-M3. Its manifest binds the Stage 4 snapshot hash, collection names, chunk counts, and payload SHA-256 values.
  - Implemented a process-local ephemeral Chroma mirror for API query runtime when `RUNTIME_VECTOR_PAYLOAD_PATH` is configured. It never queries persistent HNSW after BGE initialization; 30 focused tests passed and the local backend returns `/health` 200 with the payload configuration.

### Phase 5: Full-answer review preparation

- **Status:** sample ready; awaiting real workflow output and human decisions.
- Added the deterministic 100-row review sample at commit `215d4e3`: all 20 abstention rows plus 80 answerable rows allocated as 31 baseline, 15 oral, 12 adjacent/confusable, 12 cross-law, and 10 multi-hop. The sample manifest binds source and sample SHA-256 values; every review field is blank/pending.
- Implemented a local-only Stage 8 answer-review runner. It reads `STAGE8_LLM_API_KEY` and `STAGE8_AUTH_TOKEN` only from the invoking PowerShell process, posts sequential cache-bypassed `/query` requests, and writes credential-free JSONL plus a SHA-256-bound manifest. Test-first verification: 5 passed. A missing-token preflight fails before making any request.
- First real run at `20261029T053351Z` produced 0 completed and 100 explicit execution errors; it is retained only as a failed execution artifact, not answer-quality evidence. Root cause: the initial runner sent 100 requests without respecting the API's 60 requests/60 seconds query limit, and its error record lacked the HTTP status code. The runner now spaces requests by 1.1 seconds and preserves safe transport codes such as `HTTP_429`; 7 focused tests pass.
- Second live run at `20261029T054542Z` also produced 0 completed: 59 `HTTP_400`, 37 `HTTP_429`, and 4 interrupted connections. The `400` root cause was a payload-mode contract gap: version selection still demanded a persistent Chroma collection despite the configured verified immutable payload. Fixed with integrity-checked payload collection readiness; the runner now refuses to retry `HTTP_400` and has a `--limit 1` smoke-test mode. Focused verification after the fix: 17 runner/payload/version tests plus the payload-mode API contract test passed.
- Authenticated answer collection is now complete: 15 completed records from `stage8_answer_review_run_20261029T072846Z.jsonl` plus 85 completed records from `stage8_answer_review_run_20261029T090802Z.jsonl` cover all 100 unique frozen sample IDs; the resume run has 0 execution errors. The interrupted `20261029T084351Z` artifact and earlier failed artifacts remain diagnostic-only and must not be used for quality scoring.
- Merged the two valid answer runs with `scripts/merge_stage8_answer_review.py`. The auditable input for the legal answer review is now `reports/evaluation/stage8/answer_reviews/stage8_answer_review_merged_100.jsonl`, accompanied by a source/run-SHA-bound manifest. It has exactly 100 unique records, 100 workflow outputs, and 100 `pending` human reviews.
- Core security/route contracts passed: 32 authentication, rate-limit, request-security, route-security and security-settings tests; document/upload/Compose contracts added 21 passing tests after removing obsolete graph-volume expectations. The full asynchronous query-run API test cannot run to completion in this isolated runner: Python 3.13 blocks in its own `asyncio` local socket-pair creation before entering an API route. It remains a required local acceptance command, not a pass claim.
- Final automated release evidence: the consolidated targeted backend suite passed 56 tests, frozen-data/evaluator/runner contracts passed 82 tests, frontend unit tests passed 5/5, and a fresh frontend production build produced `frontend/dist/index.html`. Docker Compose interpolation/configuration validation passed only with process-local placeholder values; no container lifecycle claim is made. Playwright discovered the one login E2E test but could not start its local Vite server in the isolated runner, so E2E remains pending local acceptance.
- Published `reports/evaluation/stage8/STAGE8_RELEASE_READINESS_20261029.md`, which distinguishes completed evidence from human legal review, Judge/Ragas calibration, SSE/local-browser acceptance, Docker recovery, and final integration.
- Human answer review is now complete: all 100 merged records have reviewer, timestamp, note and boolean `human_review`; 97 are approved and 3 rejected. This is an observed human assertion-support result, not a substitute for the still-pending diagnostic Judge/Ragas calibration.

## Test Results

| Test | Input | Expected | Actual | Status |
|---|---|---|---|---|
| Pure metrics | `python -m pytest tests/test_stage8_retrieval_evaluation.py tests/test_stage8_dataset.py -q --basetemp=.pytest_cache/stage8-metrics-temp` | Formal metric and loader contracts pass | 71 passed | ✓ |
| Full focused Stage 8 contract | Stage 4 snapshot, frozen artifacts, formal evaluator/CLI, run manifest | All pass | 234 passed, 1 third-party deprecation warning | ✓ |
| Live BM25 | 280-row frozen set on writable verified-index copy | 260 answerable rows, no execution errors | 260 scored; Recall@5 0.5234615385 | ✓ |
| Live Vector | Same input/index copy | 260 answerable rows, no execution errors | 30 then 50 execution errors; missing HNSW readers | ✗ |

## Error Log

| Timestamp | Error | Attempt | Resolution |
|---|---|---:|---|
| 2026-10-28 | Planning-file patch context mismatch | 1 | Read the current file and applied a narrower patch. |
| 2026-10-28 | Vector HNSW segment readers missing | 1 | Preserve failed reports; do not calculate a formal Vector/RRF metric until index repair. |

## 5-Question Reboot Check

| Question | Answer |
|---|---|
| Where am I? | Phase 4: verification and live evaluation. |
| Where am I going? | Data-index repair decision, then remaining Stage 8 evaluation work. |
| What's the goal? | Reproducible formal retrieval and routing evaluation for the frozen 280-row dataset. |
| What have I learned? | See `findings.md`. |
| What have I done? | See phase log above. |

## Session: 2026-10-29

### Phase 6: Knowledge-graph removal

- **Status:** implementation complete; final environment acceptance pending
- User approved full removal of graph source, build scripts, graph data, APIs, front-end pages and NetworkX, preserving only Git history.
- Design committed separately as `b00f0db`.
- Deleted the graph source/data/API/UI/build surface, removed workflow/startup/readiness/Compose/NetworkX dependencies, and added migration `20261029_01` to drop `agent_configs.graph_search_enabled`.
- Confirmed `retrieval_optimizer.py` keeps metadata-only reference expansion without graph artifacts or NetworkX.
- Verification: `python -m compileall -q api.py app src scripts init.py`; 18 graph-removal contracts and 40 targeted backend contracts passed; metadata reference/Agent-config suite 22 passed; Stage 8 evaluator suite 71 passed; Vue type-check, Vite production build and frontend visual test passed.
- Limitation: the full evidence-workflow and admin/query-cache test batches completed their visible test execution but this Windows runner returned at its 30-second cleanup limit before a final pytest summary. They are not recorded as passed.
- `npm run test` is not a supported frontend script; the repository's Node test was run directly with `node --test tests/visualSystem.test.mjs` and passed.

## Session: 2026-10-30

### Phase 7: Gate A Judge/Ragas diagnostic calibration

- **Status:** in_progress
- Confirmed the design-approved gate scope and immutable human-review input contract.
- Confirmed the current candidate does not declare Ragas or a Judge SDK, so their runtime integration will be explicitly optional and cannot silently fabricate a score.
- Recorded the candidate-local virtual-environment absence; the next test run will use the existing verified project virtual environment explicitly.
- Added a test-first pure calibration contract. Its first run failed exactly because `src.evaluation.stage8_diagnostic_calibration` did not exist; the minimal loader/reducer implementation now passes 3 focused tests.
- Added test-first, credential-free calibration CLI and blind optional Judge runner. The focused regression now has 8 passing tests and Ruff passes for all new Gate A files. The Judge validates real provider URLs with the existing SSRF policy before making a network request; the injected test path performs no network I/O.
- Ragas remains pending as a diagnostic result, not as a dependency: its dedicated environment is now verified separately, but no framework score has been run or invented.

### Phase 8: Gate B local SSE/browser acceptance

- `tests/test_query_runtime_registry.py` passed 3/3 (`10.35s`) using the explicit verified virtual environment; two pre-existing dependency deprecation warnings were emitted.
- `tests/test_query_run_service.py` did not complete. With a 10-second faulthandler timeout, it blocked at Windows `socket._fallback_socketpair` while `asyncio.run()` initialized the event loop, before LexRAG service code. The result is logged as an environment blocker, not a passing or failing SSE claim.
- The user subsequently ran the full local suite in PowerShell: `tests/test_query_run_api.py`, `tests/test_query_run_service.py`, and `tests/test_query_runtime_registry.py` passed 11/11 in 29.26 seconds. The two emitted warnings are third-party deprecations (`pkg_resources` and LangGraph serializer configuration), not test failures.
- The user ran `npm.cmd run test:e2e` from `frontend`; Playwright started the local Vite server and the Chromium login-page E2E passed 1/1 in 28.4 seconds. Its authentication check is deterministically intercepted, so this is browser-entry evidence rather than a real backend-login claim.

### Ragas installation attempt

- Selected Ragas 0.4.3 after checking its official installation guidance and PyPI Python support. The package was not installed successfully.
- The shared virtual environment attempt was stopped by a Windows lock on `huggingface_hub`; a dedicated candidate-local evaluation environment was created instead.
- In the isolated execution service, both standard and legacy pip resolution were terminated before completion. This historical runner limitation does not invalidate the user's later external dedicated-environment verification; no diagnostic metric was run during this attempt.

### Ragas input preparation

- The user verified the external dedicated environment at `E:\\python\\LexRAG-stage8-ragas`: `import ragas` reports `0.3.9`, and `pip check` reports `No broken requirements found`.
- Implemented `stage8_ragas_input` with test-first coverage for citation-context extraction, duplicate removal and fail-closed missing input handling. The actual 100-row merged artifact materializes 100 records.
- The output deliberately excludes reference-dependent metrics because no `reference_answer` is present. Supported planning scope is Faithfulness plus LLM context precision without reference; Answer Relevancy also awaits an explicit evaluator embedding configuration.
- Implemented the real Ragas CLI. It verifies manifest-bound reviews before calling the provider, evaluates samples one at a time, preserves execution failures, and emits SHA-bound JSONL/config/summary artifacts without a credential. Focused Ragas tests pass 6/6; dedicated-environment construction of the Ragas evaluator reports version `0.3.9` without a network call.

### Ragas diagnostic execution

- The initial 100-row run retained its errors instead of dropping them: 50 completed and 50 `APIConnectionError` rows. The deterministic alternation identified that the initial client had disabled SDK retries with `max_retries=0`.
- Added a tested recovery path that keeps already-completed rows, retries only prior `execution_error` rows, and writes a new artifact rather than overwriting the prior evidence. The client now allows two SDK connection retries.
- Recovery chain: initial `50/100`, first recovery `99/100`, final recovery `100/100` completed with zero execution errors. The final artifact is `reports/evaluation/stage8/ragas/stage8_ragas_100_final.summary.json`.
- Final supported diagnostic means: Faithfulness `0.7400433334977492`; context precision without reference `0.8881111110449865`. These are Ragas diagnostic metrics over the already-produced answers and retrieved statutes. They are not gold-answer correctness, recall, or a replacement for the completed human review.

### Phase 9: Gate C isolated Docker acceptance

- Generated the ignored `.env.docker.stage8` for an isolated Compose project named `lexrag-stage8-acceptance`; it uses a fresh set of project-named volumes and the local `E:\huggingface\model` BGE-M3 mount. The environment file is intentionally not committed and no value from it is recorded here.
- The deployment verifier passed Compose configuration, build, container start, Alembic migration, statute bootstrap and API readiness. API, Web, Worker and Beat reached healthy state; the verifier evidence is under `reports/deployment/lexrag-stage8-acceptance/`.
- Created disposable acceptance administrators only in the isolated MySQL volume. Gateway-routed login, `/auth/me`, and the admin-protected `/law-updates/version-chains` read endpoint passed. No token or password was persisted.
- Created an isolated document library and uploaded `tests/fixtures/sample_text_law.pdf`. Its Celery processing job completed as `READY` with 1 page, 88 characters, and 1 vector chunk, demonstrating the Web/API/Redis/Worker/local-BGE/Chroma upload path without changing statutory content.
- Restarted the API, Worker and Web while retaining all named volumes. Readiness recovered, but the first Web-routed login returned `502`; Nginx had retained a stale API upstream address. Added a test-first Nginx contract and switched the proxy to Docker embedded-DNS request-time resolution while preserving `/api` path rewriting. The focused contract suite passed 8/8. After rebuilding only Web, forcibly recreating API with the same named volumes left Web running; `/api/health/ready`, real gateway login, and authenticated version-chain GET all passed. The recovery defect is resolved and regression-covered.
- A real runtime query is intentionally still unrun: the disposable Docker environment has no runtime LLM key, and the separate Ragas credential must not be copied into it. Gate C therefore remains incomplete.

### Judge blind calibration execution

- The initial blind Judge execution created its JSONL/config/calibration artifacts but had 100/100 `BadRequestError` provider rows. They are retained as failed execution evidence, not discarded.
- Root cause: DeepSeek JSON mode requires an explicit `json` instruction and an output-shape example in the prompt. Added a test-first JSON-mode message contract, bumped prompt provenance to `stage8-diagnostic-judge-v2`, and verified the Judge/calibration suite 10/10 with a project-local pytest base temp directory.
- The recovery Judge run completed 100/100 with zero execution errors. The hash-bound calibration result has agreement rate `0.97`, `true_positive=97`, `true_negative=0`, `false_positive=3`, and `false_negative=0`.
- Interpretation: Judge agreed with all human-approved rows but accepted all three human-rejected retrieval-failure non-answers (`round2-adjacent-038`, `round2-multihop-009`, `round2-multihop-020`). Its apparent 97% agreement is driven by the positive-heavy sample; negative-case sensitivity is 0/3. Human review remains the authoritative legal-quality evidence.
