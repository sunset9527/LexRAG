# LexRAG v3.0 Stage 2 Security and Privacy Closure Implementation Plan

**Design:** `docs/superpowers/specs/2026-10-21-stage-2-security-privacy-closure-design.md`

**Goal:** Close the documented Stage 2 authorization, SSRF, privacy, upload, and resource-protection gaps without changing legal retrieval or answer-quality behavior.

## Task 1: Establish environment and startup security contracts

### Tests first

Add `tests/test_security_settings.py` for development defaults, production refusal with the demonstration JWT/database secrets, production cookie/registration requirements, and bounded upload/LLM settings. Observe failure because these settings and validation do not exist.

### Minimal implementation

Extend `config.py` with explicit application mode and bounded security configuration. Add a side-effect-free production validation function and invoke it at the start of FastAPI lifespan before database or model initialization.

## Task 2: Add request IDs, stable errors, and safe logging

### Tests first

Add API tests proving valid request IDs are preserved, invalid IDs are replaced, every response carries `X-Request-ID`, unhandled errors return `INTERNAL_ERROR` without exception text, and supplied sensitive markers never enter captured logs.

### Minimal implementation

Add request-security middleware and a safe error envelope. Replace raw query and exception interpolation on active endpoints with structural logging. Add a narrow redaction filter as defense in depth.

## Task 3: Move browser authentication to HttpOnly cookies

### Tests first

Add tests for login/register cookie attributes, cookie authentication, Bearer compatibility, development registration, production registration refusal, and development-only first-user administrator promotion.

### Minimal implementation

Update the authentication dependency to accept a cookie or Bearer token, set/clear the browser cookie, guard registration by application mode, and provide explicit administrator bootstrap behavior for production.

## Task 4: Centralize runtime LLM and SSRF policy

### Tests first

Add `tests/test_runtime_llm_policy.py` for trusted providers, custom-endpoint permissions, URL credentials, dangerous ports, private/loopback/link-local/metadata IPv4 and IPv6, mixed DNS results, strict model names, bounded settings, and disabled redirects. Confirm current scheme-only validation fails these cases.

### Minimal implementation

Create a runtime policy service, add `runtime_models:custom`, validate `/query` and scenario model headers through it, and route all runtime LLM construction through redirect-disabled bounded clients.

## Task 5: Close endpoint authorization and IDOR gaps

### Tests first

Add focused route tests for authenticated graph access, case read permission, administrator-only scoped statute upload, and cross-organization resource hiding. Add a contract test proving `/verify/{query_id}` and `query_results` are absent.

### Minimal implementation

Apply shared authorization dependencies to graph and case routes. Change `/upload` to require a target owned knowledge base and the management permission. Remove the legacy verification endpoint and process-level result store. Audit all resource routers against the approved ownership matrix and repair only demonstrated gaps.

## Task 6: Add bounded upload validation and isolated paths

### Tests first

Add unit tests for chunked oversize rejection, safe filenames, PDF/DOCX magic validation, extension/MIME mismatch, DOCX archive bombs, batch totals, organization paths, and cleanup. Add endpoint tests for document and scenario uploads using the shared policy.

### Minimal implementation

Create reusable upload validation primitives and replace `await file.read()`/`write_bytes()` on active upload paths. Apply parser/page/character/task limits without changing successful parsing semantics.

## Task 7: Add rate limiting, repeat-submission protection, and audit coverage

### Tests first

Add deterministic tests with an injected clock for authentication, query, upload, retry, and administrative rate classes. Test scoped idempotency records and redacted audit events for sensitive writes.

### Minimal implementation

Add a bounded process-local limiter and idempotency service behind replaceable interfaces. Apply them through endpoint dependencies/helpers and reuse existing SHA, retry-state, busy-lock, and law-update idempotency where stronger.

## Task 8: Remove browser secret persistence

### Tests first

Extend frontend contract tests to fail when `lexrag_token` or `lexrag_user_api_key` is stored in `localStorage`, and to require credentialed cookie requests plus an in-memory API-key accessor.

### Minimal implementation

Update the auth/settings stores and Axios client. Keep non-secret provider/model/Base URL preferences persistent, keep the API key in memory, and use `withCredentials` for the JWT cookie.

## Task 9: Focused and full verification

Run in order:

1. Ruff over changed Python files.
2. Stage 2 security, authorization, upload, audit, query, scenario, and authentication tests.
3. Complete backend suite using `reports/quality/pytest-tmp`.
4. Frontend contract tests and `vue-tsc -b && vite build`.

Use systematic root-cause debugging for any unexpected failure. Do not alter evaluation data or run formal legal-quality evaluation.

## Task 10: Truthful closure documentation

Update `.env.example`, README, `docs/status/feature-ledger.md`, and the external `RAG法律.md` with exact automated evidence. State that rate limiting/idempotency are process-local and that reverse-proxy/multi-replica enforcement remains Stage 3. Commit cohesive local changes and do not push.

## Non-negotiable checks

- Every production behavior change is preceded by a failing automated test.
- No supplied question, answer, contract text, document text, API key, JWT, or password appears in routine logs, audits, caches, traces, or error responses.
- Resource access is scoped before data is returned or mutated.
- SSRF validation rejects every resolved non-public address and never follows redirects.
- Upload limits are enforced while reading, not only after a complete destination file is written.
- No retrieval, prompt, embedding, ranking, dataset, label, or published legal metric is changed.
- No remote push or history rewrite occurs.

## Completion record — 2026-10-22

- Stage 2 code baseline: `9c9313b`.
- Full backend regression in normal Windows PowerShell: `300 passed`, 4 dependency warnings, 18.34 seconds.
- Frontend contracts: `4 passed`; Vue type checking and production build passed.
- Ruff passed on the changed Python surface and the privacy-hardened `app/` and `src/` paths.
- Existing SHA deduplication, retry-state guards, knowledge-base busy locks and law-update event identity provide repeat-submission protection; the request limiter remains deliberately process-local until Stage 3 deployment work.
- No evaluation data, retrieval/ranking behavior, labels or published legal metrics changed. No remote push or history rewrite was performed.
