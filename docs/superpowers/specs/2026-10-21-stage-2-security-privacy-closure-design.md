# LexRAG v3.0 Stage 2: Security, Authorization, and Privacy Closure Design

**Date:** 2026-10-21

**Status:** Approved design; implementation pending

## 1. Objective

Close the Stage 2 security boundary without changing retrieval algorithms, legal prompts, datasets, or legal-answer evaluation. The implementation must prevent unauthorized knowledge-base mutation, cross-user or cross-organization access, credential disclosure, server-side request forgery, sensitive legal content in routine logs, and unbounded file or model-resource consumption.

LexRAG remains a modular FastAPI monolith. This stage adds reusable security services and applies them consistently to the existing endpoints; it does not introduce microservices or claim production readiness before Stage 3 deployment acceptance.

## 2. Confirmed product decisions

- `GET /graph` and `POST /graph/query` become authenticated read-only endpoints.
- The current law graph remains a shared public-law dataset. The authorization interface must still carry organization context so future private-document relations cannot accidentally inherit a global access path.
- Shared annual cases require authentication and `cases:read`. They do not become organization-owned in this stage.
- The unused `GET /verify/{query_id}` endpoint and the process-level `query_results` dictionary are removed. Verification remains in the `/query` response and persisted session messages.
- The legacy `POST /upload` endpoint is retained only as an organization-scoped administrator operation. Its request must identify a target statute knowledge base; it may not write the global default index.
- JWT browser authentication moves to an HttpOnly cookie. Bearer tokens remain supported for CLI clients, evaluation scripts, and API compatibility.
- Browser-supplied LLM API keys are ephemeral in-memory values and are cleared on page refresh.

## 3. Scope

### In scope

- centralized environment-sensitive security settings and production startup validation;
- request IDs, stable error envelopes, safe exception handling, and content-safe logging;
- authenticated and organization-aware authorization for all product resources;
- development-only open registration and explicit production administrator bootstrap;
- trusted runtime LLM provider policy and guarded custom Base URLs;
- DNS/IP/port validation and disabled HTTP redirects for custom LLM endpoints;
- model-name, timeout, output-token, retry, and concurrency limits;
- chunked upload limits, filename normalization, MIME/magic checks, archive-bomb checks, and isolated temporary storage;
- endpoint-specific rate limits and repeat-submission protection;
- append-only, redacted audit events for sensitive actions;
- frontend removal of JWT and API keys from `localStorage`;
- focused security tests, complete regression tests, and truthful documentation.

### Out of scope

- Docker cold-start and reverse-proxy acceptance, which remain Stage 3;
- a distributed rate-limit or idempotency store across multiple API replicas;
- malware scanning or a standalone credential-broker service;
- private case collections or private graph relations;
- retrieval, prompt, embedding, ranking, or legal-quality changes;
- formal legal-effect evaluation, which remains Stage 8;
- pushing commits to a remote repository.

## 4. Selected architecture

Security policy is concentrated in small units with explicit contracts:

```text
HTTP request
  -> RequestSecurityMiddleware
       request ID / response security headers / stable unhandled-error response
  -> authentication
       HttpOnly JWT cookie or Bearer compatibility token
  -> AuthorizationContext
       user + organization + live database permissions
  -> endpoint policy
       permission + resource ownership + rate/idempotency class
  -> RuntimeLLMPolicy or UploadSecurityPolicy when applicable
  -> existing domain service
  -> redacted audit event and response
```

The implementation adds or consolidates four responsibilities:

1. `SecuritySettings` describes application mode, cookie behavior, provider allowlists, runtime LLM limits, upload limits, and endpoint rate limits. Production validation fails before the application begins serving traffic when critical values are unsafe.
2. `RequestSecurityMiddleware` creates or accepts a strictly formatted request ID, returns it as `X-Request-ID`, installs baseline security headers, and turns otherwise unhandled exceptions into a stable error envelope.
3. `RuntimeLLMPolicy` resolves trusted providers, authorizes custom endpoints, validates network destinations, normalizes model configuration, and creates redirect-disabled HTTP clients with bounded timeouts and retries.
4. `UploadSecurityPolicy` performs bounded reads and content validation and writes only to organization/knowledge-base-scoped temporary locations.

Authorization remains in `AuthorizationService`, backed by live database membership and permissions. Endpoint modules consume authorization dependencies instead of rebuilding role rules locally.

## 5. Authentication and registration

The browser login and registration responses set a JWT cookie with `HttpOnly` and `SameSite=Lax`. `Secure` is required in production and configurable for local HTTP development. The frontend sends credentialed same-site requests and no longer writes the JWT to browser storage. The API continues to accept `Authorization: Bearer` for non-browser clients; if both cookie and header are present, the explicit Bearer token takes precedence to keep CLI behavior deterministic.

Open registration is permitted only when `app_mode=development`. Production returns a stable disabled-registration response. Production administrator creation uses an explicit bootstrap command or function that requires a configured bootstrap credential and never grants administrator rights based on registration order. The existing “first local user is admin” behavior remains development-only.

Authentication failures use the same external message regardless of whether the username exists. Login and registration are rate-limited by client address. Usernames, passwords, tokens, and decoded JWT errors are not written to routine logs.

## 6. Authorization matrix and IDOR prevention

Only `/`, `/health`, and `/auth/login` are always anonymous. `/auth/register` is anonymous only in development mode.

Authenticated read operations include dashboard data, visible knowledge bases, document results, sessions, favorites, scenarios, shared cases, and the shared public-law graph. The required permissions are enforced consistently:

- `knowledge_bases:read` for knowledge-base, document, and graph reads;
- `cases:read` for case sources, case details, and similar-case lookup;
- `queries:create` for legal questions;
- `knowledge_bases:manage` for knowledge-base creation, rebuilding, deletion, statute upload, document upload, and document retry;
- existing specialized permissions for members, prompts, agents, audit, analytics, and law updates;
- new `runtime_models:custom` permission for production custom LLM endpoints.

Resource lookups enforce these ownership keys before returning data:

| Resource | Required scope |
|---|---|
| Knowledge base and document | organization ID + resource ID/slug |
| Session, favorite, scenario | organization ID + current user ID + resource ID |
| Prompt and agent configuration | organization ID + management permission |
| Law-update subscription/event | organization ID + management permission |
| Shared case and public-law graph | authenticated read permission |

Missing resources and inaccessible resources both return 404 where revealing existence would create an enumeration channel. Permission failures that do not expose resource existence return 403.

## 7. Runtime LLM and SSRF policy

Provider resolution occurs after authentication and organization authorization. Default operation accepts only HTTPS Base URLs whose canonical hosts and ports match a configured trusted-provider allowlist. URLs containing user information, fragments, ambiguous host syntax, or non-default dangerous ports are rejected.

A custom Base URL is accepted only when either:

- the application runs in development mode; or
- the authenticated user has `runtime_models:custom`.

Custom destinations must use HTTP or HTTPS, but production custom destinations require HTTPS. Hostname resolution is performed before the request. Every returned address must be a globally routable unicast address. Loopback, unspecified, private, link-local, multicast, reserved, and cloud-metadata destinations are rejected for both IPv4 and IPv6. Literal IPs pass through the same classification. Validation errors expose no resolved addresses.

The LLM HTTP clients do not follow redirects, so a validated public endpoint cannot redirect the client to an internal target. The transport receives bounded connect/read/write/pool timeouts and a bounded retry count. Model names use a strict length and character contract. Maximum output tokens and concurrent LLM calls are bounded by settings and cannot be increased by request headers.

This validation substantially reduces SSRF risk but is not described as DNS pinning. Multi-replica egress policy, proxy enforcement, and infrastructure network controls remain Stage 3 concerns.

## 8. Credential and sensitive-data handling

The frontend settings store retains provider, model, and non-secret Base URL preferences, but the API key exists only in Pinia memory. Reloading the page clears it. The request interceptor reads the key from memory through a narrow accessor instead of browser storage.

API keys and JWTs are never written to the database, cache payload, audit metadata, trace metadata, exception response, or normal logs. Cache scoping uses a provider/model identifier and the existing user/session/knowledge-base scope, never an API-key or authorization-header hash.

Routine request logs contain only request ID, numeric user and organization identifiers when available, route template, status, latency, payload length, and approved structural counters. They do not contain questions, answers, prompts, contract text, document text, filenames supplied by a user, credentials, or model reasoning.

## 9. Error, logging, and audit behavior

Expected validation and domain errors retain stable 4xx status codes and safe messages. Unexpected failures return a stable body containing `code="INTERNAL_ERROR"`, a generic Chinese message, and the request ID. No endpoint returns `str(exception)` for a 500 response.

Server logs may retain stack traces for operational diagnosis, but the log message uses a controlled operation name and exception class rather than interpolating exception text or request content. A logging redaction filter provides defense in depth for authorization headers and known credential field names.

Sensitive actions call a shared audit helper that writes append-only events containing event ID, actor, organization, action, resource type and ID, result, request ID, timestamp, and scalar allowlisted metadata. Query audit retains only hashes, lengths, verification status, and structural counters. Audit failure remains non-fatal to a completed legal query but is logged without sensitive payloads.

## 10. Upload and parser protection

Document-library uploads, batch uploads, contract-file scenarios, and any retained statute upload share the same bounded reader and validation primitives.

The upload path performs these steps in order:

1. authenticate and authorize the target organization and knowledge base;
2. normalize the client filename to a display-only basename and generate a random storage ID;
3. read fixed-size chunks while hashing and counting bytes, aborting immediately at the configured limit;
4. compare the permitted extension, declared MIME type, and detected magic bytes;
5. inspect DOCX ZIP metadata before extraction, enforcing entry-count, per-entry, total-uncompressed-size, and compression-ratio limits;
6. enforce configured PDF page, extracted-character, parser-time, OCR-time, and Celery retry limits;
7. write temporary data beneath an organization/knowledge-base-specific `.incoming` directory;
8. submit the existing domain task and clean temporary data on every failure path.

Batch uploads apply limits independently to each file and also enforce a maximum file count and aggregate byte limit. Failure records retain an error code and structural metadata, not extracted text, raw filenames, or exception strings.

FastAPI enforces application-level body, upload, and concurrency bounds in this stage. Matching Nginx and Celery values are documented or added to configuration, while their real cold-start and multi-process acceptance remain Stage 3.

## 11. Rate limiting, concurrency, and repeat submission

Rate-limit classes are configured separately for login, registration, query, upload, retry, and administrative writes. Anonymous authentication limits use a normalized client address; authenticated limits use user and organization IDs. Responses use `429` with a stable retry hint and do not expose internal counters.

Stage 2 provides a bounded, process-local implementation behind a replaceable interface. This is sufficient for the current single-process application and automated acceptance, but it is explicitly not a distributed production guarantee. Stage 3 will bind the same interface to Redis or enforce equivalent limits at the reverse proxy.

Existing domain protections remain authoritative where they are stronger:

- upload SHA-256 deduplication prevents duplicate document jobs;
- failed-state checks constrain document and scenario retries;
- knowledge-base rebuild busy state prevents concurrent destructive rebuilds;
- law-update observation remains content-idempotent.

Selected write endpoints additionally accept `Idempotency-Key`. The stored record is scoped by user, organization, route, and an approved request fingerprint and never stores request bodies or credentials. Replays return the original safe result or the current task identifier.

## 12. Production startup validation

Before serving traffic in production mode, LexRAG refuses startup when any of the following holds:

- the JWT secret equals the development default or is below the configured strength threshold;
- the effective database password is the documented demonstration password;
- secure cookies are disabled;
- open registration or first-user administrator promotion is enabled;
- trusted provider configuration is empty or malformed;
- critical upload, timeout, retry, or concurrency limits are missing or outside safe ranges;
- required administrator-bootstrap configuration is absent when no administrator exists.

Failure messages identify the configuration key and remediation category without printing secret values.

## 13. Test strategy

Implementation follows red-green-refactor. Each behavior receives a failing test that is observed failing for the intended reason before production code is changed.

### Authorization and IDOR

- anonymous, member, lawyer, administrator, and custom-runtime permission cases;
- cross-user and cross-organization access attempts for every owned resource type;
- authenticated graph and case reads;
- administrator-only statute upload into an owned knowledge base;
- removal of the legacy verification endpoint and global result registry.

### Authentication and configuration

- HttpOnly/SameSite/Secure cookie attributes and Bearer compatibility;
- frontend absence of JWT storage;
- development registration and production registration refusal;
- explicit administrator bootstrap and absence of production first-user promotion;
- startup refusal for unsafe production secrets and limits.

### SSRF and resource limits

- trusted providers and canonical URL normalization;
- URL credentials, private/loopback/link-local/metadata IPv4 and IPv6, dangerous ports, and mixed DNS answers;
- custom-endpoint authorization and disabled redirects;
- model format, timeout, token, retry, and concurrency bounds.

### Privacy, uploads, and errors

- sensitive marker strings absent from logs, audit rows, caches, traces, and error responses;
- chunked oversize failure, filename traversal, MIME/magic mismatch, archive bombs, batch totals, and cleanup;
- organization-specific temporary paths;
- stable unhandled-error envelopes with request IDs;
- audit event shape and metadata filtering.

### Completion verification

- Ruff over changed Python files;
- focused Stage 2 tests;
- complete backend test suite;
- frontend contract tests and production build;
- no formal legal-quality evaluation and no modification of published metrics.

## 14. Documentation and commit structure

After automated verification, update `.env.example`, README security/development instructions, the feature ledger, and the external roadmap. Documentation must distinguish application-level automated verification from real multi-process deployment acceptance. It must not claim that process-local rate limiting, development custom endpoints, or configuration templates constitute production hardening.

Implementation commits should remain reviewable and local:

1. approved design and implementation plan;
2. security policy, authentication, and request-boundary infrastructure;
3. endpoint authorization, uploads, audit, and resource protection;
4. frontend credential handling, documentation, and acceptance evidence.

No remote push is part of this stage.

## 15. Acceptance criteria

Stage 2 is complete only when all of the following are true:

- no anonymous endpoint can mutate a knowledge base or read graph/case/product data;
- resource ownership checks prevent cross-user and cross-organization access;
- `/verify/{query_id}` and process-level query-result storage no longer exist;
- production registration and first-user administrator promotion are disabled;
- browser JWTs use HttpOnly cookies and browser API keys are memory-only;
- untrusted LLM destinations, private networks, unsafe redirects, and unbounded model settings are rejected;
- file limits and type validation occur during bounded processing, with isolated paths and cleanup;
- routine logs, audits, traces, caches, and errors do not contain supplied sensitive marker content;
- request IDs, rate limits, repeat-submission defenses, and redacted audit events cover the identified endpoints;
- unsafe production settings prevent startup;
- focused and full automated verification pass;
- documentation records the remaining Stage 3 infrastructure boundaries and makes no Stage 8 quality claim.
