# LexRAG Feature Ledger

**Baseline:** code through `697a2d8`, inventoried and verified 2026-10-18

## State definitions

- **Implemented:** the route/service/code path exists.
- **Automation passed:** relevant automated tests passed on the current grouped code content.
- **Real-chain verified:** a real local dependency chain was exercised and the evidence is retained with sufficient context. A historical smoke test on an uncommitted tree is labeled historical rather than silently promoted to the current baseline.

## Ledger

| Capability | Entry point | Core implementation | Data/runtime dependency | Permission boundary | Failure/degradation behavior | Automated evidence | Real-chain status |
|---|---|---|---|---|---|---|---|
| Authentication and identity | `/auth/register`, `/auth/login`, `/auth/me` | `app/api/auth.py`, `AuthService` | MySQL, JWT secret | Register/login public; `/me` authenticated | Stable 4xx for invalid credentials; production registration policy still pending | `test_admin_rbac_api.py`, `test_rbac_service.py` and related tests passed | Historical local login/proxy smoke only; production bootstrap not verified |
| Organization and RBAC | `/admin/organization`, members, usage, audit, agent config | `AuthorizationService`, admin router, RBAC models | MySQL | Organization roles and explicit permission codes | 401/403 on missing identity or permission | Platform-focused suite passed | No retained multi-tenant deployment acceptance |
| Knowledge-base management | `/knowledge-bases`, rebuild, law listing, delete | `KnowledgeBaseService`, `LawIndexer` | MySQL, Chroma, embedding model | `knowledge_bases:read/manage` plus organization scope | Busy/not-ready and authorization errors are explicit | Knowledge-base and organization tests passed | Historical local collections exist; clean bootstrap not verified |
| Main legal query | `POST /query` | Shared compiled LangGraph `StateGraph`, typed invocation state/context, evidence ledger, verifier | Chroma, BM25, BGE-M3, optional case/graph sources, external LLM, MySQL/Redis for session/cache | Authenticated `queries:create` plus knowledge-base visibility | Retrieval branches degrade structurally; failed citation repair returns evidence-insufficient output; failed results are not cached | Graph structure/branch/API tests passed; full backend suite 238 passed | Historical 15-query local run only; not current frozen-release evidence |
| Conversation memory | `/sessions`, `/recommendations`, `session_id` in `/query` | `SessionService` | MySQL | User and organization ownership | Missing/archived/cross-user sessions are rejected; only verified citations enter memory context | Session and conversation tests passed | Real multi-turn LLM acceptance remains pending |
| Document libraries | `/document-libraries`, `/documents/*` | document ingestion/result/structure/relation services and Celery task | MySQL, Redis, Celery, filesystem, parser/OCR, Chroma | Knowledge-base read/manage and document-to-library ownership | State machine records failure; retry endpoint available; temporary cleanup limits need security hardening | Document-focused tests passed | Historical PDF/DOCX/OCR local chain verified on earlier uncommitted tree |
| Case library | `/cases`, `/case-sources`, similar-case lookup | case source/ingestion services, annual case index and retrievers | Local case corpus, OCR output, Chroma, MySQL | Current read routes are effectively public; final boundary pending | Empty/unavailable retriever yields empty or degraded results | Case tests passed | Historical 10-book, 3,661-page, 623-case local dataset record; current rebuild not rerun |
| Legal scenarios | `/scenarios/*`, report PDF | `ScenarioService`, `scenario_runtime`, Celery task | MySQL, Redis/Celery, evidence workflow, optional LLM | Authenticated user and organization ownership | Jobs retain structured failure; retries supported; advice remains evidence-gated | Scenario tests passed | Historical contract/compliance/rights-path local smoke on earlier uncommitted tree |
| Law-update workflow | `/law-updates/*` | `LawUpdateService`, external source adapter, rebuild task | MySQL, external source, Chroma/index rebuild | `law_updates:manage`, organization scope | Observation does not switch READY data until explicit confirmation and successful rebuild | Law-update and confirmed-rebuild tests passed | Local snapshot/confirmation capability only; no authorized automatic source accepted |
| Knowledge graph | `/graph`, `/graph/query` | `LawGraph`, graph builder/retriever | `data/law_graph.json`, statute metadata | Current route boundary needs Stage 2 decision | Missing relations return empty/degraded structures | Graph rebuild and retrieval tests passed | Historical local visualization/data record; organization-private graph isolation not accepted |
| Prompt and agent configuration | `/prompts/*`, `/admin/agent-config` | `PromptService`, `AgentConfigService` | MySQL | `prompts:manage` / `agents:manage`, organization-scoped mutable fields | Unauthorized or disallowed fields rejected | Prompt/admin/agent-config tests passed | No production operator acceptance |
| Favorites | `/favorites/*` | `FavoriteService` | MySQL | Authenticated user and organization scope | Cross-user access is rejected | Favorite API/service tests passed | No separate real-chain record required beyond API acceptance |
| Audit, usage, dashboard, metrics | `/admin/audit-logs`, `/admin/usage`, `/dashboard/stats`, Prometheus mount | audit/usage services and metrics | MySQL, Prometheus | Admin permissions for audit/analytics | Database audit stores hashes/lengths, but raw-query application logs remain a known gap | Audit idempotency and admin tests passed | Grafana/Prometheus deployment not accepted end to end |
| MCP read interface | `python -m app.mcp_server` | `app/mcp_server.py` | MySQL, local indexes, optional HTTP bearer | Service-account organization context; HTTP bearer required outside stdio | Missing permission or bearer rejects access; external concept search is non-authoritative | Covered indirectly by service tests; no dedicated end-to-end MCP suite | Not real-chain verified for release |
| Offline evaluation | evaluation scripts and `scripts/quality_gate.py` | `src/evaluation/*`, runners, report writers | Frozen datasets, local collections, optional live API | Local operator task | Missing candidates/unreviewed labels fail loaders; current 100-row historical builder remains a known governance defect | Evaluation and quality-gate tests passed | 100-row reports are provisional; formal Stage 8 evaluation pending |

## Deliberately incomplete items

- security and privacy closure for logs, SSRF, legacy verification, uploads, and public/private route boundaries;
- reproducible Docker cold start and data bootstrap;
- authoritative legal-source manifests and effective-version selection;
- automatic multi-knowledge-base routing and cross-library evidence orchestration;
- consumer-facing streaming event delivery and final frontend end-to-end acceptance;
- frozen 300-row retrieval evaluation and 100-answer human legal review.
