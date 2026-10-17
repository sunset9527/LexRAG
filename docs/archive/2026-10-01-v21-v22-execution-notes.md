# LexRAG v2.1/v2.2 Execution Notes

Archived on 2026-10-15 before reusing the repository-root planning files for the v3.0 Stage 0 baseline task.

## Original task plan

### Goal

Complete the remaining v2.1 formal evaluation and v2.2 engineering work with reproducible tests and real local smoke checks.

### Phases

- [x] Inventory current scenario architecture, services, migrations, and evaluation assets.
- [x] Add case evidence and controlled LLM advice to scenario workflows.
- [x] Extend compliance mapping and rights-path graph contracts.
- [x] Produce structured report/PDF and replace background tasks with Celery dispatch.
- [x] Add Alembic migration and evaluation runners.
- [x] Run full automated regression, frontend build, and real local smoke checks.

### Constraints

- Evidence may only be shown when it is in the current request ledger and passes citation verification.
- Do not write API keys to files or output them.
- Preserve unrelated uncommitted v2.1 work.

### Errors

| Error | Resolution |
|---|---|
| API port 8000 occupied by WSL relay | Run current LexRAG API on 8001; frontend proxy targets 8001. |
| Alembic has no active metadata/version setup | Fixed: metadata imports and idempotent scenario-job revision are present; apply it during final validation. |
| Current Python environment lacks Celery despite requirements declaration | Installed Celery into the actual Python 3.13 environment and confirmed the refreshed Worker registers `lexrag.process_scenario`. |
| Ports 8000/8001 are occupied by WSL/Docker forwarding | Run LexRAG API on verified-local port 8002; Vite proxy now targets 8002. |
| Worker initially left jobs PENDING | Fixed model registration in `init_db()` so the `scenario_jobs.user_id -> users.id` foreign key resolves in an isolated Celery process. |

## Original progress log

### 2026-10-01

- Created persistent completion plan.
- Inventoried service boundaries and migration configuration.
- Added tested scenario-service contracts for controlled LLM advice and separate case evidence. Advice is evidence-gated; cases cannot become statute citations.
- Added and wired free-text annual-case retrieval for scenario evidence.
- Configured Alembic metadata and an idempotent scenario-jobs baseline revision.
- Completed compliance mapping and rights-path graph contracts with explicit knowledge-base targets.
- Replaced in-process scenario execution with `lexrag.process_scenario` Celery jobs. User API keys are not sent through the broker or stored.
- Added structured report sections before PDF rendering and a v2.1 live-workflow evaluation runner with an explicit human-review gate.
- Verified Alembic at `20261001_01`, Redis/Celery worker registration, API health on `127.0.0.1:8002`, and the Vite proxy.
- Completed real v2.2 smoke checks for contract review, labor compliance, labor rights paths, and PDF output.
- Recorded a real v2.1 cold-cache evaluation: 15/15 verification pass, 15/15 expected citation coverage, 0 cache hits, and mean end-to-end latency of 18,978.205 ms. Human assertion-support review remained unset.
- Recorded 156 passing pytest tests and a successful Vue production build with pre-existing warnings.

## Original findings

- MySQL and Redis were running locally; LexRAG API was healthy on `127.0.0.1:8001` during the initial check.
- v2.1 completed one real DeepSeek smoke query with verified citations.
- v2.2 had contract, compliance, document, and rights MVPs; contract and compliance supported verified statute evidence.
- The annual case retriever and evidence ledger could be reused for case evidence.
