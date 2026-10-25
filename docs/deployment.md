# Stage 3 deployment guide

This guide describes the versioned Stage 3 runtime contract. It distinguishes
versioned implementation from evidence recorded for a particular environment.
An isolated cold-start acceptance was completed on 2026-10-24; its exact scope
and exclusions are recorded in
[the Stage 3 verification ledger](status/stage-3-deployment-verification.md).

## Runtime topology

\`compose.yaml\` is the single Compose entry point. Its normal profile creates an
isolated private network with these services:

| Service | Role | Start gate / exposure |
| --- | --- | --- |
| \`mysql\` | Application metadata | Private; persistent named volume |
| \`redis\` | Celery broker/result backing service | Private; persistent named volume |
| \`migrate\` | \`alembic upgrade head\` | One-shot; waits for healthy MySQL |
| \`bootstrap\` | Validates/builds the eight local statute indexes | One-shot; waits for successful migration and healthy Redis |
| \`api\` | FastAPI | Private; waits for successful migration/bootstrap and Redis |
| \`worker\`, \`beat\` | Asynchronous task execution/scheduling | Private; use the same gates as API |
| \`web\` | Vue static files and Nginx reverse proxy | The only default published port |
| \`mcp\` | Stdio MCP server | Disabled unless \`--profile mcp\` is specified; no port |

MySQL, Redis, and API do not publish host ports in this topology. The API is
reached through Nginx as \`/api/*\`; the trailing slash in the proxy deliberately
maps browser \`/api/query\` to backend \`/query\`.

The runtime application account is \`MYSQL_APP_USER\`; API, migration and worker
services never use the MySQL root account. Runtime data are separated into
named volumes for MySQL, Redis, Chroma, uploads, graph artifacts, and statute
update snapshots. The embedding model is a required, read-only host mount at
\`/models/bge-m3\`; Compose does not download a model and does not silently fall
back to a remote embedding provider.

## Prepare an isolated environment

Use \`.env.example\` for a local, non-container development process. Use
\`.env.docker.example\` only as the template for Compose:

\`\`\`powershell
Copy-Item .env.docker.example .env.docker
\`\`\`

Fill the blank values in \`.env.docker\` locally. At minimum, set distinct
\`MYSQL_ROOT_PASSWORD\`, \`MYSQL_APP_PASSWORD\`, and \`JWT_SECRET_KEY\` values, plus
an existing host directory for \`LEXRAG_LOCAL_EMBEDDING_MODEL_PATH\`. Keep
\`.env.docker\` untracked. Do not place a key in a command line or commit an
environment file.

Before starting anything, render the topology with a new project name. The
reserved name \`lexrag\` is intentionally rejected by the verification script so
that a developer's existing volumes are not selected accidentally.

\`\`\`powershell
docker compose --env-file .env.docker --project-name lexrag-stage3-acceptance config
\`\`\`

Choose a project name that has never been used for a developer environment.
Compose names all volumes and containers from that name. Do not run an
acceptance command against an existing project or a database/Chroma directory
that contains work you need to keep.

## Startup and health contract

The normal startup command is:

\`\`\`powershell
docker compose --env-file .env.docker --project-name lexrag-stage3-acceptance up --build
\`\`\`

\`migrate\` must exit with code 0 before \`bootstrap\` can run. \`bootstrap\` calls
\`python scripts/bootstrap_runtime.py all --json\`; it validates each local
snapshot and builds/recovers each statute independently. A missing or changed
snapshot is reported as \`UNAVAILABLE\` rather than being represented as a READY
index. Collections are keyed by source hash, embedding fingerprint and index
schema version, so a new source/model identity does not overwrite the legacy
unscoped collection.

There are two different health endpoints:

| Public path through Nginx | Meaning | Expected result |
| --- | --- | --- |
| \`/api/health/live\` | FastAPI process liveness only | \`200\` with \`{"status":"alive"}\` |
| \`/api/health/ready\` | Bounded, read-only checks for database, Alembic head, Redis, embedding, persisted graph artifact and statute indexes | \`200\` only when all components are ready; otherwise a redacted \`503\` component map |

The API image's Docker healthcheck intentionally uses the lightweight liveness
endpoint. Compose uses readiness before publishing the web service. A missing
graph file, an unavailable local model, a migration mismatch, or an unhealthy
statute index makes readiness fail closed; the endpoint does not expose paths,
credentials, driver errors, or raw exception text.

\`worker\` has a broker-backed control-ping healthcheck for the exact configured
worker name. \`beat\` uses an explicit temporary pidfile/schedule path. In
Windows local development outside containers, run the worker with \`--pool=solo\`
as shown in the README; the Linux Compose worker deliberately uses normal
process concurrency instead.

## Verification commands and evidence

Static contracts cover the topology, readiness behaviour, migration chain,
bootstrap isolation, embedding/index identity, worker/Nginx behaviour and the
safe verifier. They do not contact Docker, MySQL, Chroma, Redis, a local BGE
model, or an external LLM unless a separately opt-in test is selected.

\`\`\`powershell
.\.venv\Scripts\python.exe -m pytest \`
  tests\test_alembic_contract.py \`
  tests\test_alembic_mysql_integration_contract.py \`
  tests\test_embedding_contract.py \`
  tests\test_statute_catalog.py \`
  tests\test_deployment_bootstrap.py \`
  tests\test_readiness.py \`
  tests\test_compose_contract.py \`
  tests\test_worker_nginx_contract.py \`
  tests\test_verify_deployment.py -q
\`\`\`

\`scripts/verify_deployment.py\` records redacted JSON and Markdown evidence. Its
default is a dry run: it only writes a plan and does not invoke Docker.

\`\`\`powershell
.\.venv\Scripts\python.exe scripts\verify_deployment.py \`
  --project-name lexrag-stage3-acceptance \`
  --env-file .env.docker \`
  --report-directory reports\deployment\lexrag-stage3-acceptance
\`\`\`

With \`--execute\`, it runs \`compose config\`, \`build\`, \`up --detach\`, checks that
the \`migrate\` and \`bootstrap\` jobs exited 0, and calls the private API readiness
endpoint. It stops at the first failed check. It never runs \`docker compose down\`,
deletes a volume, repeats bootstrap writes, restarts services, or injects a
fault; those actions require a separate, explicitly scoped operator decision.

\`\`\`powershell
.\.venv\Scripts\python.exe scripts\verify_deployment.py \`
  --project-name lexrag-stage3-acceptance \`
  --env-file .env.docker \`
  --report-directory reports\deployment\lexrag-stage3-acceptance \`
  --execute
\`\`\`

For migration-specific recovery, see [migration-recovery.md](migration-recovery.md).
It requires a backup and forward repair; it deliberately does not prescribe an
automatic downgrade, schema recreation, or data deletion.

## Current verification boundary

The following are implemented as versioned code and static contracts: Alembic
as the sole schema initializer, index identity isolation, eight-statute
bootstrap, liveness/readiness separation, Compose start gates, worker/Nginx
contracts, and a non-destructive acceptance runner. The detailed ledger is
[stage-3-deployment-verification.md](status/stage-3-deployment-verification.md).

The following remain **outside** the recorded isolated acceptance:

- A completed full, hash-pinned transitive Python dependency lock or a clean
  Linux installation of that lock; this Task 1 acceptance work was explicitly
  abandoned after registry/network failures.
- A browser end-to-end run, restart recovery, or fault-injection exercise.
- A real LLM-answer smoke test or a legal-effectiveness/production acceptance.

The 2026-10-24 run did complete image build, fresh-volume migration, local
BGE-M3/Chroma statute bootstrap and dependency-aware API readiness in the
isolated project \`lexrag-stage3-acceptance\`. Those facts are still narrower
than the exclusions above; they do not establish production readiness or legal
answer quality.
