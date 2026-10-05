# v0.7.0 implementation candidate

Recorded 2026-10-05. Branch: `codex/v070-data-foundation`, based on `main`
`55d41469fb0694444e8c5b2211002179f09a776e`. Implements the
[accepted plan](RELEASE_0.7.0_PLAN.md) for [issue #89](https://github.com/jarondlk/ocean-platform/issues/89).
This is a review candidate, not a release or scientific acceptance record.
Implementation review: [draft PR #99](https://github.com/jarondlk/ocean-platform/pull/99).
Exact-source candidate `ff8dfe51141cf549277a389174594b28753c547f` passed
all four jobs in [CI run 324](https://github.com/jarondlk/ocean-platform/actions/runs/37262348375):
backend, frontend, PostgreSQL 16 migration/integration and dependency review.
Production remains v0.6.1; no production migration, registry application,
research publication, tag, traffic switch or batch job was performed.

## Implemented behavior

The research path calculates detection frequency from reviewed physical samples.
The denominator is fixed before taxon selection; one reviewed representative
assay and one assignment method contribute per unit. Environmental eligibility,
complete protocols/method tables, full resolved fish-species lineage and exact
source hashes are required. Unresolved units, controls, unknown classifications,
empty target tables and stale/incomplete evidence receive explicit exclusions.
Observed non-detection is zero; an unsampled group has a null frequency.

- Read-only readiness census validates the retained candidate without approving
  physical identity, classification or geography from matching metadata.
- Separate immutable sampling/area and SST-product registries bind reviewed
  evidence, hashes, rationale, representative assays and footprint uncertainty.
  Researchers create/approve/reject; administrators apply approved records.
  Expected content/version checks, source rechecks, transaction locks and an
  immutable event chain prevent stale or conflicting application. Classification
  continues through its existing separate review workflow.
- Additive migration `20261004_0015` creates six registry tables. Four evidence
  tables reject updates/deletes in PostgreSQL and through ORM hooks. Historical
  applied versions remain available; replay does not restore an obsolete head.
- Product-aware SST adapters validate explicit units, time coordinates, quality/
  uncertainty rules, masks, reviewed footprints and surface depth. MUR foundation
  analyses, Himawari retrievals and JCOPE model assimilation retain distinct
  semantics. Sample-time links use indexed bounded windows and exact pixel/granule
  provenance. Monthly context requires a reviewed daily product and sufficient
  daily coverage; instantaneous products never manufacture monthly means.
- Bounded acquisition preflight and a two-granule NOAA MUR pilot establish
  access/adapter behavior. This is an unapproved pilot, not a historical panel.
  Full multi-year acquisition is pending product, extent and coverage decisions.
- The deterministic engine publishes rankings, year/season/month series,
  temperature bins/contrasts, representative series, best-month spatial counts,
  a fixed endpoint comparison panel and intermediate-year follow-through.
  JST seasons include explicit partial winters. Contrasts preserve all-eDNA and
  SST-matched denominators separately. Q2 retains the Q1 top-ten candidate list. Representative selection uses equally
  weighted supported area-season contrasts; Q5 fixes its panel independently
  of SST and uses mean absolute endpoint changes. Rational frequency differences
  avoid floating cancellation creating spurious nonzero changes.
- Version-two bundles pin recipe, algorithm/runtime, canonical generations,
  classification fingerprint, review versions, retained SST panel metadata,
  memberships, exclusions and exact result IDs. Database snapshots are bounded,
  streamed and repeatable-read. Publication is manual and immutable. Existing v1
  table/file contracts remain unchanged. Known older research algorithms remain
  readable as historical; changed sources/heads require a new publication.
- Bounded APIs supply real available filter choices, paginated exact tables,
  provenance, filtered CSV and complete ZIP exports. Full export rejects partial
  filter requests. Historical data remains inspectable; historical/unavailable
  analyses cannot become current Chat answers through fallback.
- Six typed Chat intents and three English phrasings per intent use published
  rows directly, without a model or top-k retrieval. Unsupported wording and
  conflicting filters require clarification. Source checkboxes are preserved;
  SST comparisons require enabled compatible eDNA and SST. Saved answers retain
  scope, rows, citations, plot metadata and audit snapshots.
- Data and Chat share reviewed-footprint maps and separate frequency/SST series.
  Sampled zero, unsampled null, low support, missing periods and incomplete pages
  are explicit. Chart selection opens its exact row. Species/protocol choices
  show readable labels. SVG exports include recipe, result IDs, plotted rows,
  caption and completeness metadata. CSV/ZIP remain the full numeric export.
  Viewers receive inline Chat cards without privileged Data links.

## Local verification

Checks use synthetic fixtures and disposable local databases. They do not prove
the original Miyagi examples or live Google sign-in/role behavior.

| Check | Evidence / result |
| --- | --- |
| Full backend regression | 996 passed, 38 skipped; 79.03% coverage (required floor 70%). Skips include PostgreSQL-only tests, run separately. |
| Fresh PostgreSQL integration | 38 passed on PostgreSQL 18.3/pgvector, including migration/immutability, approved application, real repeatable-read input capture and current/historical publication. The PostgreSQL 16 integration/migration and isolated backup/restore CI job also passed at the recorded candidate commit. |
| Frontend | 57 tests passed, including five mounted research checks; TypeScript passed. Isolated production build passed with required authentication configuration. |
| Research answer matrix | All six intents × all 16 source combinations; all 18 supported English phrasings; exact row and citation checks; saved viewer snapshots, stale-source rejection and instantaneous/model monthly-context boundaries. No model invocation permitted in these checks. |
| Browser, synthetic disposable preview | Viewer source-disabled abstention and explicit SST re-enable; current/historical selection; Q4 sampled zero/positive/unsampled maps and exact row selection; researcher preview/rationale controls; admin cannot approve drafts. Data CSV reported export complete. |
| Export/provenance API | CSV metadata and exact filters, full ZIP contents, result trace and retained review approval hashes verified by regression tests. Downloaded CSV and SVG files were found and inspected locally: recipe metadata, exact plotted IDs/footprints and sampled-zero/null distinctions agree. The browser download-event hook did not expose them; full ZIP is independently verified through the API tests. |
| Lint/contracts/security | Ruff active paths, generated Chat scope check and diff whitespace checks pass. Production npm audit and remote dependency review pass. Both candidate images build and pass runtime QA; full scans report zero critical and zero reported Node/Python findings. Eight distinct high OS advisories remain for applicability/disposition review; a successful scan is not blanket security acceptance. |

The synthetic size probe uses 3,498 occurrences and 349,638 assignment rows with
three repeating fish taxa. Membership preparation took 1.056 s and calculation
2.098 s; 3,697 result rows occupied 7,656,537 bytes, with process peak RSS
315,899,904 bytes. It excludes SST links, full publication/status latency and
large taxon cardinality. It is a sizing probe, not a production performance SLA.
Caps currently allow 10,000 occurrences, 1,000,000 detections, 5,000 taxon keys,
200,000 result rows and 128 MiB bounded input/result snapshots; SST preparation
has separate grid/granule/observation limits. Work exceeding limits fails before
unbounded allocation. Representative real-cohort and request-latency profiling
remain required before release.

Browser QA caught and fixed duplicate React sibling keys between answer cards
and feedback, regionless Q4 bin aggregation, missing resolved taxon labels and
irrelevant legacy CTD-catalog errors on the research-review tab and legacy table controls flashing before research metadata loaded. The numeric Q4
fix advances the algorithm to `physical-detection-frequency-v3` (v2 corrected Q4, v3 fixes
Q2 to Q1’s top-ten list); old v1/v2 research
bundles remain readable as historical. These fixes are included in the candidate.

## Original real-data case dispositions

All six are currently **data_blocked**, not accepted/deferred by the user.

| Case | Required evidence before real acceptance |
| --- | --- |
| Q1 top-ten yearly/seasonal | Environmental classification, physical units/representative assays and reviewed Miyagi cohort; independently checked denominator/coverage. |
| Q2 high/low SST and series | Q1 evidence plus approved historical product, overlapping valid sample-time links, cuts/support and representative selection review. |
| Q3 best 2023 month/sardine map | Reviewed areas/cohort and sardine key; calculate month coverage independently of detections/SST. The discovery box is not a Miyagi boundary. |
| Q4 spatial SST conditions | Q3 evidence plus approved footprint/product and sample-time versus daily monthly coverage; retain sampled negatives and missing areas. |
| Q5 endpoint top-three changes | Q1 evidence and supported fixed area-season-protocol endpoint panel; insufficient data is valid if honestly demonstrated. |
| Q6 fixed-panel intermediate years | Q5 panel/taxa retained unchanged; eligible intermediate samples and approved SST links/coverage. |

The retained census has 343 negative controls, 3,155 unknown classifications,
zero reviewed environmental/physical units and 83 empty target tables per
method. The provisional box has limited 2023 coverage. Matching run labels,
`num_filter=2`, worldmesh strings or a broad latitude/longitude box do not supply
the missing scientific approvals. See the exact
[review packet](V0.7.0_SCIENTIFIC_REVIEW.md). Neither a nationwide alternative
nor the 2025–2026 JCOPE collection silently satisfies a 2020–2023 Miyagi case.

## Manual preparation and publication procedure

Use a designated environment and its existing operator credentials outside Git.
Do not point synthetic recipes/reviews at production. The commands below are
templates; the sample paths/IDs must be replaced with actual reviewed inputs.

1. Take and restore-test a fresh database backup using the existing release
   runbook before a production migration. Apply `alembic upgrade head` to a
   zero-traffic candidate environment. Verify head `20261004_0015`, existing
   history/corpus counts and registry permissions. After evidence exists,
   downgrade intentionally refuses to erase it: use an application rollback with
   the additive schema retained. Database restore is a separately reviewed action.
2. Run `python scripts/check_research_readiness.py --candidate-root <retained-candidate>
   --output <readiness.json>`. Compare with a fresh active production census before
   selecting actual source bindings. The retained archive census alone is not
   a fresh production database check.
3. Prepare exact classification reviews through the existing workflow. Prepare
   sampling/area and product JSON against the strict contracts in
   `preprocessing/research_recipe.py` and `preprocessing/research_sst.py`.
   In Data → Research reviews, a researcher saves a draft, checks current source
   bindings and records an evidence-backed rationale/decision. An administrator
   checks the approved record and applies it. A synthetic fixture approval does
   not approve actual provider data. Browser JSON requests, including their
   envelope, are limited to 1 MiB; divide large regional packets into reviewed
   cohorts or prepare an approved operator workflow rather than bypassing limits.
4. Preflight the proposed MUR pilot with `python scripts/prepare_research_sst.py
   --day 2020-05-15 --south <south> --north <north> --west <west> --east <east>
   --output <plan.json>`. Default is read-only. `--execute --output <fresh-directory>`
   downloads up to 32 bounded daily subsets with checksums and no cloud writes.
   Archive access, full extent, dates and quality rules require scientific review
   before a multi-year batch. Himawari acquisition is not implemented by this
   MUR-specific helper; reviewed local compatible granules can use the adapter.
5. Run `python scripts/run_research_sst_panel.py --product-registry-id <applied-id>
   --sampling-registry-id <applied-id> --granules <complete-manifest.json>
   --output <panel-preflight.json>`. Default normalizes/preflights without
   publishing. Review valid/missing coverage and bytes; add `--execute` only for
   the authorized immutable artifact store. A panel supports at most 1,600
   granules and 200,000 area observations; use a qualified bounded panel design.
6. Write a strict `DetectionFrequencyRecipe` pinning the actual generations,
   registry versions, region/calendar/method, target taxon, SST panel and explicit
   cuts/support policies. Run `python scripts/run_research_analysis.py
   --recipe <recipe.json> --sampling-registry-id <applied-id> --output <preflight.json>`.
   Review counts/exclusions and independently reproduce selected results.
   Add `--execute` to publish the exact run. Chat never triggers these commands.
7. Inspect the current run through Data's available analysis/filter selections,
   six Chat workflows, CSV/ZIP/SVG and result provenance. Preserve source choices
   and effective scope. Changed reviews/classification/canonical data require
   another explicit preparation/publication; historical answers remain snapshots.

## Container hardening candidate

The API image applies available OS updates, validates the hash-locked dependency
installation and removes pip/setuptools/wheel afterward. The standalone frontend
runner uses a pinned official Node 22 Debian 13 slim base, applies OS updates and removes global npm/npx/corepack package-manager trees;
startup remains `node server.js`. Non-root users and PostgreSQL 16 backup tools are
retained. Source/image exclusions now cover local archive caches, data and nested
real environment files. No credentials or retained archive should enter a build.

`deploy/gcp/cloudbuild-candidate-qa.yaml` prepares both images, an ephemeral
PostgreSQL 16 database, migrations, isolated backup/restore, application/batch
imports, a synthetic numeric/NetCDF probe, startup/auth-denial checks, runtime
tooling checks and full pinned Trivy scans. Reports and candidate images are
versioned by build ID. It performs no deployment or real-data operations. Submit
from a clean exact-commit export, not the working directory containing the retained
archive. Scan exit code zero means collection completed; review every high/critical
finding and preserve all severities/unfixed results before acceptance.

Google Cloud sign-in was refreshed on 2026-10-05. Final isolated build
`6815e352-275a-40fe-b4e7-d7bf5103b0c5` used the exact candidate commit above,
exported cleanly with 484 uploaded files (9.6 MiB), excluding real environment
files, caches and retained scientific data. It passed both image builds, PostgreSQL
16 migration/isolated backup restore, imports, the 7/15 numeric fixture, NetCDF,
non-root/tooling checks and startup/auth-denial checks. After the frontend base
correction, both scans report zero critical and no reported Node/Python findings.
API/frontend retain 44/43 high package/advisory records for the same eight OS CVEs,
with no fixed versions offered for the scanned distribution. No findings were
suppressed or security alerts dismissed. Exact digests, complete report locations,
the superseded first build and residual advisory review are in the
[container QA record](V0.7.0_CONTAINER_QA_2026-10-05.md). These are isolated
candidate images, not a live Cloud Run candidate or release authorization.
An October 5 read-only traffic check confirms 100% remains on
`ocean-platform-v061-assay1002`.

## Remaining acceptance and rollout

Scientific decisions and full historical data preparation are pending. Complete
the original-case dispositions with independent count/link/trace review, real
coverage/performance profiling, designated live viewer/researcher/admin and
history acceptance, responsive/keyboard/empty/error checks and the accepted
language requirements. The third research paper's detailed methods/supplement
still need a complete reading record before those protocols are reused.

Require passing exact-commit CI (including PostgreSQL 16), dependency/security
review, container image build/scan, fresh backup/restore and a zero-traffic GCP
candidate before a release. Review and merge the draft candidate only when its
scope/limits are accepted. Follow the existing exact-source build/tag, rollback,
manual job-image alignment and traffic-promotion procedure. No v0.7.0 release
or deployment is implied by local synthetic checks. Version declarations remain
at the currently published v0.6.1 until release preparation.
