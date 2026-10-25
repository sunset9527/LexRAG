# Stage 3 deployment verification

- Project: `lexrag-stage3-acceptance`
- Mode: `EXECUTE`
- Generated: `2026-10-24T05:50:07.558621+00:00`

| Check | Status | Purpose |
| --- | --- | --- |
| compose_config | PASS | validate rendered Compose topology |
| compose_build | PASS | build the isolated runtime images |
| compose_up | PASS | start the declared services |
| migration_completed | PASS | capture the one-shot migration service state |
| bootstrap_completed | PASS | capture the one-shot bootstrap service state |
| api_readiness | PASS | capture the API readiness response from the private network |

## Recovery exercises

All recovery and fault exercises are intentionally not executed by this runner.
