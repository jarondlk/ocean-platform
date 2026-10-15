# C10 readiness audit

Updated: 2026-10-15 JST. Branch: `overhaul`.
Audited checkpoint: `ae02e89d1d6f6b38c07d4a5a95c47976affda45b`.

**C10 is ready for explicit implementation selection. No prerequisite blocker
was found. C10 remains Not started and unselected.** This audit runs existing
regressions and verifies interfaces; it does not implement or accept the adapters.

## Prerequisites and source reconciliation

The specification and component manifest require **C02 and C09**.

- C02 is Complete for local software/synthetic acceptance. Nine of its twelve
  original accepted paths still match. Three are intentionally superseded:
  `api/main.py` matches accepted C07, `orchestration/unified.py` matches accepted
  C05, and `tests/test_derived_artifact_eligibility.py` matches the C01/C02 delivery
  audit. The scientific producer, full-abundance/missingness, receipt/history and
  invalidation implementations remain intact. Historical receipts are preserved.
- C09 is complete and delivered: implementation `9214bbe`, delivery `ae02e89`.
  All fourteen accepted source/test/generated/workflow hashes and both receipt
  checksums match. The current checkout differs from its CI-tested implementation
  only by its ten delivery documentation/evidence files.
- A fresh read of [C09 hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38703483565)
  confirms success: 2,460 backend tests/83.39% coverage; 84 actual PostgreSQL cases
  including 21 C09; 162 v1/132 legacy frontend tests, both typechecks/builds and
  production dependency audits, idempotent upsert and isolated backup/restore.
- C05's metagenome producer, explicit Kraken/MetaEuk field contract and regression
  suite match their accepted hashes. C08's twelve shared-contract paths match.
- Local HEAD and origin/overhaul match the audited checkpoint. All 36 current
  prototype files, 30 unrelated files, seven real scientific artifacts, two
  serving files and previously committed evidence remain unchanged.

[The verification receipt](evidence/c10-readiness-2026-10-15/verification.json)
records current and historical source bindings, command results and preservation.

## Fresh offline checks

| Check | Result |
|---|---|
| Exact C10 baseline: CTD, metagenome loaders, overview coverage | 36 passed; zero skips |
| C02 science/eligibility, C09 store/capture/transfer/fixtures, C08 contracts/fixtures and C05 metagenome contract | 534 passed; zero skips |
| Generated scope, catalogue schema, browser types, examples and snapshot schema/examples | All five current |
| Readiness harness Ruff, document links and diff checks | Pass |

The baseline is:

```sh
.venv/bin/python -m pytest tests/test_ctd.py tests/test_metagenome_loaders.py tests/test_overview_coverage.py -q --tb=short
```

Tests use explicit test settings, unused loopback database/model URLs and
temporary synthetic fixtures. Existing dependency/deprecation warnings remain
visible (one baseline, 23 prerequisite warnings). No service is started and no
real data is regenerated or imported. Unchanged PostgreSQL/frontend implementation
is covered by C09's accepted exact-source hosted run; those jobs are not rerun
locally for this readiness check. Pandas 2.3.3, PyArrow 23.0.1, Pydantic 2.13.5
and SQLAlchemy 2.0.52 are available in the project's Python environment.

## Adapter implementation boundaries

1. **Frozen inputs and canonical identities.** Read verified C09 bytes through an
   explicitly supplied v1 store/current access gate. Register CTD casts and depth
   observations separately, plus metagenome collection/QC and complete normalized
   abundance tables when supplied. Preserve source/campaign/dataset identities;
   a matching sample label alone does not establish one physical sample. C08
   requires all six dataset sections and source-specific descriptors.
2. **Scientific semantics before reuse.** Retain CTD units, depth units and
   sampling support; count casts separately from depth rows. The existing CTD
   summary groups by sample label, so qualify its grouping against the frozen
   source contract. Preserve actual collection-date precision, distinct run/QC
   dates, Kraken/MetaEuk assignments, abundance units/denominators and measured
   zero versus missing/omitted values. Missing metadata or full inputs must have
   explicit qualification/unavailable operations. Contig operations stay unavailable.
3. **Exact operations over complete matching rows.** Validate shared scope and
   current eligibility before pagination. Counts, coverage and descriptive
   summaries must consume the full matching frozen population, independently of
   preview limits, document ranking and embeddings. Legacy top-ten JSON fields
   and the overview helper's bounded live-path projections cannot stand in for
   complete abundance or snapshot-bound queries. Do not infer expected CTD casts
   or missing sampling days without an explicit sampling contract.
4. **Respect the capture boundary.** C09 captures whole enabled families and
   rejects nonempty scientific filters/analysis IDs before DB access. C10 applies
   row filters after verified capture. Capture registration currently includes
   all four source families, while disabled families are not exported; that does
   not authorize a fixture fallback or implement C11/C12. The executable
   `fixture_registry()` and frozen wire examples are synthetic registration
   references. Full source-aware table parsing and semantic validation are C10 work.
5. **Demonstrate C10 acceptance.** Add independent expectations for over 500
   matches, page-independent counts/aggregates, taxa absent from ranked summaries,
   missing/incomplete tables, source identity collisions and temporal precision.
   Reopen old snapshots after updated seals; reject malformed scopes, corrupted
   inputs and revoked access explicitly. Neither the 570 readiness passes nor
   C08's inventory fixtures prove these future adapter operations.

The existing C02 real-artifact regeneration/review and C05 serving rebuild remain
deferred. They do not block synthetic local C10 development. Actual data copying,
scientific publication, authenticated service/UI integration and GCP deployment
remain later separately selected work.

## Exact next action

After explicit C10 selection, read the specification/prompt, prerequisite handoffs,
C08/C09 contract guides and site-separation plan. Begin checkpoint 1 by defining
versioned frozen-table inputs and source-owned registration/semantics fixtures;
then implement exact operations and reproducibility acceptance. Only then create
`handoffs/C10.md` and mark C10 In progress. This audit does not start C10 or C11.
