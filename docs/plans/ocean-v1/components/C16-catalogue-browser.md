# C16 — Complete catalogue browser

Status: **Not started**. Prerequisites: **C14, C15**.

## Objective and boundaries

Deliver a standalone Context Catalog destination where researchers can inspect the entire permitted catalogue, every directory and subdirectory, without starting a conversation. Reuse this browser for context selection inside investigations later.

Include tree/list/inspector navigation, exhaustive search and filters, pagination, snapshot selection, deep links and accessible responsive behavior. Exclude automatic scope attachment, investigation persistence, agent execution, experimental approval and scientific query definitions.

Verified entry points: [data page](../../../../frontend/app/data/page.tsx), [record inspector](../../../../frontend/components/RecordInspector.tsx), [source table](../../../../frontend/components/SourceTable.tsx), [coverage view](../../../../frontend/components/SourceCoverage.tsx), and [backend proxy](../../../../frontend/app/api/backend/[...path]/route.ts). Reuse suitable presentation patterns without retaining any discovery ceiling from existing views.

## Interfaces and decisions

The full-page layout has a directory tree, contents listing and selected-item inspector. Show Data, Analyses, Statistics, Metadata and Relationships. Dataset inspection provides Overview, Tables, Coverage, Methods, Provenance and Related sections. Nodes use stable IDs rather than names as identity.

Use C14 responses directly for membership, totals and completeness; do not independently approximate dataset counts. Show current snapshot, breadcrumbs, active filters, matching totals and page continuation. Exhaustive catalogue search is distinct from documentary relevance search. Unknown coverage, unavailable operations, zero matches, empty directories and request failures receive different presentations.

Lazy tree loading and pagination are permitted, but every authorized descendant must remain reachable. Browser Back/Forward and reload restore selected snapshot, node, filters and inspector section. The standalone view defaults to latest eligible data; embedded use receives the investigation snapshot. Browsing never attaches data, pins constraints or refreshes an investigation. Emit an explicit selection event for C18 to handle.

## Resumable checkpoints

1. **Build canonical navigation.** Wire roots, child listings, breadcrumbs and inspector to C14. Acceptance: every node in a fixture can be opened directly and through its parent; cross-links retain identity; totals match tool responses.
2. **Prove large-inventory reachability.** Exercise the 100,000-object fixture. Acceptance: targets beyond legacy rank 25 and page one are reachable by tree and filters; every subdirectory can be traversed; loading pages never silently drops entries.
3. **Verify usable state restoration.** Acceptance: deep links, Back/Forward, reload and snapshot changes behave consistently; permission revocation clears protected content; keyboard and screen-reader tree navigation, narrow-screen drawers and English/Japanese labels remain usable.

## Validation, compatibility and handoff

Existing commands: `npm --prefix frontend run typecheck`, `npm --prefix frontend test`, and `npm --prefix frontend run build`. Planned new browser interaction tests cover navigation, paging, server totals, snapshot URLs and errors. Perform manual keyboard, screen-reader and mobile checks; record evidence rather than claiming automation proves them.

Keep specialist pages and legacy links accessible. Rollback disables the new browser route without affecting snapshots or saved evidence. Save reachability results, UI/tool parity, accessibility observations and selection-event contract in `handoffs/C16.md`; update `STATUS.md` per checkpoint.

## Copy-and-paste prompts

**Planning-only**

> Review C16 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this specification, mockups and C14/C15 handoffs. Reconcile with the actual checkout. Refine the plan; do not implement application changes.

**Implementation**

> Implement explicitly requested component C16 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this specification and C14/C15 handoffs; verify prerequisites in the actual checkout. Complete its checkpoints and checks, preserving unrelated changes. Update STATUS.md and handoffs/C16.md throughout. Do not start another component, make cloud writes or paid calls, or publish production data.

**Resume**

> Resume C16 only. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this specification, prerequisite handoffs and handoffs/C16.md. Reconcile progress with the actual checkout and evidence. Continue the first unfinished checkpoint; update STATUS.md and handoffs/C16.md. Do not repeat completed work, start another component, make cloud writes or paid calls, or publish production data.
