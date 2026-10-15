# LexRAG Stage 0 Baseline and Truth Alignment Design

**Date:** 2026-10-15

**Scope:** Stage 0 only — freeze the current state, organize existing work, and align factual claims

**Repository:** `E:\python\LLM\Legal_RAG_Agent`

## 1. Objective

Turn the current large, mixed working tree into an explainable and reviewable local Git history without losing existing work. Establish one factual baseline for the repository before starting the LangGraph migration or any later closure stage.

This stage does not add product features, migrate `/query` to LangGraph, run paid LLM evaluations, or claim production readiness.

## 2. Current Baseline

At design time, the repository is on local `main` at `2405e83`, one commit ahead of `origin/main`. The working tree contains 156 modified tracked files and 16 untracked files. The changes span database migrations, platform services, legal data processing, retrieval and evidence workflows, evaluation assets, tests, and temporary execution notes.

The current README also describes the main query path as LangGraph even though `/query` is implemented by `LegalEvidenceWorkflow`, a deterministic Python workflow. Correcting that mismatch is part of this stage.

## 3. Safety Boundaries

- Preserve all current project work unless it is confirmed to be a secret, local database, runtime log, raw user consultation, or disposable generated artifact.
- Do not use `git reset`, `git checkout --`, `git clean`, force push, or history rewriting.
- Do not push any commit to a remote.
- Review every staged diff before committing it.
- Split files by hunk when a file contains changes from more than one concern.
- Do not perform a repository-wide line-ending normalization in this stage.
- Keep evaluation data honest. Do not edit samples to manufacture better metrics.
- Treat curated evaluation questions as test data, not as user consultation logs; document their provenance before publishing them.

## 4. Change Classification

Every existing change will be assigned to one of these classes:

1. **Platform foundation:** migrations, models, authentication, organization/RBAC, sessions, favorites, prompts, audit, usage, and API wiring.
2. **Legal data lifecycle:** statute versions and updates, document and case processing, ingestion, indexing, and graph rebuilds.
3. **Evidence workflow:** retrieval, evidence ledger, citation verification, controlled repair, legal scenarios, query API, and legacy agent-path clarification.
4. **Evaluation:** eight-law datasets, builders, runners, aggregation reports, and evaluation-specific tests.
5. **Engineering quality:** Ruff configuration, quality-gate tooling, and changes that are purely formatting.
6. **Documentation and working notes:** README claims, status documents, feature ledger, and temporary planning notes.
7. **Local-only or unsafe artifacts:** credentials, logs, local databases, raw user content, and other non-publishable runtime data.

Files that mix classes will be staged by hunk. Pure formatting changes will not hide semantic changes.

## 5. Planned Commit Structure

The expected local commit sequence is:

1. `feat(platform): consolidate organization-scoped platform foundation`
2. `feat(legal-data): consolidate versioned legal data workflows`
3. `feat(evidence-workflow): consolidate evidence-driven legal workflows`
4. `eval(eight-law): add reproducible multi-law evaluation assets`
5. `chore(quality): align quality-gate and formatting configuration`
6. `docs(stage-0): establish the v3.0 closure baseline`

Tests should remain with the behavior they verify. The exact number of commits may change when dependency review shows that two adjacent groups cannot be separated safely. Any merge of groups must be explained in the baseline report.

## 6. Documentation Deliverables

### 6.1 Baseline report

Create `docs/status/v3.0-closure-baseline.md` containing:

- branch, HEAD, remote relationship, and inventory date;
- categorized tracked and untracked changes;
- public, local-only, and excluded artifacts;
- current runtime and data dependencies;
- known risks and unresolved validation gaps;
- the final local commit sequence;
- validation commands, dates, results, and report paths.

### 6.2 Feature ledger

Create `docs/status/feature-ledger.md`. Each material capability must record:

- product entry point;
- backend route or command;
- core service/module;
- database, index, model, or queue dependency;
- authentication and authorization requirement;
- failure and degradation behavior;
- automated test evidence;
- real-chain acceptance evidence;
- current state: `implemented`, `automation passed`, or `real-chain verified`.

The three state labels are cumulative but not interchangeable. Code presence alone must never be presented as successful automated or real-chain verification.

### 6.3 README truth alignment

Update README so that:

- `/query` is described as a deterministic evidence-driven Python workflow;
- the existing `create_react_agent` path is marked legacy and not presented as the current main chain;
- LangGraph `StateGraph` migration is described as planned Stage 1 work;
- automatic statute updating is described as local snapshot monitoring, administrator confirmation, rebuild, and collection switching until an authorized source is integrated;
- enterprise and production wording is qualified as a target until deployment, security, recovery, and end-to-end acceptance are complete;
- each published metric includes its dataset, run date, code commit, and report path;
- stale test totals or coverage figures are labeled historical or replaced only after a reproducible current run.

### 6.4 External roadmap

After repository validation, update `E:\个人发展\002职业\项目1：RAG法律\RAG法律.md` only where the current-state table or Stage 0 progress would otherwise contradict the verified repository baseline. The roadmap remains a planning document and is not part of the repository commits.

## 7. Validation Strategy

### 7.1 Before each commit

- inspect the staged file list and staged diff;
- run a credential and privacy scan without printing secret values;
- run `git diff --cached --check`;
- confirm the commit contains one explainable concern;
- confirm no unrelated existing work is omitted or overwritten.

### 7.2 Focused validation

Run the relevant existing tests for each behavioral group after its dependencies are present. A clean temporary worktree may be used to validate committed states without disturbing the remaining working tree.

### 7.3 Final Stage 0 validation

Run, where the existing environment supports them:

- Ruff checks;
- the complete backend test suite;
- frontend contract tests;
- frontend production build.

These checks are regression evidence, not the formal legal-effect evaluation reserved for Stage 8. No paid LLM, 300-item retrieval evaluation, Docker cold-start acceptance, or production security claim is part of Stage 0.

Pre-existing failures will be recorded accurately rather than hidden or expanded into unrelated fixes. Failures introduced by Stage 0 edits must be fixed before completion.

## 8. Temporary Notes and Reports

- Preserve useful content from `task_plan.md`, `progress.md`, and `findings.md` by merging it into the baseline report or moving it to an explicit archive.
- Do not publish temporary working-memory files at the repository root merely to make the tree clean.
- Publish only evaluation reports that are reproducible, contain no credentials or raw user content, and clearly identify their dataset and code context.
- Keep runtime quality output ignored when it is machine-specific; record stable commands and summarized results in the baseline report.

## 9. Error Handling

- If a staged group cannot pass its focused tests because it depends on a later group, merge the dependent groups and document why.
- If a suspected secret or private record is found, leave the file unstaged and record only the file path and remediation status, never the value.
- If an existing file cannot be classified confidently, leave it untouched and list it as unresolved rather than guessing.
- If validation requires paid services, unavailable infrastructure, or destructive state changes, record the limitation and defer the check.
- If the final worktree cannot be made clean without discarding information, retain the files and document each exception.

## 10. Completion Criteria

Stage 0 is complete only when:

- all existing project work is committed in meaningful local commits or explicitly documented as local-only;
- the worktree is clean or every remaining file is individually explained;
- no identified credentials, raw consultations, runtime logs, or local databases are committed;
- README no longer claims that the current `/query` path is a LangGraph `StateGraph`;
- published metrics have reproducible provenance or are labeled historical;
- the feature ledger covers the major API, service, permission, data, degradation, test, and acceptance paths;
- validation results are recorded with dates and commit identifiers;
- no remote push, history rewrite, Stage 1 implementation, or inflated quality claim has occurred.
