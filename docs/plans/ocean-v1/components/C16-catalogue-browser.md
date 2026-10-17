# C16 — Complete catalogue browser

**Status:** Complete local acceptance; source checkpoint and exact-source hosted delivery pending. **Prerequisites:** P00, C14, C15.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Deliver a standalone Context Catalog destination where researchers can inspect the entire permitted catalogue, every directory and subdirectory, without starting a conversation. Reuse this browser for context selection inside investigations later.

Include tree/list/inspector navigation, exhaustive search and filters, pagination, snapshot selection, deep links and accessible responsive behavior. Exclude automatic scope attachment, investigation persistence, agent execution, experimental approval and scientific query definitions.

Verified entry points: [data page](../../../../frontend/app/data/page.tsx), [record inspector](../../../../frontend/components/RecordInspector.tsx), [source table](../../../../frontend/components/SourceTable.tsx), [coverage view](../../../../frontend/components/SourceCoverage.tsx), and [backend proxy](../../../../frontend/app/api/backend/[...path]/route.ts). Reuse suitable presentation patterns without retaining any discovery ceiling from existing views.

## Interfaces and decisions

The full-page layout has a directory tree, contents listing and selected-item inspector. Show Data, Analyses, Statistics, Metadata and Relationships. Dataset inspection provides Overview, Tables, Coverage, Methods, Provenance and Related sections. Nodes use stable IDs rather than names as identity.

Use C14 responses directly for membership, totals and completeness; do not independently approximate dataset counts. Show current snapshot, breadcrumbs, active filters, matching totals and page continuation. Exhaustive catalogue search is distinct from documentary relevance search. Unknown coverage, unavailable operations, zero matches, empty directories and request failures receive different presentations.

Lazy tree loading and pagination are permitted, but every authorized descendant must remain reachable. Browser Back/Forward and reload restore selected snapshot, node, filters and inspector section. The standalone view defaults to latest eligible data; embedded use receives the investigation snapshot. Browsing never attaches data, pins constraints or refreshes an investigation. Emit an explicit selection event for C18 to handle.

## Prototype-to-service integration

Read the P00 handoff and reuse frontend-v1; do not restart the UI from the static
mockup. Keep the accepted UX and iterate on any contract-driven change. P00's
synthetic interactions do not satisfy this component's real-service acceptance.
Use the actual frontend-v1 scripts established in P00 and record runtime/browser
checks against the appropriate v1 services. Existing frontend paths above are
reference implementations, not the target for the new site.

## Resumable checkpoints

1. **Build canonical navigation.** Wire roots, child listings, breadcrumbs and inspector to C14. Acceptance: every node in a fixture can be opened directly and through its parent; cross-links retain identity; totals match tool responses.
2. **Prove large-inventory reachability.** Exercise the 100,000-object fixture. Acceptance: targets beyond legacy rank 25 and page one are reachable by tree and filters; every subdirectory can be traversed; loading pages never silently drops entries.
3. **Verify usable state restoration.** Acceptance: deep links, Back/Forward, reload and snapshot changes behave consistently; permission revocation clears protected content; keyboard and screen-reader tree navigation, narrow-screen drawers and English/Japanese labels remain usable.

## Validation, compatibility and handoff

Planned commands, after P00 establishes these scripts: `npm --prefix frontend-v1 run typecheck`, `npm --prefix frontend-v1 test`, and `npm --prefix frontend-v1 run build`. Planned new browser interaction tests cover navigation, paging, server totals, snapshot URLs and errors. Perform manual keyboard, screen-reader and mobile checks; record evidence rather than claiming automation proves them.

Keep relevant v1 specialist workflows accessible; legacy links remain on the existing site. Rollback disables the v1 browser route without affecting snapshots or saved evidence. Save reachability results, UI/tool parity, accessibility observations and selection-event contract in `handoffs/C16.md`; update `STATUS.md` per checkpoint.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c16). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Acceptance result — 2026-10-18 JST

All three local checkpoints pass. The real authenticated C14/C16 fixture routes
match134 shared-tool responses; all51 sealed-fixture objects are reachable through
canonical parents. The actual client and URL state traverse100000 datasets over
200 listing/205 tree pages. Final v1 tests510, typecheck/build, full backend3895
with127 PostgreSQL-gated skips/84.87% coverage and nine generated checks pass.
[Contract](../C16_CATALOGUE_BROWSER_CONTRACT.md), [handoff](../handoffs/C16.md),
[browser observations](../evidence/C16/browser-qa.md). Manual accessibility-tree
and keyboard observations are recorded; spoken screen-reader and independent
assistive-user assessment are not claimed. Real identity, scientific validation,
production performance and deployment retain their separate operational gates.
