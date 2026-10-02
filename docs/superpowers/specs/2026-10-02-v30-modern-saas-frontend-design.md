# LexRAG V3.0 Modern SaaS Frontend Design

## Objective

Refresh the complete LexRAG frontend into a restrained, modern B2B legal-research workspace. The redesign must improve credibility and scanability without changing API contracts, legal-retrieval behaviour, or the truthfulness of displayed data.

## Approved Direction

**Modern enterprise SaaS (Direction B)**

- Neutral white and cool-gray surfaces; ink text; cobalt blue used only for current navigation, links, primary actions, and keyboard focus.
- Product visual language is calm, structured, and content-first. It must not rely on gradients, glass effects, decorative illustrations, oversized statistic cards, or generic "AI" sparkle treatments.
- Emoji are removed from navigation, page headings, message avatars, and structural UI. Use the existing Element Plus outline icon family instead.
- The `LexRAG` wordmark remains, but it is not accompanied by an emoji logo.

## Non-Goals and Invariants

- No backend/API/database change is in scope.
- Existing routes, permissions, real-time data, evidence-source switching, graph filtering, and documented empty/error states continue to work.
- No demo values or fabricated counts are introduced. Dashboard and graph values remain API-derived.
- Existing Element Plus components may be reskinned or composed differently; the dependency is not replaced.

## Design Tokens

Create global semantic CSS variables. Components consume tokens rather than page-local raw colors.

| Role | Token | Value |
| --- | --- | --- |
| Application canvas | `--surface-canvas` | `#F7F8FA` |
| Raised surface | `--surface-raised` | `#FFFFFF` |
| Subtle selected surface | `--surface-selected` | `#EFF6FF` |
| Primary text | `--text-primary` | `#172033` |
| Secondary text | `--text-secondary` | `#64748B` |
| Muted text | `--text-tertiary` | `#94A3B8` |
| Border | `--border-subtle` | `#E2E8F0` |
| Brand/action | `--brand-primary` | `#2563EB` |
| Brand hover | `--brand-primary-hover` | `#1D4ED8` |
| Focus ring | `--focus-ring` | `rgba(37, 99, 235, .28)` |
| Success/warning/danger | semantic state tokens | existing state semantics, contrast-compliant |

Typography uses the system Chinese sans-serif stack for interface and content. `Noto Serif SC` is reserved for the wordmark and optional top-level page title only. The type scale is 12 / 14 / 16 / 20 / 28px; body text has at least 1.5 line height. Numbers in tables and statistics use tabular figures. The spacing scale uses 4px units, with 8px as the default rhythm. Radius is 6px for controls and panels; elevation is limited to a single light shadow token.

## Shared Application Shell

1. Replace the current 220px dark-gradient sidebar with a 232px white navigation rail separated by a subtle right border.
2. Use a compact wordmark at the top; render all menu items with consistently sized Element Plus line icons.
3. Group primary work areas and management tools with visual spacing rather than decorative containers. The selected entry uses a pale-blue fill, medium text weight, and a 3px blue left indicator.
4. Keep the user/account area at the bottom with a clear label and a separately labelled sign-out affordance.
5. Use a 64px top command/header region on desktop when a page needs search or primary actions. Do not duplicate page title, route title, and section title at the same visual weight.
6. At narrower desktop/tablet widths, collapse the rail to icon-plus-tooltip mode before the main content becomes horizontally cramped. Preserve keyboard-accessible navigation.

## Page Patterns

### Dashboard

- Present a concise welcome/page heading with one primary next action.
- Replace decorative card grids with a small real-data status strip, then task-oriented entry points for legal consultation, regulation search, document processing, and cases.
- Display recent activity as a compact list or table with meaningful empty state and recovery action.

### Legal Consultation

- Use a three-column desktop workbench: conversation history, answer workspace, source inspector. The answer workspace is primary; history and source panels may collapse at narrower breakpoints.
- Replace avatar emoji with consistent icon/avatar components.
- Render each answer in a predictable hierarchy: conclusion, legal basis, analysis/risk, limitation, and actions. Evidence citations use numbered, blue, keyboard-accessible links.
- Keep all citations visible while a specific citation is selected. The source inspector distinguishes metadata, cited excerpt, and full original text; a selection never prevents choosing another citation.
- Make the input bar visually anchored with clear sending, loading, retry, and failure states. Do not imply an answer was verified when it was not.

### Regulations, Search, and Knowledge Graph

- Use a common page heading + filter/action bar + data viewport pattern.
- Regulation browsing has a clean directory tree and readable original-text pane; law selection is visible and independently switchable.
- Search results prioritize law name, article number, status, matched excerpt, and an explicit open-source action.
- The graph uses a neutral canvas, compact controls, accessible legend, law filter, loading state, and a right-side selected-node inspector. Avoid large decorative graph title treatments.

### Knowledge Base, Documents, Cases, Favorites, Scenarios, Settings, and Admin

- Standardise titles, actions, filter rows, table headers, pagination, detail drawers, and empty/error/loading states.
- Use one primary button per view; secondary and destructive actions are visibly subordinate and semantically labelled.
- Tables use compact but readable row height, aligned numeric/date columns, hover and keyboard focus feedback, and mobile overflow handling.
- Settings separates model configuration, account, and organisation controls into labelled sections with helper copy, inline validation, and non-secret key masking.

## Interaction and Accessibility Requirements

- All interactive controls have hover, active, disabled, and visible keyboard focus states. Use `:focus-visible` and the shared focus token.
- Do not rely on colour alone for validity, verification, or selection; preserve readable text labels and icons.
- Icon-only controls require `aria-label`/tooltip and a target of at least 40px by 40px on desktop.
- Respect `prefers-reduced-motion`; transitions are limited to opacity/transform and 150–220ms.
- Long legal text is constrained to a readable measure in panels, with line height 1.65–1.8. It must never be shortened merely to make cards look tidy.
- All API loading, error, and zero-data conditions use stable layout and give a user a next action where possible.

## Implementation Sequence

1. Establish tokens, base typography, Element Plus overrides, and shared `AppLayout` shell.
2. Redesign the dashboard and legal consultation workbench, including evidence/source states.
3. Apply the shared information architecture to regulations, search, and graph pages.
4. Standardise remaining management pages and authentication pages.
5. Run build and relevant frontend/API regression tests; manually inspect desktop and narrow viewport layouts, keyboard focus, citation switching, source-original-text display, and graph/law filters.

## Acceptance Criteria

- No structural UI emoji remains in the frontend source.
- No primary UI uses the existing dark blue gradient, generic gradient headline, or glass/card-heavy visual treatment.
- All pages share the approved palette, typography, spacing, icon and interaction rules.
- Existing locally demonstrable flows continue to work: consultation with source switching; original-text display; regulation switching; dashboard case statistics; graph law filter; knowledge-base and document lists; settings API key use.
- `npm run build` passes. Frontend focused tests and previously affected backend regression tests pass without changing their expected behaviour.
