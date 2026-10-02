# LexRAG V3.0 Modern SaaS Frontend Implementation Plan

## Goal

Implement the approved modern enterprise SaaS visual system across the existing Vue frontend without changing its legal-RAG behaviour, routes, API contracts, or real data sources.

## Scope Boundary

- User-approved design: `docs/superpowers/specs/2026-10-02-v30-modern-saas-frontend-design.md`.
- Existing V2.1/V2.2 root planning files are preserved unchanged; this plan is scoped to the V3.0 visual refresh.
- Backend edits are out of scope except restarting the existing local API after frontend validation if necessary.

## Phases

### 1. Baseline and component inventory — complete

- [x] Confirm the visual direction and capture three comparison mockups.
- [x] Identify systemic causes of the current look: structural emoji, dark gradient shell, page-local colours, inconsistent panels.
- [x] Record API/data invariants and current demonstrated consultation, source, law, dashboard and graph workflows.
- [x] Record baseline frontend build/test result immediately before visual code changes.

### 2. Establish the visual foundation — complete

- [x] Replace global colours, typography, surfaces, controls and motion with semantic tokens.
- [x] Re-skin Element Plus defaults without changing component APIs.
- [x] Rebuild `AppLayout` around the light navigation rail and responsive shell.
- [x] Add focused tests/source checks for no structural emoji and stable navigation behaviour.

### 3. Rebuild high-traffic workspaces — in progress

- [x] Redesign Dashboard using real dashboard statistics and task-oriented actions.
- [x] Redesign Chat as a dense three-pane legal workbench while preserving citation/source switching.
- [x] Verify source-level visual contracts, reduced-motion rule, narrow-layout rules and keyboard-visible focus styling; browser interaction inspection remains part of final handoff.

### 4. Apply shared patterns to research and management — pending

- [ ] Standardise Laws, Search and Graph heading/filter/content/inspector patterns.
- [ ] Standardise knowledge-base, documents, cases, favorites, scenarios, settings, admin and authentication views.
- [ ] Remove remaining structural emoji and page-local visual anti-patterns.

### 5. Verification and handoff — pending

- [ ] Run focused frontend tests, `npm run build`, and relevant existing API regression tests.
- [ ] Inspect key flows in the local running app at desktop and narrow viewport widths.
- [ ] Verify no business/API regressions and report only reproducible results.

## Implementation Decisions

| Decision | Rationale |
| --- | --- |
| Apply tokens in the global stylesheet before page work | Prevents one-off colours and makes all pages visually coherent. |
| Retain Element Plus and existing route/component boundaries | Minimises risk to working local demonstrations. |
| Work shared shell → core workspaces → remaining views | Gives the biggest visible change early while maintaining a stable design system. |
| Treat citation and source states as functional, not decorative | Legal provenance is LexRAG's core product capability. |
| Keep evidence and dashboard values API-derived | Maintains data integrity. |

## Known Environment Notes

| Issue | Resolution |
| --- | --- |
| Repository is owned by the Windows user while tool shell uses a sandbox identity | Use per-command `-c safe.directory=E:/python/LLM/Legal_RAG_Agent`; do not mutate global Git configuration. |
| UI design-helper script referenced by the UI skill is absent in this installation | Apply the skill's documented accessibility, token, typography and interaction rules directly; do not retry the missing script. |

## Verification Matrix

| Area | Required check |
| --- | --- |
| Shell | Current route, navigation, logout and responsive rail remain functional. |
| Chat | Send path, error/retry, multiple citation selection and original-law text remain usable. |
| Laws/Graph | Law switching, law filter and selected-node/source panels retain real API data. |
| Dashboard | Case count continues to come from `/dashboard/stats`. |
| Management | Lists retain loading, empty, error, table and form states. |
| Quality | Build passes; relevant tests pass; visible no-emoji/source and focus-state checks pass. |
