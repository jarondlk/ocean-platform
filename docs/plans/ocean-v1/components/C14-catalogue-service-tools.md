# C14 — Catalogue service and agent tools

**Status:** Complete locally; source checkpoint and hosted delivery pending. **Prerequisites:** C04, C08, C09, C10, C11, C12, C13.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Provide one authenticated catalogue service for both human browsing and agent navigation. Catalogue membership must be exhaustive within permissions, filters and snapshot, rather than limited by retrieval ranking.

Include `/catalogue/*` discovery/query endpoints, typed agent wrappers, deterministic navigation, cursor pagination and validated scoped operations. Exclude agent planning, answer synthesis, unrestricted SQL, new scientific computations, UI work and experiment execution.

Verified entry points: [API application](../../../../api/main.py), [API schemas](../../../../api/schemas.py), [authentication](../../../../api/auth.py), [catalogue cache](../../../../orchestration/catalogue_cache.py), and [canonical eDNA queries](../../../../api/edna_service.py). Reuse established authorization and error conventions after C04 while replacing bounded catalogue assumptions.

## Interfaces and decisions

Implement `catalogue.overview`, `list`, `open`, `coverage`, `query` and `relationships`, plus `analysis.get_published`, through shared services and C08 contracts. Expose Data, Analyses, Statistics, Metadata and Relationships with stable identities and snapshot-aware links. The model never receives a database or administrative capability.

Listings return applied scope, deterministic ordering, total matching entries, returned count, cursor and completeness. Default record pages contain 100 rows and cap at 500. Query aggregates cover all matching eligible records, regardless of previews. Unknown totals remain unknown; incomplete source coverage is distinct from a truncated page.

Name/path/identity search is exhaustive and paginated. Optional relevance sorting cannot remove members. Ranked documentary search remains a separate later capability. Authorization precedes counts, facets, caches and returned data; permission changes invalidate access even for older snapshots. Cache keys bind effective access, scope and snapshot. Reject cursor reuse against mismatched queries rather than silently changing membership.

## Resumable checkpoints

1. **Expose typed services.** Wire registered adapters and roots to authenticated routes and tool wrappers. Acceptance: equivalent UI/API/tool requests return identical identities, counts, scope, qualifications and errors.
2. **Prove exhaustive traversal.** Add a 100,000-object fixture with relevant objects beyond legacy rank 25 and page one. Acceptance: cursor traversal visits every permitted object once; stable ordering, direct lookup and filters reach the target; cross-links do not inflate totals.
3. **Harden boundaries.** Acceptance: forbidden entries never appear in counts or search; stale/mismatched cursors fail explicitly; snapshot rollover preserves prior results; aggregate answers match complete reference calculations despite small previews.

## Validation, compatibility and handoff

Existing regression command: `python -m pytest tests/test_catalogue_cache.py tests/test_api_security.py tests/test_api_schemas.py tests/test_auth.py`. Planned new route/tool tests exercise the scale fixture, equivalence, permissions, pagination and resource-bounded queries. Use local fixtures, not paid model calls or production services.

Keep legacy `/chat` and source APIs compatible; protect new routes with the catalogue flag. Rollback disables exposure without destroying snapshots. Record endpoint/tool contracts, operation support, scale evidence and permission coverage in `handoffs/C14.md`; update `STATUS.md` per checkpoint.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c14). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.
