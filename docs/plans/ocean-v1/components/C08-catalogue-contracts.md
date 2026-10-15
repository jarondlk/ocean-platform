# C08 — Catalogue contracts and fixtures

**Status:** Complete locally (2026-10-15 JST). **Prerequisites:** P00, C01. **Contract:** Context Catalog v1.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Define the shared information model used by humans, agents, adapters and the browser. Discovery must represent the entire permitted inventory, independent of retrieval rank or displayed page size. Establish types and reusable synthetic fixtures before implementing storage or endpoints.

Included: five roots, object identity, listings, scope, operation/receipt envelopes and acceptance fixtures. Excluded: ingestion, snapshots, adapters, catalogue API implementation, agent execution and UI. C09–C16 consume this contract rather than independently inventing navigation semantics.

## Existing entry points

Verified references: [source scope](../../../../retrieval/source_scope.py), [statistics capabilities](../../../../orchestration/statistics_catalog.py), and [existing overview tests](../../../../tests/test_overview_coverage.py). The current statistics catalogue and `orchestration/catalogue_cache.py` have bounded inventories; use their meaning as references without carrying their limits into exhaustive discovery. Read C01's accepted shared-scope handoff before defining query envelopes.

## Interface decisions

Freeze roots Data, Analyses, Statistics, Metadata and Relationships. Data contains CTD, SST, metagenome and eDNA. Nodes use stable canonical IDs independent of paths/names; facets and cross-links reference the same object. Dataset sections are Overview, Tables, Coverage, Methods, Provenance and Related. Private experiments never enter global published analyses automatically.

Define typed node/listing/query-result envelopes carrying schema version, snapshot, identity/kind, scope, availability, authority, provenance and supported operations. Listings expose filters, stable ordering, total matches or explicit unknown, returned count and cursor. Unknown is not zero. A cursor binds snapshot, scope and ordering. Permission changes invalidate access rather than preserve hidden membership. Summaries count distinct qualifying canonical descendants; cross-links do not inflate counts. Every count declares its entity and denominator. Separate preview truncation, source completeness and query completion. Keep ingestion, query readiness, publication, approval and embedding readiness independent.

## P00 contract reconciliation

Read P00's accepted UX handoff and provisional fixture adapter. Preserve useful
interaction states and labels while defining validated backend contracts; record
any mismatch requiring a UI change. Prototype models are design input, not an
existing scientific contract. Give frontend-v1 one versioned adapter boundary so
real data replaces fixtures without rebuilding the experience. Include approved
cross-site transfer identity/provenance fields from SITE_SEPARATION.md; a source
origin reference must not become a live dependency on the legacy site.

## Resumable checkpoints and acceptance

1. **Core schema:** define node, listing, scope and operation contracts using existing Python validation conventions and typed frontend representations. Acceptance: all five roots and source-specific distinctions fit without path-based identity or ambiguous counts.
2. **Synthetic catalogue:** add reusable fixtures for each source, cross-links, revoked/hidden nodes, gaps and unknown availability, plus a deterministic 100,000-object generator. Acceptance: a relevant rank-26 object and entries beyond page one remain inventory members.
3. **Contract checks:** validate page traversal, totals, complete-scope aggregates, stable IDs, permissions and explicit unknowns. Acceptance: listings and descendant summaries reconcile without duplicate counting; dataset queryability does not depend on embeddings.

Proposed future tests: `tests/test_context_catalogue_contract.py` and `tests/test_context_catalogue_fixtures.py`; run `python -m pytest` with those paths after creating them. Baseline compatibility: `python -m pytest tests/test_chat_source_scope.py tests/test_overview_coverage.py tests/test_api_schemas.py`. This component tests contracts/fixtures, not actual 100,000-object service performance.

## Compatibility, rollback and handoff

Add new versioned types; preserve old source aliases, API shapes and identifiers through adapters. No production migration occurs here. Record frozen fields, semantics, fixture import locations, test evidence and downstream guidance in `handoffs/C08.md`; update `STATUS.md` at checkpoints. Later incompatible changes require a documented contract revision and impacted-component review.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c08). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Local acceptance — 2026-10-15 JST

Python-owned v1 models, generated JSON Schema/TS types, shared wire examples and
an opt-in validated frontend boundary are complete. 274 required tests pass;
162 v1 tests, typecheck/build, 100,000-dataset exhaustive fixture traversal and
10,398 cross-runtime mutation cases pass. Full backend: 2,314 passed,
63 gated PostgreSQL skips, 82.28% coverage. No existing runtime or UI
source changes. See [contract guide](../C08_CATALOGUE_CONTRACT.md),
[handoff](../handoffs/C08.md) and [receipt](../evidence/C08/verification.json).
Reference fixture traversal is not real service performance or live authorization
acceptance. C09 and real storage/endpoints/UI/cloud work remain unselected.
