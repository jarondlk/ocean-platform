# C11 — SST adapter

**Status:** Not started. **Prerequisites:** C02, C09.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Represent satellite SST products and their complete eligible observations in the frozen Context Catalog. Support exact inventory and scoped coverage questions without retrieving individual documents or treating preview rows as the complete population.

Include product/collection/dataset registration, observation pages, defined counts, summaries and sampling-aware coverage. Exclude new remote acquisition, downloading missing dates, inventing spatial resolution, publication promotion, experiments and UI implementation.

Verified entry points: [regional publication](../../../../ingestion/regional_publication.py), [SST inventory](../../../../ingestion/sst_inventory.py), [research SST preprocessing](../../../../preprocessing/research_sst.py), [regional retrieval](../../../../retrieval/regional_sst.py), and [coverage API](../../../../api/overview_coverage.py). Use C02 eligibility decisions when selecting corrected products and derived tables.

## Interfaces and decisions

Implement C09 frozen-data adapters with C08 identities and common node sections. Preserve product, spatial resolution/support, calendar, measurement units, quality fields, source hashes and actual observation precision. Separate daily regional summaries from underlying grid observations; every aggregate names the entity counted.

The Data/SST hierarchy groups products before collections and datasets. Cross-links into Statistics and Metadata point to the same canonical records. Snapshot versions bind the exact products and coverage contracts used. Current canonical query availability must not depend on vector-index readiness.

Report zero matches, unknown coverage, unavailable product data and expected missing dates distinctly. Expected dates require the documented sampling contract and declared scope. Do not fill final-product gaps using interim data or silently combine products. A narrower product is not evidence for a wider requested region; unsupported geographic scopes require explicit failure or qualification.

## Resumable checkpoints

1. **Map products and contracts.** Register eligible immutable inputs with product boundaries, spatial support and expected sampling definitions. Acceptance: each fixture dataset has unambiguous identity and availability, including excluded or unavailable product cases.
2. **Implement queries and coverage.** Use shared validated scope filters over full frozen tables. Acceptance: totals are independent of pages; missing dates match a reference calendar only where a sampling contract applies; product and regional incompatibilities are visible.
3. **Establish parity.** Compare supported existing exact SST questions with adapter outputs. Acceptance: retained observations reproduce after publication rollover and do not mix final/interim generations or silently improve input resolution.

## Validation, compatibility and handoff

Existing regression command: `python -m pytest tests/test_sst_nasa_context.py tests/test_research_sst.py tests/test_regional_publication.py tests/test_overview_coverage.py`. Planned new adapter checks cover product isolation, zero/unknown distinctions, full-scope aggregation and snapshot rollover. No implementation validation is claimed here.

Preserve existing SST workflows and published artifacts. Rollback removes catalogue exposure through its flag without deleting snapshots. Save operation definitions, calendars, parity evidence and unresolved availability in `handoffs/C11.md`; update `STATUS.md` after each checkpoint.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c11). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.
