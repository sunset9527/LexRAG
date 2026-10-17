# LexRAG v3.0 Stage 0 execution log

## Objective and constraints

Stage 0 preserved and organized the existing mixed working tree, aligned public claims with code reality, and established a reproducible baseline before the Stage 1 LangGraph migration.

Constraints followed:

- no reset, clean, force push, history rewrite, or remote push;
- no Stage 1+ implementation and no paid LLM or formal Stage 8 evaluation;
- no modification of evaluation samples to improve metrics;
- secrets, local databases, runtime logs, raw consultations, caches, and generated build output remained local-only.

## Starting inventory

- Branch: `main`; starting HEAD: `2405e83`.
- The local branch was already one commit ahead of `origin/main`.
- Working tree: 156 modified tracked files and 16 untracked files.
- Largest areas: tests (52), `app` (49), `src` (42), Alembic (11), and script/root entries (10).
- README overstated the active `/query` path as LangGraph; inspection showed that it uses the deterministic Python `LegalEvidenceWorkflow`.

## Decisions and findings

- Work was grouped in place into append-only commits by dependency and concern.
- A value-pattern scan found no OpenAI-style key, GitHub token, AWS key, bearer token, or private key. The ID-shaped test value is synthetic and verifies that audit metadata does not retain supplied consultation text.
- The 85-row eight-law additions file remains `pending` without review dates. The historical builder promoted all rows when given one shared date, so the resulting 100-row snapshot and reports are provisional only.
- The active query workflow is not a LangGraph `StateGraph`; `src/agent/` is a legacy path.

## Local commit sequence

| Commit | Purpose |
|---|---|
| `a29e87a` | Define the Stage 0 design |
| `beecbf8` | Correct design-document formatting |
| `9702c38` | Consolidate organization-scoped platform foundation |
| `43c8c1a` | Consolidate versioned legal-data workflows |
| `c2615d8` | Consolidate the evidence-driven query path |
| `907afc2` | Preserve the provisional eight-law evaluation snapshot |
| `1295e2c` | Enforce maintained-code quality checks |

## Verification evidence

- Pre-split full backend run: 235 passed on 2026-10-15.
- Focused suites: platform 50 passed; legal data 63 passed; evidence workflow 93 passed; evaluation 13 passed; quality-gate tests 4 passed.
- Final 2026-10-17 checks on the grouped code content:
  - Ruff passed over maintained Python code.
  - Full backend suite: 235 passed, 67% total coverage (6,507 statements, 2,159 misses), with 51 recorded warnings.
  - Frontend Node contract suite: 3 passed.
  - Frontend production build: passed, with third-party annotation and large-chunk warnings.

## Problems encountered and resolutions

| Problem | Resolution |
|---|---|
| Initial design commit contained Markdown trailing whitespace | Added an append-only formatting commit instead of rewriting history. |
| A patch attempted to delete and recreate planning files together | Archived content first and handled file replacement in separate patches. |
| Pytest could not write its cache/default temp path in the sandbox | Used `-p no:cacheprovider` and a verified repository-local `--basetemp`. |
| Disabling `core.autocrlf` while staging exposed whole-file whitespace noise | Unstaged only the index and restaged with repository Git settings; worktree content was preserved. |
| Combined final quality-gate process was interrupted | Re-ran Ruff, backend coverage, frontend tests, and frontend build separately; did not cite the stale 2026-10-03 report. |
| System Python lacked Ruff | Used the project virtual environment, which contains the maintained tooling. |

The durable outcome is recorded in `docs/status/v3.0-closure-baseline.md` and `docs/status/feature-ledger.md`.
