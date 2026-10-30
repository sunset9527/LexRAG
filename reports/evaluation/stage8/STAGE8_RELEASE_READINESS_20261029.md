# Stage 8 release readiness — 2026-10-29

This report records only evidence produced from the isolated Stage 8 candidate
and its post-merge local verification.
It does not turn unreviewed answers, diagnostic runs, or environment-limited
checks into release passes.

## Local integration status (2026-10-30)

The scoped candidate was fast-forward merged into the original repository's
local `main` branch at commit `6f5f8be`. The merged-main core Stage 8 suite
then passed 43 tests. This is a local integration record only: no remote push,
production deployment, full real-stack browser workflow, or credentialed
Docker runtime query is claimed.

| Gate | Status | Evidence / limitation |
| --- | --- | --- |
| Formal frozen set | complete | 280 records (260 answerable, 20 abstention) are bound by `data/evaluation/stage8/stage8_frozen_280.manifest.json`; frozen-artifact/dataset tests passed (60 tests in the final run). |
| Formal retrieval | complete | Immutable runtime-payload report summary: `STAGE8_FORMAL_RETRIEVAL_PAYLOAD_SUMMARY_20261028.md`. BM25 `R@5=.5235, MRR@5=.5206, NDCG@5=.4737`; Vector `.6237/.6311/.5798`; RRF `.5428/.5440/.4889`. These are retrieval metrics, not answer-quality claims. |
| 100 workflow outputs | complete | `answer_reviews/stage8_answer_review_merged_100.jsonl` contains 100 unique sample IDs and 100 workflow outputs; its adjacent manifest binds the source sample and both valid run files by SHA-256. |
| Answer legal review | complete | All 100 merged rows contain reviewer, timestamp, note and boolean `human_review`: 97 approved and 3 rejected. The observed human assertion-support rate is 97.00%; it does not by itself establish separate Ragas-style dimensions. |
| Judge/Ragas calibration | complete, diagnostic only | Ragas diagnostics are complete (100/100 rows, zero execution errors). Blind Judge-vs-human calibration is also complete (100/100, zero execution errors), but Judge accepted all 100 rows: it agreed on 97 human-approved rows and missed all 3 human-rejected rows. Its observed 97% agreement is class-imbalanced and must not substitute for human legal review. |
| Backend security and release contracts | passed | 56 targeted tests passed: answer-review merge, authentication, rate limit, request/route security, security settings, document/upload and Compose contracts. |
| Stage 8 evaluator/runner contracts | passed | 82 tests passed: frozen artifacts, formal dataset, formal retrieval evaluator and answer-review runner. |
| Frontend build/unit checks | passed | A fresh production build generated `frontend/dist/index.html`; Vitest unit suite passed 5/5. |
| Docker Compose syntax/required-variable contract | passed only | `docker compose config --quiet` passed with process-local non-secret placeholders. No containers, volumes, MySQL migration, or recovery scenario was started. |
| SSE/cancellation API suite | passed locally | The user ran `python -m pytest tests\\test_query_run_api.py tests\\test_query_run_service.py tests\\test_query_runtime_registry.py -q` in the project PowerShell: 11/11 passed in 29.26 seconds. Two third-party deprecation warnings were emitted; neither is a test failure. |
| Browser E2E | smoke passed; full workflow suite pending | The user ran `npm.cmd run test:e2e` locally: Playwright Chromium login entry passed 1/1 in 28.4 seconds. The test intercepts `/api/auth/me`, so it proves browser rendering/routing only—not the documented real backend login, query streaming/citations, session/favorites, upload/task, or RBAC workflows. |
| Empty-volume Docker cold start/recovery | partially complete | A new, isolated `lexrag-stage8-acceptance` Compose project and five project-named volumes completed config, build, up, migration, bootstrap and readiness checks. API/worker/web were healthy; a real login, authenticated version-chain GET, and document upload task succeeded. A discovered stale-upstream `502` following API recreation was fixed and regression-tested without restarting Web. A credentialed runtime query was not run because no runtime LLM key was supplied to this isolated environment, so the full restart/re-query gate is not a release pass. |
| Final candidate commit / merge to original repository | complete, scoped local integration | Candidate commit `6f5f8be` was fast-forward merged into local `main`; merged-main Stage 8 core suite passed 43 tests. No remote push is claimed. |

## Completed human review

`answer_reviews/stage8_answer_review_merged_100.jsonl` now contains the final
human decisions. The three rejected answers must remain visible in follow-up
diagnostics and release triage; neither the source questions nor their workflow
outputs may be rewritten to improve the reported rate.

## Non-blocking follow-ups outside the approved local close

- Run the full real-stack browser workflow: authenticated login, query
  progress/citations, session/favorites, upload/task entry, and cross-org RBAC.
- Run one authenticated Docker runtime query with a process-local runtime LLM
  credential. The Ragas key must not be copied into Docker configuration.
- Push the local `main` result to a reviewed remote and perform any production
  release procedure separately.

## 2026-10-30 follow-up evidence

| Gate fragment | Result | Evidence / limitation |
| --- | --- | --- |
| Runtime-registry contracts | passed | `python -m pytest tests\\test_query_runtime_registry.py -q -o faulthandler_timeout=10 --basetemp=.pytest_stage8_sse_registry` completed 3/3. The run emitted two third-party deprecation warnings. |
| Query-run service contracts | local acceptance still required | `tests\\test_query_run_service.py` reproduced the Python 3.13 Windows event-loop block. Faulthandler shows `asyncio.run()` stuck in `socket._fallback_socketpair` before LexRAG service code executes. This is neither an SSE pass nor a product failure. |
| Judge diagnostic plumbing | completed later | The strict SHA-bound calibration loader/reducer and blind OpenAI-compatible Judge runner later completed a 100/100 recovery run; the authoritative details appear in the completed Judge section below. |
| Ragas environment | completed later | The initial shared-environment attempt was abandoned. Ragas 0.3.9 was installed in a dedicated environment and the final 100-row diagnostic is recorded below. |

The historical isolated-runner observations above are superseded for SSE by
the local PowerShell evidence: the combined API/service/runtime-registry suite
completed **11/11** in **29.26 seconds**. The remaining Gate B action is
browser E2E, not backend SSE acceptance.

## 2026-10-30 Ragas environment correction and runner evidence

The previous table records the isolated-runner installation attempt only. The
user subsequently verified a dedicated evaluation environment with
`ragas==0.3.9` and a clean `pip check`. It was later recreated in the main
repository as `.venv-stage8-ragas`; the former external environment was
removed after that verification. At this point in the chronology the
environment was ready; it did **not** yet create a score or close the
Judge/Ragas calibration gate.

`scripts/run_stage8_ragas.py` is now available for the live diagnostic. It
uses only `STAGE8_RAGAS_API_KEY` from the invoking process, stores no
credential, binds all outputs to the reviewed JSONL and manifest hashes, and
preserves individual provider failures. Its only supported metrics are
Faithfulness and context precision without reference. The artifact has no
independently authored `reference_answer`, so answer correctness, context
recall, and factual correctness remain explicitly unsupported.

## 2026-10-30 completed Ragas diagnostic

The final immutable evidence is
`ragas/stage8_ragas_100_final.summary.json` and its adjacent JSONL/config
files. It binds the reviewed 100-row artifact and review manifest by SHA-256,
uses `ragas==0.3.9`, `deepseek-chat`, temperature `0.0`, and two connection
retries. Result: **100 completed, 0 execution errors, 100 unique IDs**.

| Metric | Result | Interpretation boundary |
| --- | ---: | --- |
| Faithfulness | 0.7400 | Diagnostic estimate of whether the produced answer is supported by retrieved text; not legal-answer correctness. |
| Context precision without reference | 0.8881 | Diagnostic estimate of retrieval-context relevance without an independently authored answer. |

The first run recorded 50 connection failures rather than excluding them. A
recovery run reused completed rows and retried only failed ones (50/100 →
99/100 → 100/100). The artifacts preserve this history. There is still no
independent `reference_answer`, so answer correctness, context recall,
factual correctness, and answer relevancy must not be claimed from this run.

## 2026-10-30 completed blind Judge calibration

The first Judge artifact, `judge/stage8_judge_100.jsonl`, is retained as a
failed execution record: all 100 calls returned `BadRequestError`. The
provider requires an explicit JSON-output instruction and example when JSON
mode is selected. The Judge prompt was repaired under test first; the focused
Judge/calibration suite then passed 10/10.

The recovery artifacts `judge/stage8_judge_100_recovery.jsonl`, adjacent
configuration, and `stage8_judge_100_recovery_calibration.json` are the valid
evidence. They bind the reviewed 100-row artifact and its review manifest by
SHA-256 and use DeepSeek `deepseek-chat`, temperature `0.0`, and prompt
version `stage8-diagnostic-judge-v2`.

| Result | Value | Interpretation boundary |
| --- | ---: | --- |
| Completed / execution errors | 100 / 0 | The blind Judge run itself completed. |
| Agreement with human review | 97.00% | Numerically high because 97 of 100 human labels are positive. |
| True positive / true negative | 97 / 0 | Judge accepted each of the 97 human-approved answers. |
| False positive / false negative | 3 / 0 | Judge accepted every human-rejected answer and therefore detected none of the available negative cases. |

The three false positives are `round2-adjacent-038`, `round2-multihop-009`,
and `round2-multihop-020`. In all three, human review found that the retrieved
statutes did not answer the asked loss/causation question and that the answer
gave only an unsupported non-answer; Judge instead marked the abstention and
coverage as adequate. Therefore this Judge is useful as a reproducible
secondary diagnostic, but its negative-case sensitivity is 0/3 in this sample
and it cannot replace the 100-row human legal review.

## 2026-10-30 isolated Docker acceptance evidence

The Docker checks used the explicit, disposable Compose project
`lexrag-stage8-acceptance`, with its own named MySQL, Redis, Chroma, uploads,
and law-snapshot volumes. The generated `.env.docker.stage8` is git-ignored;
it contains locally generated credentials and is not an evidence artifact.

| Check | Result | Evidence / boundary |
| --- | --- | --- |
| Compose configuration and image build | passed | `docker compose --env-file .env.docker.stage8 --project-name lexrag-stage8-acceptance config --quiet` and the isolated build passed. |
| Cold start, migration, bootstrap and API readiness | passed | `reports/deployment/lexrag-stage8-acceptance/deployment-verification.json` records `compose_config`, `compose_build`, `compose_up`, `migration_completed`, `bootstrap_completed`, and `api_readiness` as `PASS`. All eight catalogue statutes were available from the read-only local BGE-M3 runtime setup. |
| Authenticated gateway and version-read health | passed | After gateway recovery, a disposable administrator completed `POST /api/auth/login`, `GET /api/auth/me`, and admin-protected `GET /api/law-updates/version-chains`. The final version-chain list was empty, as expected for the new isolated database. Tokens and passwords were never persisted in logs or reports. |
| Async document upload | passed | A project-owned public fixture `tests/fixtures/sample_text_law.pdf` was uploaded only to an isolated document library. The Celery job reached `READY`, with `page_count=1`, `character_count=88`, and `chunk_count=1`; Worker logs show local BGE-M3 and Chroma execution. It was not added to the statute knowledge base. |
| Restart recovery | passed for gateway/API recovery | The first combined restart exposed a stale Nginx upstream address and `502`. A test-first fix makes Nginx use Docker DNS (`127.0.0.11`) to resolve the API service at request time, while explicitly preserving the `/api` prefix rewrite. After rebuilding only Web, API was forcibly recreated with all volumes retained; without restarting Web, `/api/health/ready`, real gateway login, and authenticated version-chain GET all passed. `tests/test_worker_nginx_contract.py` passed 8/8. |
| Authenticated runtime query | not run | The isolated Docker environment was deliberately created without a real runtime LLM credential. A Ragas evaluation key must not be reused or written into Docker configuration. No query success is claimed. |
