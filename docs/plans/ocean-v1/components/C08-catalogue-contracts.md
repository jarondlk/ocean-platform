# C08 — Catalogue contracts and fixtures

**Status:** Not started. **Prerequisites:** C01. **Contract:** Context Catalog v1.

## Objective and boundaries

Define the shared information model used by humans, agents, adapters and the browser. Discovery must represent the entire permitted inventory, independent of retrieval rank or displayed page size. Establish types and reusable synthetic fixtures before implementing storage or endpoints.

Included: five roots, object identity, listings, scope, operation/receipt envelopes and acceptance fixtures. Excluded: ingestion, snapshots, adapters, catalogue API implementation, agent execution and UI. C09–C16 consume this contract rather than independently inventing navigation semantics.

## Existing entry points

Verified references: [source scope](../../../../retrieval/source_scope.py), [statistics capabilities](../../../../orchestration/statistics_catalog.py), and [existing overview tests](../../../../tests/test_overview_coverage.py). The current statistics catalogue and `orchestration/catalogue_cache.py` have bounded inventories; use their meaning as references without carrying their limits into exhaustive discovery. Read C01's accepted shared-scope handoff before defining query envelopes.

## Interface decisions

Freeze roots Data, Analyses, Statistics, Metadata and Relationships. Data contains CTD, SST, metagenome and eDNA. Nodes use stable canonical IDs independent of paths/names; facets and cross-links reference the same object. Dataset sections are Overview, Tables, Coverage, Methods, Provenance and Related. Private experiments never enter global published analyses automatically.

Define typed node/listing/query-result envelopes carrying schema version, snapshot, identity/kind, scope, availability, authority, provenance and supported operations. Listings expose filters, stable ordering, total matches or explicit unknown, returned count and cursor. Unknown is not zero. A cursor binds snapshot, scope and ordering. Permission changes invalidate access rather than preserve hidden membership. Summaries count distinct qualifying canonical descendants; cross-links do not inflate counts. Every count declares its entity and denominator. Separate preview truncation, source completeness and query completion. Keep ingestion, query readiness, publication, approval and embedding readiness independent.

## Resumable checkpoints and acceptance

1. **Core schema:** define node, listing, scope and operation contracts using existing Python validation conventions and typed frontend representations. Acceptance: all five roots and source-specific distinctions fit without path-based identity or ambiguous counts.
2. **Synthetic catalogue:** add reusable fixtures for each source, cross-links, revoked/hidden nodes, gaps and unknown availability, plus a deterministic 100,000-object generator. Acceptance: a relevant rank-26 object and entries beyond page one remain inventory members.
3. **Contract checks:** validate page traversal, totals, complete-scope aggregates, stable IDs, permissions and explicit unknowns. Acceptance: listings and descendant summaries reconcile without duplicate counting; dataset queryability does not depend on embeddings.

Proposed future tests: `tests/test_context_catalogue_contract.py` and `tests/test_context_catalogue_fixtures.py`; run `python -m pytest` with those paths after creating them. Baseline compatibility: `python -m pytest tests/test_chat_source_scope.py tests/test_overview_coverage.py tests/test_api_schemas.py`. This component tests contracts/fixtures, not actual 100,000-object service performance.

## Compatibility, rollback and handoff

Add new versioned types; preserve old source aliases, API shapes and identifiers through adapters. No production migration occurs here. Record frozen fields, semantics, fixture import locations, test evidence and downstream guidance in `handoffs/C08.md`; update `STATUS.md` at checkpoints. Later incompatible changes require a documented contract revision and impacted-component review.

## Exact prompts

**Planning-only**
> Review C08 without implementing. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C08-catalogue-contracts.md and handoffs/C01.md plus any C08 handoff. Inspect current checkout and prerequisite evidence. Report refinements only; do not edit application code or begin implementation without an explicit implementation request.

**Implementation**
> Implement only C08 after reading the planning README, MASTER_PLAN, DECISIONS, STATUS, this C08 specification and C01/C08 handoffs under docs/plans/ocean-v1. Verify C01 and the checkout; preserve unrelated work. Follow checkpoints and update STATUS.md and handoffs/C08.md after each. Run required tests before completion. Do not start another component, publish, make cloud writes, provision, deploy or run paid model evaluation.

**Resume**
> Resume C08 only. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C08-catalogue-contracts.md and handoffs/C01.md and C08.md. Reconcile prerequisites, checkout and test evidence before continuing the next checkpoint. Preserve unrelated work, retest changes and update status/handoff. Do not start another component, publish, make cloud writes, provision, deploy or run paid model evaluation.
