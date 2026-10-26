# Stage 7 dependency-governance closure design

## Decision

Use the approved bounded approach: remediate only non-major frontend dependency updates, repeat Python audit in an isolated project environment, produce the missing frontend license inventory, and document unresolved major upgrades and PyMuPDF licensing as explicit release boundaries.

## Scope

1. Keep Node 22 as the repository/CI baseline declared by `.nvmrc`. The owner chose not to replace an existing local Node 24 toolchain, so the local runtime is upgraded in place to Node 24.22.1 (which satisfies the audited packages' `>=24.15.0` engine requirement); this local evidence does not replace Node 22 CI verification.
2. Apply `npm audit fix` without `--force`, then run frontend unit tests, production build, real Chromium E2E, and a post-fix audit. The existing dry run proposes 22 non-major updates.
3. Generate a frontend license inventory with `npx.cmd`, avoiding the PowerShell-blocked `npx.ps1` shim.
4. Create a disposable isolated Python 3.13 environment, install the repository's requirements through its declared constraints, and run `pip-audit` and `pip-licenses` there. Report this separately from the already collected shared-interpreter audit.
5. Keep major frontend upgrade candidates open: Vitest/Tinypool, ECharts, Tailwind, and vue-echarts require dedicated compatibility work and are not included in the non-breaking remediation.
6. Keep PyMuPDF unchanged. Its AGPL-3.0 / Artifex-commercial dual license is an explicit public-release and commercial-deployment blocker until the owner selects AGPL compliance, commercial licensing, or a replacement parser.

## Evidence and acceptance

The closure evidence must include the local Node 24.22.1 version output, the unchanged Node 22 baseline declaration, pre/post npm audit reports, frontend license JSON, isolated Python audit/license JSON, frontend unit/build/E2E results, and an updated governance document. A zero-vulnerability claim is out of scope: accepted open findings must be recorded with severity, scope, and next action.

## Safety boundaries

No `npm audit fix --force`, no major dependency upgrade, no deletion of an existing normal runtime environment, and no claim of Python-release audit coverage from the shared `E:\python` interpreter. The isolated audit environment is disposable and does not replace the project's normal runtime environment.
