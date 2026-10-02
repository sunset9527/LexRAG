# V3.0 Modern SaaS Frontend Findings

## Requirements

- Rework the entire frontend so it feels like a credible, modern B2B legal product rather than generic AI UI.
- Direction B is approved after three visual comparisons: light, modern enterprise SaaS with restrained blue.
- Preserve all existing working local demonstrations and real data.

## Visual Findings

- The existing application shell uses a deep-blue gradient, translucent active item, large side rail and structural `⚖️` emoji.
- Structural emoji also appear in Chat, Graph, Laws, Login and Register. Their platform-dependent appearance makes the interface feel inconsistent.
- Global styles contain page-oriented legal colour variables, a gradient headline helper, late Google-font import, and no semantic surface/text/focus token system.
- The approved direction benefits from a single neutral surface hierarchy, crisp outline icons, smaller radius, restrained borders and a source-inspector-first information hierarchy.
- The frontend has no test runner script, but its existing `node --test` suite can run source-level visual-system contract tests without adding a dependency.

## Functional Findings

- The already repaired frontend supports API-derived dashboard case statistics, dynamic regulation browsing, graph law filtering, citation switching and source original-text display.
- The local frontend is Vite/Vue/Element Plus; changing its visual layer should not require replacing dependencies or changing backend routes.

## Decisions

| Decision | Rationale |
| --- | --- |
| Use system Chinese sans-serif for UI body text | Predictable rendering and a more contemporary B2B reading experience. |
| Retain serif for brand/rare high-level titles only | Keeps legal character without making operational pages feel like a document scan. |
| Use blue only for interactive/selected meaning | Maintains signal strength and reduces template-like colour noise. |
| Use a three-pane consultation workbench | Keeps evidence source inspection available without losing legal answer focus. |

## Issues Encountered

| Issue | Resolution |
| --- | --- |
| UI skill helper command pointed to an unavailable `search.py` | Used the complete documented design rules directly; no repeat attempt. |
