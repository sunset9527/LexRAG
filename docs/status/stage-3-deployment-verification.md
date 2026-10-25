# Stage 3 deployment status and verification boundary

**Status date:** 2026-10-24

**Scope:** the Stage 3 working tree, including the final cold-start fixes for
MySQL TCP readiness, runtime model registration, persistent graph bootstrap,
runtime-volume permissions, worker/beat health probes, frontend IPv4 health,
and verifier portability.
**Closure state:** core isolated deployment acceptance is recorded below. This
does not claim a production release, legal-answer quality, a complete hashed
dependency lock, browser end-to-end coverage, real LLM smoke coverage, or a
recovery/fault-injection drill.

## Capability ledger

| Capability | Versioned implementation | Automated/static evidence | Real-chain evidence | Status |
| --- | --- | --- | --- | --- |
| Schema initialization | Alembic root-to-head chain; application startup only makes the engine/session | \`test_alembic_contract.py\`, MySQL integration contract | Isolated Compose MySQL completed \`migrate\` with exit 0 | Accepted in isolated runtime |
| Failed-migration handling | Backup/current/history/forward-retry guide | \`docs/migration-recovery.md\`, migration contracts | No incident drill | Documented; drill pending |
| Embedding and index identity | Explicit \`local\`/\`zhipu\` provider, dimension check, identity-scoped cache and Chroma metadata | \`test_embedding_contract.py\`, knowledge-base contracts | BGE-M3 mounted read-only; fresh Chroma/statute bootstrap completed | Accepted in isolated runtime |
| Statute catalog/bootstrap | Eight local snapshot identities, per-law validation, idempotent/recoverable bootstrap command | \`test_statute_catalog.py\`, \`test_deployment_bootstrap.py\` | \`bootstrap\` exited 0 on fresh dedicated volumes and rebuilt the graph artifact | Accepted in isolated runtime |
| API health | \`/health/live\` and dependency-aware \`/health/ready\` | \`test_readiness.py\` | Container readiness returned 200 with database, migration, Redis, embedding, graph and statutes ready | Accepted in isolated runtime |
| Compose topology | One \`compose.yaml\`, private services, named volumes, read-only model mount and one-shot gating | \`test_compose_contract.py\` | Isolated image build and cold start completed; API, worker, beat, web, MySQL and Redis healthy | Accepted in isolated runtime |
| Queue/proxy runtime contract | Broker-backed worker ping, Beat paths, Nginx \`/api/\` proxy and bounded upload/timeout settings | \`test_worker_nginx_contract.py\` | Worker and Beat healthy; host request to Nginx on port 18080 returned 200 | Accepted in isolated runtime |
| Safe acceptance evidence | \`scripts/verify_deployment.py\` dry-run/execute plan with redaction and no implicit cleanup | \`test_verify_deployment.py\` | Execute mode completed all configured checks; see \`reports/deployment/deployment-verification.md\` | Accepted in isolated runtime |

## Exact commands

The command set and its safety boundaries are maintained in
[deployment.md](../deployment.md). The focused static check is:

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

The default deployment-verifier command is a dry run and does not call Docker:

\`\`\`powershell
.\.venv\Scripts\python.exe scripts\verify_deployment.py \`
  --project-name lexrag-stage3-acceptance \`
  --env-file .env.docker \`
  --report-directory reports\deployment\lexrag-stage3-acceptance
\`\`\`

## Explicit exclusions

The dependency-lock acceptance work is intentionally excluded from Stage 3
closure work by user decision. The incomplete direct-package file
\`constraints-py313.txt\` is not represented as a full transitive lock and must
not be used to claim reproducible Linux dependency installation.

No source legal text, evaluation labels, retrieval metrics, MySQL database,
Chroma collection or Docker volume was modified by this documentation record.
The external \`RAG法律.md\` roadmap is synchronized only as a status summary.
The legal snapshots are local clean-text inputs, not a claim that they are
authoritative or current official legal sources.

## Recorded isolated acceptance

On 2026-10-24, project \`lexrag-stage3-acceptance\` built and started from
fresh dedicated Compose volumes. The redacted local report at
\`reports/deployment/deployment-verification.md\` records PASS for Compose
configuration, image build, service start, migration completion, statute
bootstrap and API readiness. The final service inspection found API, MySQL,
Redis, Worker, Beat and Web healthy; a host request to Nginx port 18080 returned
HTTP 200.

This is a core isolated-runtime acceptance, not a production or legal-quality
claim. The intentionally abandoned full hashed dependency lock, browser manual
end-to-end testing, a real LLM answer smoke test, restart recovery and controlled
fault injection remain outside this evidence set.
