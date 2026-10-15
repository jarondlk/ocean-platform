# C12 readiness audit

Updated: 2026-10-15 JST. Branch: `overhaul`.
Audited checkpoint: `1d3b7b6ae924c41e7021a535783224e238992f2f`.

**C12 is ready for explicit local implementation selection. No prerequisite
blocker was found. C12 remains Not started and unselected.** Checkpoint 1 must
resolve the raw-inventory method representation and keep frozen canonical
queryability independent of legacy retrieval publication. Neither interface is
claimed implemented by this audit.

## Prerequisites and accepted source

The specification and component manifest require **C01 and C09**. C10/C11 are
adjacent implementation references, rather than formal prerequisites.

- C01 is Complete. Five of its ten original accepted source hashes still match.
  Five intentionally superseded paths match accepted later receipts:
  `api/main.py` matches C07; `orchestration/settings_planner.py` and
  `tests/test_auto_settings.py` match C06; `orchestration/publication_scope.py`
  and `tests/test_publication_scope_contract.py` match the C01/C02 delivery audit.
  Original receipts remain historical and unchanged.
- All fourteen accepted C09 paths match, including storage/capture/transfer,
  fixtures, schemas, tests and workflow. All twelve C08, ten C10 and ten C11
  accepted paths also match. C11 implementation `41cd876` differs from the audited
  checkpoint only by twelve delivery documentation/evidence files.
- A fresh read of [C11 exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38744193298)
  confirms success: 2,820 backend tests/84.04% coverage, 84 actual PostgreSQL
  cases, 162 v1 and 132 legacy frontend tests, both typechecks/builds and production
  dependency audits, idempotent upsert and isolated backup/restore. The actual
  PostgreSQL job includes `test_edna_aggregate_postgres.py`; these are prior hosted
  acceptance results, not fresh local C12 database tests. Current eDNA reference
  sources and that test file are identical to the exact CI-tested commit.
- Local HEAD and origin/overhaul match the audited checkpoint. All 30 unrelated
  files, seven real scientific artifacts, two serving files, 36 current P00 files
  and 345 previously committed evidence files remain unchanged.

[Verification receipt](evidence/c12-readiness-2026-10-15/verification.json),
[start snapshot](evidence/c12-readiness-2026-10-15/start-snapshot.json).

## Fresh checks

| Check | Result |
|---|---|
| Exact C12 baseline: eDNA service, aggregation, taxonomy and API | 116 passed |
| Current full C01 reference suites, C09 storage/capture/transfer and C08 contracts/fixtures | 677 passed |
| Classification/review application, eligibility/analysis, catalogue and nontarget semantics | 83 passed |
| Generated scope, catalogue schema/types/examples, snapshot and adjacent C10/C11 contracts | All seven current |
| Readiness harness Ruff, document links and diff checks | Pass |

**876 focused tests passed, zero final failures/skips.** The exact baseline is:

```sh
.venv/bin/python -m pytest tests/test_edna_service.py tests/test_edna_aggregation.py tests/test_edna_taxonomy.py tests/test_api_edna.py -q --tb=short
```

Explicit test settings use unused loopback database/model URLs and temporary
synthetic fixtures. Some additional classification/catalogue fixtures start
temporary loopback HTTP servers. The first sandboxed attempt could not bind those
sockets: 9 failures/14 errors, all `PermissionError`. That attempt is preserved.
Only the affected group and remaining generation checks were rerun with local
socket permission; all 83 cases then passed. The successful 116/677 checks were
not repeated. No application code changed to address an environment restriction.
Final warnings remain visible: one baseline, 167 prerequisite and one semantic
dependency/deprecation warning.

No persistent service, source database, external provider or model is accessed.
No real data is acquired/copied/regenerated, and no classification or publication
is changed. The unchanged broad backend/frontend/PostgreSQL implementations are
covered by the verified hosted run; no full backend or PostgreSQL service is
repeated locally for this readiness audit.

## Required C12 implementation decisions

1. **Freeze the complete relational inputs.** Define source-owned occurrence,
   assay, detection, method-availability and classification/review exports,
   retaining exact scientific/source hashes and source/publication/classification/
   relationship/operation generations. Preserve provider/locus/team/project/run
   namespaces and source-qualified IDs. C09 requires `canonical_rows` and
   `classifications` roles for every eDNA dataset; its small synthetic exports
   are registration examples, not a complete canonical eDNA parser. Register
   explicit v1 inputs and current gates; no mutable-path or fixture fallback.
2. **Separate raw inventory from eligible cohorts.** Reuse
   `evaluate_analysis_eligibility`, actual active assays, protocol fields and
   source-backed method availability. The compatibility helper
   `environmental_analysis_eligibility(sample, assay_count)` substitutes known
   protocol fields and is insufficient for frozen scientific eligibility.
   Preserve environmental/control/unknown tri-state classification with
   `validate_sample_classification` and exact optional review lineage. A later
   review creates a new snapshot; it cannot rewrite retained classifications or
   grant scientific approval automatically. Current access/withdrawal still
   governs historical reads and totals.
3. **Resolve raw-method transport explicitly.** The canonical service supports
   four raw labels: target/nontarget variants of `qcauto` and `qcauto_95pct_3nn`.
   Existing analysis recipes, shared eDNA scope and C08 `EDNADescriptor` support
   the two target methods. Nontarget rows remain queryable raw inventory and
   carry `method_not_supported` for environmental analysis. Checkpoint 1 must
   define an additive/versioned raw-inventory representation and test browser/
   schema compatibility before exposing mixed or nontarget dataset descriptors.
   Do not coerce nontarget labels into target methods, silently drop raw rows or
   use an enum extension to grant unsupported scientific execution.
4. **Preserve canonical filter semantics.** Reuse/extract shared predicates and
   compare frozen operations with the canonical service's disposable database
   fixtures. Keep assay, method, target status and taxon predicates correlated
   to the same assay; a matching sibling assay cannot satisfy the selected assay.
   A source-backed available empty method table remains available even with zero
   detections. A missing method/table remains unavailable. Some raw filters
   (assay/locus/team/target status) exceed current shared scope fields; source-owned
   parameters must be typed, compatible with pinned scope and explicitly rejected
   when unsupported. Preserve collection-date precision, unresolved dates and
   coordinate qualifications; do not manufacture times or infer physical areas.
5. **Name entities and denominators.** Count source occurrences, assays, assignment
   rows and reads separately. `sample_id` is not proof of one independent physical
   sample; reviewed physical linkage belongs to its explicit registry/relationship
   contract. Alternative assignment methods share sequence evidence and must not
   be summed as independent observations. Detection frequency uses a declared
   method/protocol-specific eligible denominator, including eligible empty tables;
   selecting a taxon's positive rows must not reduce its denominator to positives.
   Preserve zero/missing/column-absent concentration states and source units.
   Reuse taxonomy resolution so padded ancestor/unknown labels do not acquire
   invented species precision. A filtered zero is not ecological absence.
6. **Remove retrieval readiness from the new query boundary.** The existing
   `ingestion.edna_aggregate.build_aggregate` checks a live publication pointer and
   requires canonical/retrieval readiness together. Its SQL semantics are useful
   references; invoking that entry point would violate C12's canonical-query
   independence. Query verified frozen rows directly through validated operations,
   without model/document materialization or live legacy dependencies. Apply C01
   compatibility rules where relevant; model readiness cannot authorize an
   incompatible or unresolved scientific scope.
7. **Demonstrate new adapter acceptance.** Add independent full-population counts
   beyond 500 rows, late-page discovery, duplicate-link deduplication, active/raw/
   eligible cohort differences, method/assay correlation, controls/unknowns,
   taxonomy and precision cases, missing versus empty inputs and explicit
   denominator checks. Compare against actual disposable PostgreSQL canonical
   queries, then verify classification rollover, old-snapshot replay, current
   revocation, corruption failures and synthetic independent-copy parity. Existing
   readiness/hosted results do not prove these future C12 adapter operations.

Real source imports/copies, classification review changes, physical identity
inference, scientific approval, frontend integration and GCP operations remain
outside local C12 selection. Earlier deferred real scientific regeneration and
serving rebuild work do not block this synthetic implementation.

## Exact next action

After explicit C12 selection, read its specification/prompt, C01/C09 handoffs,
C08/C09 contracts and site-separation plan. Start checkpoint 1 with versioned
relational fixtures and a compatible raw-method representation; then implement
qualified frozen operations and independent database/snapshot parity. Only after
selection create `handoffs/C12.md` and change implementation status. This audit
starts neither C12 nor C13.
