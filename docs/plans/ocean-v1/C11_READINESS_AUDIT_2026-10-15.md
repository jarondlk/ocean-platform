# C11 readiness audit

Updated: 2026-10-15 JST. Branch: `overhaul`.
Audited checkpoint: `75703457db6cc011506765c4c24ce3aa8106badc`.

**C11 is ready for explicit local implementation selection. No prerequisite
blocker was found. C11 remains Not started and unselected.** This audit verifies
existing software and source contracts; it does not implement the SST adapter.

## Prerequisites and delivery

The specification and component manifest require **C02 and C09**. C10 is a useful
adjacent implementation reference, rather than a formal prerequisite.

- C02 is Complete for local software/synthetic acceptance. Nine of its twelve
  original source hashes still match. Three intentionally superseded paths match
  later accepted receipts: `api/main.py` matches C07, `orchestration/unified.py`
  matches C05, and `tests/test_derived_artifact_eligibility.py` matches the C01/C02
  delivery audit. Scientific producers, retained history and eligibility remain
  intact; original receipts have not been rewritten.
- All fourteen accepted C09 files, twelve C08 shared-contract files and ten C10
  adapter files match their accepted hashes. The original C09/C10 local and
  delivery receipts are preserved. C10 implementation `c3d5b8b` and delivery
  checkpoint `7570345` differ only by ten delivery documentation/evidence files.
- A fresh read of [C10's exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38731722030)
  confirms success. Its accepted delivery records 2,570 backend tests/83.68%
  coverage, 84 actual PostgreSQL cases including 21 C09 cases, 162 v1 and 132
  legacy frontend tests, both typechecks/builds, zero-vulnerability production
  dependency audits, idempotent upsert and isolated backup/restore. These are
  prior hosted acceptance results, not fresh local C11 test counts.
- Local HEAD and origin/overhaul match the audited checkpoint. All 30 unrelated
  files, seven real scientific artifacts, two serving files, 36 current P00
  files and 308 previously committed evidence files remain unchanged.

[The verification receipt](evidence/c11-readiness-2026-10-15/verification.json)
binds source reconciliation, commands, hosted status and preservation. The
[start snapshot](evidence/c11-readiness-2026-10-15/start-snapshot.json) retains
the individual preservation hashes.

## Fresh offline verification

| Check | Result |
|---|---|
| Exact C11 baseline: NASA context, research SST, regional publication and overview coverage | 55 passed |
| C02 science/eligibility, C09 store/capture/transfer/fixtures and C08 contracts/fixtures | 482 passed |
| Acquisition census, context review and regional normalization semantics | 61 passed |
| Immutable panel/collection and daily sampling/monthly calendar contracts | 8 passed |
| Generated scope, catalogue schema, browser types, examples, snapshot and adjacent C10 adapter contracts | All six current |
| Readiness harness Ruff, document links and diff checks | Pass |

**606 tests passed, zero failures or skips.** The exact baseline is:

```sh
.venv/bin/python -m pytest tests/test_sst_nasa_context.py tests/test_research_sst.py tests/test_regional_publication.py tests/test_overview_coverage.py -q --tb=short
```

Checks use explicit test settings, unused loopback database/model URLs and
temporary synthetic fixtures. Provider transports in acquisition tests are
mocked. No service starts, real publication, scientific regeneration or data
import occurs. Existing warnings remain visible: 1,532 baseline, 23 prerequisite,
568 SST semantics and 38 panel/collection warnings, including xarray/NumPy
deprecations, the NumPy extension-size runtime warning and pandas concatenation
warnings. They do not produce failures in this environment.

No application, frontend, SQL or workflow source changes in this audit.
Unchanged broad backend, PostgreSQL and frontend acceptance is covered by the
verified exact-source hosted run; those broad jobs are not rerun locally.

## Contracts C11 must implement

1. **Own the SST frozen-input contract.** Define versioned product, collection,
   dataset, observation and coverage inputs with C08 canonical identities and
   all six common dataset sections. C09 already supplies immutable bytes,
   source/publication/operation bindings and current access checks. Its example
   SST exports are synthetic registration references, not a complete product
   schema. C10's CTD/metagenome-only models must not silently acquire SST rows.
   Use explicit v1 stores/inputs, source generations, bounds and current gates;
   missing inputs or unsupported schemas fail without a live or fixture fallback.
2. **Preserve each product's meaning.** Retain product/version, generation,
   measurement type, units, quality/uncertainty masks, exact hashes, spatial
   support and actual precision. MUR foundation analysis is not a direct
   satellite retrieval or an hourly station measurement. The retained regional
   delivery is 0.05-degree grid-point subsampling with cosine-latitude weighting,
   not a finer native-grid reconstruction. Daily regional means and grid-point
   observations are separate counted entities. If underlying points are absent,
   their operations remain unavailable; do not recreate them from summaries.
3. **Keep final/interim, eligibility and scope separate.** Final MUR `04.1`
   excludes retained `04.1nrt` evidence. Final gaps remain gaps. Operational
   publication acceptance is not independent scientific approval. Apply C02's
   current eligibility policy to corrected/derived inputs, preserving unknown,
   review-required, invalidated and superseded states. Acquisition inventory
   tiles/halos and reported coordinates are not reviewed scientific areas.
   A product with narrower spatial support cannot satisfy a wider request;
   validate containment or return an explicit qualification/unavailable result.
4. **Freeze calendars and expected sampling.** `monthly_area_context` uses
   Asia/Tokyo dates and requires a declared daily product; regional publication
   validates its 2020–2023 period against a 1,461-day UTC-date calendar. Its
   `daily_rows` helper copies the UTC date into a legacy `date_jst` field. C11
   must retain the actual date basis and test UTC/JST boundary cases instead of
   trusting that field name. Date-only values never gain invented timestamps.
   Expected missing dates require a product sampling contract and declared
   temporal/spatial scope. The overview helper's inferred extent/default window
   is not a generic sampling contract; daily expectations do not apply to an
   instant-retrieval product automatically.
5. **Query complete frozen populations before paging.** Existing ranked regional
   retrieval, live-pointer caches and overview projections are regression
   references. They cannot be the new exhaustive inventory or snapshot query
   engine. Product-qualified identities prevent same-date product collisions.
   Totals, summaries and coverage consume all matching eligible rows, independently
   of page/preview limits and embeddings. Keep known zero, unknown coverage,
   unavailable products, invalid observations and expected gaps distinguishable.
6. **Establish independent C11 acceptance.** Add reference expectations for product
   isolation, quality exclusions, leap days and UTC/JST boundaries, unsupported
   geographic scopes, zero/unknown/unavailable states, more than 500 matching
   observations and page-independent totals. Reopen old snapshots after a new
   publication/seal; verify exact retained results, current revocation checks and
   explicit corruption/missing-input failures. Existing readiness tests do not
   prove these future SST adapter operations.

Real-artifact regeneration/review and the older serving rebuild remain deferred.
They do not block synthetic local C11 development. Actual source copying,
acquisition, publication promotion, authenticated service/UI integration and GCP
deployment retain their later separately selected gates.

## Exact next action

After explicit C11 selection, read its specification/prompt, C02/C09 handoffs,
C08/C09 contracts and the site-separation plan. Begin checkpoint 1 with immutable
product/support/sampling fixtures and excluded/unavailable cases, then implement
exact frozen queries and reproducibility acceptance. Create `handoffs/C11.md`
and change implementation status only after selection. This audit starts neither
C11 nor C12.
