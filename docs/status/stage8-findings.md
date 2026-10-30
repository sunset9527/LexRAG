# Findings: Stage 8 formal retrieval and routing evaluation

## Requirements

- Consume only `data/evaluation/stage8/stage8_frozen_280.jsonl` via the formal validator.
- Report ranking metrics by overall, law, question type, and difficulty.
- Report automatic router Top-1 only for single-law rows and candidate recall for single- and cross-law rows.
- Preserve abstention rows and execution errors without silently changing denominators.

## Research Findings

- `src/evaluation/retrieval_evaluation.py` requires the legacy single-law fields and cannot consume formal records.
- `src/evaluation/multikb_retrieval.py` performs per-slug retrieval but assumes `query` and one `knowledge_base_slug`.
- `KnowledgeBaseRouter.route()` returns candidates and selected slugs deterministically from the released catalogue.
- `run_manifest.py` already binds dataset bytes, legal-source manifests, collection names, runtime identity, and Git commit.
- The Stage 4 provenance snapshot supplies all eight explicit collection names, version IDs, source hashes, embedding fingerprint, index schema version, and chunk count needed by the later CLI.
- `LawRetriever.retrieve_optimized()` (RRF) needs the correct Chinese `law_name`; the CLI must derive it from the existing statute catalog instead of accepting a caller-supplied string or falling back to the Civil Code.

## Technical Decisions

| Decision | Rationale |
|---|---|
| New `stage8_retrieval_evaluation` module | Isolates Stage 8 contract from legacy reports. |
| Structured item outcomes | Supports failures and later report/audit layers without re-running retrieval. |
| CLI uses explicit `slug=collection` arguments | Prevents accidental evaluation against an implicit/default collection. |
| Retrieval callback returns slug-qualified article IDs | Makes cross-law scoring unambiguous even when laws share a numbered article. |
| CLI reads collection names only from the Stage 4 snapshot | Prevents accidental measurement against a default or caller-substituted collection. |
| Formal CLI must verify the frozen manifest | Strict row validation alone permits an approved subset; byte hashes and immutable 280/320/460 counts bind the intended release data. |
| Dependency versions belong in the run manifest | The release design requires them; a local result must not rely only on package names installed by convention. |
| Chroma local client requires write access even for queries | The original verified directory is read-only under the current workspace policy; evaluate a byte-for-byte working copy and record the copy path. |
| Legacy Stage 4 collections may omit a collection-level source hash | The snapshot validates each chunk's article/source provenance; the formal CLI must use the same fail-closed fallback. |
| HNSW repair method | A new Chroma copy can regenerate physical segments by reinserting verified stored embeddings, documents, IDs and metadata; this neither re-embeds text nor changes frozen legal evidence. |
| Windows persistent HNSW runtime boundary | A collection can pass a same-process repair check yet fail after a reopen, and loading the local BGE runtime before a persistent Chroma read triggers the same failure. Runtime retrieval therefore needs a process-local vector mirror built from a verified immutable payload, rather than querying persisted HNSW segments. |
| Runtime payload export | `scripts/export_stage8_runtime_payload.py` reads the eight snapshot-bound collections before any embedding model is loaded, validates their identity/count/article catalog, and emits a gzip payload plus SHA-256 manifest. The API opens an in-memory Chroma mirror when `RUNTIME_VECTOR_PAYLOAD_PATH` is configured. |

## Resources

- `docs/superpowers/specs/2026-10-26-stage-8-final-validation-design.md`
- `src/retrieval/knowledge_base_router.py`
- `src/evaluation/run_manifest.py`

## Knowledge-graph removal findings (2026-10-29)

- The active graph feature spans `src/graph`, `src/retrieval/graph_retriever.py`, the `/graph` routes, workflow graph-retrieval nodes, startup/readiness, bootstrap, Compose, front-end graph views and the `agent_configs.graph_search_enabled` column.
- Graph retrieval is a one-hop optional branch after statute retrieval. It has no demonstrated Stage 8 retrieval or answer-quality benefit.
- `src/retrieval/retrieval_optimizer.py` reference expansion reads statute metadata directly and must remain; it does not depend on NetworkX or graph artifacts.
- The approved hard-delete specification is `docs/superpowers/specs/2026-10-29-remove-knowledge-graph-design.md` at commit `b00f0db`.
- Implementation deleted the graph feature surface and `networkx`; `20261029_01_drop_agent_graph_config.py` drops the retired database column while preserving a downgrade path.
- The Stage 8 pure evaluator is independent of the graph feature and still passes its 71-test suite after removal.
- A browser BYOK key cannot be read by a local batch process by design. The Stage 8 answer-review runner therefore requires process-local LLM and LexRAG authentication environment variables and never writes either value into review artifacts.
- In payload runtime mode, version selection previously checked only the retired persistent Chroma collection, causing `VERSION_COLLECTION_NOT_READY` before retrieval. Readiness now accepts only an immutable-payload collection that passes its artifact and per-collection SHA-256 checks; all other collections remain unavailable.
- The first two live answer-review runs are failed execution artifacts only: a business `HTTP_400` was retried immediately and amplified into the app's `HTTP_429` limit. The runner now fails non-transient client errors once and retries only transport/rate-limit faults.
- The isolated Windows test runner cannot execute `tests/test_query_run_api.py` to completion: faulthandler shows Python 3.13 blocking inside `socket._fallback_socketpair` while `asyncio.run()` creates a local event loop, before any FastAPI route or LexRAG code runs. This is an environment limitation, not evidence that SSE passes or fails; retain the test as a local/Docker acceptance gate.

## Gate A calibration findings (2026-10-30)

- The audited input is `reports/evaluation/stage8/answer_reviews/stage8_answer_review_merged_100.jsonl`; its adjacent manifest binds the merged JSONL, sample, and the two successful workflow-run hashes.
- Every row already contains the completed `human_review` boolean, reviewer, review timestamp, review note, source evidence, and a workflow output including answer, citations, verification data, trace, attempts, and latency.
- `requirements.txt` contains neither `ragas` nor a dedicated Judge SDK. Gate A must therefore keep both adapters optional and fail closed with an explicit `NOT_RUN` reason when dependencies or process-local credentials are absent.
- The candidate worktree has no local `.venv`; diagnostics and tests must point explicitly at the existing verified project virtual environment rather than silently installing packages or mutating dependency state.
- Existing Stage 8 CLI patterns use dependency-free JSONL inputs, atomic artifact writes, SHA-256 bindings, and process-local credentials. Gate A can preserve that boundary by calibrating externally materialized Judge/Ragas rows; live provider execution remains a separate optional adapter concern.
- `run_manifest.py` already rejects common secret-bearing metadata keys and provides a precedent for recording only safe runtime identifiers. Gate A should preserve evaluator model/temperature/version metadata, not keys, endpoints with credentials, or raw prompts.
- The verified virtual environment includes `openai==2.44.0` but not `ragas`. The Judge adapter can therefore be implemented without changing dependency state, while Ragas requires an explicit versioned dependency decision and a compatible evaluation-model configuration.
- The Judge input hides `human_review` from the evaluator and confines its declared scope to evidence fidelity, coverage, abstention appropriateness, and clarity. Its execution helper preserves provider errors as structured `execution_error` rows.

## Gate B local acceptance findings (2026-10-30)

- `tests/test_query_runtime_registry.py` passed 3/3 in the verified Windows environment. The run emitted only two known dependency deprecation warnings.
- `tests/test_query_run_service.py` reproduced the existing local blocker: its second test stalls while `asyncio.run()` creates a Windows Proactor event loop. The faulthandler trace ends in `socket._fallback_socketpair` / `socket.accept`, before the test's LexRAG service invocation.
- This does not demonstrate an SSE feature failure or success. Service/API SSE acceptance and browser E2E remain required in a local/Docker runtime whose event loop can initialize.

## Ragas installation findings (2026-10-30)

- Official Ragas installation guidance is `pip install ragas`; PyPI lists `ragas==0.4.3` as supporting Python 3.9+.
- Installing `ragas==0.4.3` into the shared verified project environment encountered a Windows file lock while pip attempted to replace `huggingface_hub`; the existing imports still work, but the shared environment now emits an invalid-distribution warning. Do not use it for Ragas.
- A dedicated `.venv-stage8-ragas` was created in the isolated candidate. In the current isolated executor, pip dependency resolution (including `instructor` backtracking) is terminated before it reaches an installation result, including when the legacy resolver is requested. `ragas` remains absent and no Ragas metric must be reported.

## Ragas input contract findings (2026-10-30)

- The 100-row merged review artifact has a question, workflow answer and citation `original_text` for every row. The materializer verified 100/100 usable Ragas records.
- It has no independently authored `reference_answer`. The legal source text is evidence, not a gold natural-language answer, so `context_recall`, `factual_correctness` and `answer_correctness` cannot be calculated honestly.
- With the selected Ragas 0.3.9 API, `Faithfulness` and `LLMContextPrecisionWithoutReference` are available from the actual environment. Answer relevancy additionally requires a declared evaluation embedding configuration, so it remains `NOT_RUN` until that configuration is explicitly supplied.

## Ragas dedicated-environment verification (2026-10-30)

- The user verified `E:\\python\\LexRAG-stage8-ragas\\Scripts\\python.exe`: `import ragas; print(ragas.__version__)` returned `0.3.9`, and `python -m pip check` returned `No broken requirements found`.
- Ragas 0.3.9 confirms both planned metrics require only `user_input`, `response`, and `retrieved_contexts`, which are present in every materialized Stage 8 record.
- The new runner invokes Ragas per record with `raise_exceptions=True`; network/provider failures are retained as `execution_error` rows. Invalid metric output remains a CLI failure rather than being misclassified as a provider outage.

## Completed Ragas diagnostic (2026-10-30)

- Final summary: `reports/evaluation/stage8/ragas/stage8_ragas_100_final.summary.json`, schema `lexrag.stage8-ragas-diagnostic`, status `COMPLETE`, 100 completed, 0 execution errors, and 100 unique sample IDs.
- On the immutable 100-row reviewed artifact (SHA-256 `69d3d4670fb9f748f9cab90b489d7368ffc21ec2c43144f074f3fad8fb99fae1`), Ragas 0.3.9 with `deepseek-chat`, temperature 0.0 and two connection retries reported Faithfulness `0.7400433334977492` and context precision without reference `0.8881111110449865`.
- The original run had 50 `APIConnectionError` results in a strict alternating pattern because the runner explicitly set `max_retries=0`. The recovery artifacts preserve that history: 50/100, then 99/100, then the complete final 100/100 artifact. No success rows were rerun during recovery.
- No independent reference answer or evaluation embeddings were introduced. Consequently answer correctness, context recall, factual correctness, and answer relevancy remain unsupported rather than receiving invented scores.
