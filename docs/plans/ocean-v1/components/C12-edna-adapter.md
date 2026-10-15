# C12 — eDNA adapter

**Status:** Not started. **Prerequisites:** C01, C09.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Expose the eligible canonical eDNA corpus through immutable, scientifically qualified catalogue views. Exact counts, filters and coverage operate over all matching frozen rows while browsing remains paginated.

Include provider/project/dataset discovery, occurrence and assay tables, detections, classification qualifications and supported descriptive operations. Exclude new imports, classification review changes, physical sample identity inference, automatic scientific approval and frontend work.

Verified entry points: [canonical eDNA service](../../../../api/edna_service.py), [analysis eligibility](../../../../preprocessing/edna_eligibility.py), [classification rules](../../../../preprocessing/anemone_classification.py), [eDNA aggregation](../../../../orchestration/edna_aggregation.py), and [canonical models](../../../../db/models.py). Reuse shared rules rather than independently approximating SQL filters.

## Interfaces and decisions

Implement the C09 adapter contract over frozen canonical exports, using C08 identities and C01 scope validation. Snapshots bind assay records, source occurrences, detections and classification/relationship versions. Every result identifies counting unit, assignment method, eligibility definition, applied scope and operation version.

Preserve environmental/control/unknown classifications and assay distinctions, including target gene, primers and methods where provided. Report raw inventory and scientifically eligible cohorts as separate named populations. Source occurrences are not automatically physical samples; sequence reads are not organism abundance; detection frequency uses an explicit eligible denominator. Preserve coarse or unresolved dates without manufacturing precision.

Availability of canonical catalogue queries does not require materialized retrieval documents. Unknown taxonomy or unsupported method combinations must remain visible. Empty filtered results cannot become a claim of ecological absence. Current permissions apply to archived snapshot reads and totals as well as record pages.

## Resumable checkpoints

1. **Map canonical exports.** Register provider/project datasets and table sections using frozen IDs and classifications. Acceptance: exported counts and hashes reconcile with source generation; controls and unknowns remain identifiable.
2. **Implement qualified operations.** Apply shared eligibility, date, geography, taxa, assay and assignment-method filters. Acceptance: exact results match canonical service fixtures, denominators are explicit, and incompatible scopes fail before execution.
3. **Verify snapshot and inventory integrity.** Acceptance: pagination does not change totals, duplicate links do not duplicate entities, retrieval-unready data remains queryable when eligible, and later reviews do not rewrite an existing snapshot.

## Validation, compatibility and handoff

Existing regression command: `python -m pytest tests/test_edna_service.py tests/test_edna_aggregation.py tests/test_edna_taxonomy.py tests/test_api_edna.py`. Database parity uses `tests/integration/test_edna_aggregate_postgres.py` only against an explicitly configured disposable local test database. Planned new tests cover frozen export parity, classification rollover, occurrence/sample counts and method-separated queries. This document does not claim test execution.

Keep current eDNA endpoints and classifications compatible. Rollback disables the adapter without deleting snapshot exports or altering scientific approvals. Record reference cohorts, parity evidence, counting definitions and unsupported operations in `handoffs/C12.md`, updating `STATUS.md` at each checkpoint.

## Exact prompts

Readiness was verified on 2026-10-15 JST at `1d3b7b6`: 116 baseline, 677
prerequisite and 83 additional eDNA semantic tests pass; seven generated checks
are current. C01/C09 accepted sources reconcile. Read the
[readiness audit](../C12_READINESS_AUDIT_2026-10-15.md) for raw/eligible cohort,
four raw versus two scientific methods, denominator and retrieval-independence
constraints. This is readiness evidence only; C12 remains Not started/unselected.

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c12). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.
