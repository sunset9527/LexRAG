# Stage 3 deployment status and verification boundary

**Status date:** 2026-10-23  
**Scope:** versioned Stage 3 code through \`74fbe11\` and its preceding Stage 3 commits.  
**Closure state:** implementation and static contracts are present; real isolated
deployment acceptance is not recorded, so Stage 3 is not marked complete.

## Capability ledger

| Capability | Versioned implementation | Automated/static evidence | Real-chain evidence | Status |
| --- | --- | --- | --- | --- |
| Schema initialization | Alembic root-to-head chain; application startup only makes the engine/session | \`test_alembic_contract.py\`, MySQL integration contract | No current real Docker MySQL run | Implemented; real-chain pending |
| Failed-migration handling | Backup/current/history/forward-retry guide | \`docs/migration-recovery.md\`, migration contracts | No incident drill | Documented; drill pending |
| Embedding and index identity | Explicit \`local\`/\`zhipu\` provider, dimension check, identity-scoped cache and Chroma metadata | \`test_embedding_contract.py\`, knowledge-base contracts | No current BGE-M3/Zhipu/Chroma run | Implemented; real-chain pending |
| Statute catalog/bootstrap | Eight local snapshot identities, per-law validation, idempotent/recoverable bootstrap command | \`test_statute_catalog.py\`, \`test_deployment_bootstrap.py\` | No Compose bootstrap run | Implemented; real-chain pending |
| API health | \`/health/live\` and dependency-aware \`/health/ready\` | \`test_readiness.py\` | No running Compose API measurement | Implemented; real-chain pending |
| Compose topology | One \`compose.yaml\`, private services, named volumes, read-only model mount and one-shot gating | \`test_compose_contract.py\` | No image build/cold-start evidence | Implemented; real-chain pending |
| Queue/proxy runtime contract | Broker-backed worker ping, Beat paths, Nginx \`/api/\` proxy and bounded upload/timeout settings | \`test_worker_nginx_contract.py\` | No Worker/Beat/Nginx container acceptance | Implemented; real-chain pending |
| Safe acceptance evidence | \`scripts/verify_deployment.py\` dry-run/execute plan with redaction and no implicit cleanup | \`test_verify_deployment.py\` | Script has not been used for a successful real execution | Implemented; real-chain pending |

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
Chroma collection, Docker volume, or external \`RAG法律.md\` status was modified
by this documentation record. The legal snapshots are local clean-text inputs,
not a claim that they are authoritative or current official legal sources.

## Remaining acceptance evidence

Before the stage could truthfully be closed, an operator would need to retain
redacted evidence from a new isolated Compose project showing: successful image
build, migration exit 0, bootstrap exit 0, readiness 200, worker/proxy behaviour,
and separately approved restart/recovery checks. A real MySQL integration and
real BGE-M3/Chroma runtime must also be recorded. These are acceptance actions,
not completed facts.

