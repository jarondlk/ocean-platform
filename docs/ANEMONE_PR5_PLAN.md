# ANEMONE PR5 — Live Pilot, Cloud Publication, and v0.4.0

> Status: local code implemented; real pilot, GCP validation, deployment and release pending
> Audited: 2026-09-03 JST, local `gcp-dev` worktree
> Dependency: accumulated PR1–PR4 implementation
> The user authorized the gated rollout sequence on 2026-09-03; pilot inputs and acceptance gates remain required

## Rollout order

Current checkpoint: code commit `bfc8c0a` is pushed and CI/CodeQL passed. The
user confirmed JPY 20,000/month total and delegated one-sample selection. The
first real canary passed local acquisition/storage/citation/role/recovery
checks, but unknown source classification blocks environmental analysis;
current cloud spend is still unverified. See
[`ANEMONE_PILOT_2026-09-03.md`](ANEMONE_PILOT_2026-09-03.md).

1. Review, commit and push PR1–PR5 to `gcp-dev`; require passing GitHub CI.
2. Approve the exact pilot scope, resource/spend limits and fresh credential
   delivery; validate the bounded real pipeline and scientific outputs in
   isolation using the operator runbook.
3. Merge the verified development branch into `main`, keeping both branches.
4. Deploy the verified build to GCP with backup/rollback preparation and pass
   authenticated application, evidence-navigation and data-plane checks.
5. Publish `v0.4.0` only after deployment acceptance.

Authorization to start this sequence does not supply missing pilot choices or
permit skipping acceptance gates. The implementation record below describes
local evidence, not a completed rollout.

## Implementation record — 2026-09-03

- A1–A3 are fixed with permanent regressions: complete registered manifests,
  verified bytes consumed by API/export/context, stable result IDs, retained
  per-run provenance, and sample/method filters before local/SQL ranking.
- `ingestion/artifact_store.py` implements bounded local/GCS immutable objects,
  generation-pinned reads, create-only receipts and CAS-merged history indexes.
  Tests exercise interruptions, replay, conflicts, tampering, concurrent
  registration, and a fake GCS client. No real bucket was used.
- Analysis serving reads registered objects without staging writes. Retrieval
  uses a serialized local cache capped at 512 MiB, checks fresh publication
  pointers and validates cached hashes. Canonical import marks eDNA pending;
  SQL serving requires the ready object pointer and committed DB generation to
  match. Import failure or incomplete materialization cannot enable stale eDNA.
- `scripts/run_anemone_job.py` separates inventory, acquisition, normalization,
  eDNA-only import/rollback validation, materialization, immutable recipe
  delivery, analysis, and provenance. It defaults to an offline plan and records
  safe operation reports. No in-process API ingestion or scheduling was added.
- Opt-in GCP job templates require an image digest and numeric secret versions;
  one task, parallelism one, no automatic retries, bounded timeout, separate
  acquisition credentials, and a read-only processing data mount. Rendering
  does not apply jobs or grant IAM. Serving templates select the object store.
- `scripts/evaluate_edna_pilot.py` verifies saved authenticated responses and
  explicit researcher verdicts against registered analyses/provenance. It does
  not generate answers or replace scientific review. Live tests are not claimed.
- Operator commands, IAM boundaries, failure handling and acceptance evidence
  are in [`../deploy/gcp/ANEMONE_PILOT.md`](../deploy/gcp/ANEMONE_PILOT.md).
  No new migration, frontend redesign or version bump was needed.
- Final local verification: 583 backend tests passed (8 PostgreSQL-gated skips),
  76.75% CI-boundary coverage, and all 8 PostgreSQL integration tests passed
  separately against a freshly migrated disposable PG16/pgvector database.
  All 14 frontend tests, typecheck, production build, Ruff, dependency
  consistency and diff checks passed. Alembic has one head, `20260902_0007`.
  The disposable database was removed; no live bucket, model or deployment
  validation is included in these results.

Remaining: approved pilot URL/limits, current provider conditions, fresh secrets,
real GCS/Cloud Run and memory/latency/cost checks, independent source/metric and
model-answer review, authenticated browser/role/export regression, backup/restore
and rollback rehearsal, committed build, deployment and release authorization.
Source-specific CTD/SST extraction and profile review depend on the chosen
pilot; no live overlap or qualified environmental input is assumed.

## 1. Outcome

A researcher can query a bounded real ANEMONE cohort, inspect exact sources
and method-separated analyses, follow current and historical citations, and
export reproducible research results from the deployed application.

PR5 completes and validates the existing integration; it does not add FASTQ
processing, archive-wide ingestion, scheduled synchronization, automatic
contamination correction, abundance inference, or new statistical models.
Keep scientific labels, units, and necessary limitations; no marketing copy or
redundant interface descriptions.

## 2. Audit findings and entry gates

The following is the historical entry audit. A1–A3 are now fixed and covered
by permanent tests. G1 has a local/GCS object-store implementation and simulated
protocol tests; real cloud behavior remains a rollout gate. The reproductions
describe pre-fix code, not current unresolved findings or production incidents.

### A1 — P1: verify every result against a registered manifest

`ingestion/edna_analysis_bundle.py:105–120` verifies the input-derived identity
but does not enforce the complete output-file contract or an independently
registered manifest hash for direct-ID reads. `verify_bundle` only hashes files
listed in the manifest; API table reads then open the requested table directly.

Reproduction: publish a synthetic run, remove `diversity.json` from the manifest
file map, and change its richness value. The direct table endpoint returns
HTTP 200 with the altered value. The catalog's pointer-hash check does not
protect direct table, export, or context access. This is an integrity-validation
gap, not evidence of an exposed filesystem-write exploit.

Required correction:

- Validate the exact versioned input/output file set and table schemas/counts.
- Register each published run's manifest digest outside the bundle and resolve
  it for all reads, including historical runs; latest-recipe pointers alone
  cannot authenticate history.
- Verify the bytes actually consumed by tables, exports, and chat context.
- Fail closed on omitted entries, changed outputs, adjusted hashes, symlinks,
  unregistered runs, and incomplete publications. Keep errors explicit.

### A2 — P2: retain provenance for superseded analysis runs

`ingestion/edna_analysis_bundle.py:206–217` builds provenance descriptors only
from the latest pointer for each recipe. Publishing the same recipe against
changed input replaces that pointer. A subsequent provenance snapshot no
longer contains the earlier analysis citation, although its bundle still exists.

Reproduction: publish two runs of the same recipe with different read counts.
`load_analysis(old_id)` succeeds, but `analysis_trace(old_citation,
provenance_descriptors())` returns `None` after the second publication.

Required correction: maintain an immutable per-run publication registry; keep
latest selection separate from history. Include retained registered runs in
local and GCS provenance snapshots, or resolve their pinned snapshot directly.
Test an old saved-chat citation through navigation, provenance, and exports
after refresh, process restart, and publication of a new snapshot. Historical
read access must not make stale analyses eligible for fresh chat injection.

### A3 — P2: constrain the candidate set before retrieval ranking

`request_scope` removes `sample_ids` from propagated filters. In
`api/main.py:5087–5089` and `5215–5216`, membership and recipe methods are applied
only after top-K retrieval. An excluded sample or method can occupy the result
window, starving the selected cohort of citable raw evidence.

An isolated ranked-backend stub reproduced an empty `/retrieve` response at
`k=1` when an excluded sample ranked ahead of an available included sample.
This confirms request plumbing and post-filter behavior, not live ranking.

Required correction: pass allowed sample IDs and recipe methods into both SQL
and local retrieval before candidate limits/ranking. Intersect explicit filters
without widening the cohort. Recompute diagnostics for the returned scope.
Add real PostgreSQL and local tests with more excluded candidates than K,
including sample-list-only recipes, one-method recipes, and empty cohorts.

### G1 — cloud deployment gate: do not publish through directory rename

Acquisition, normalization, retrieval bundles, and analysis publication rely
on directory rename/replace. Existing job templates write through a GCS FUSE
mount, and the foundation script does not request hierarchical namespace.
Google documents that directory renaming on flat-namespace buckets is disabled
by default and is non-atomic when enabled. This is a template/code compatibility
risk; the live bucket's configuration was not inspected in this audit.
[GCS FUSE filesystem semantics](https://github.com/GoogleCloudPlatform/gcsfuse/blob/master/docs/semantics.md)

A1–A3 were acceptance blockers and are now resolved locally. G1's real cloud
validation remains required before claiming release readiness.

## 3. PR5 implementation sequence

### 5A. Repair and lock down PR4 behavior

Implement A1–A3 with regression tests first. Share the per-run registry between
integrity verification and historical provenance. Document upgrade handling for
pre-registry bundles: explicitly verify/register them offline or regenerate;
do not silently trust an arbitrary existing directory.

Update bootstrap/readiness checks for every required publication-registry
table, including existing `corpus_publication`. Preserve all PR1–PR4 changes
and split reviewable commits by responsibility when committing is requested.

### 5B. Add storage-safe publication and bounded jobs

Recommended design: local POSIX staging plus immutable object uploads and a
conditional publication pointer, not rename of a bucket-mounted directory.
Reuse or extract the existing `GcsSnapshotStore` generation-precondition
pattern in `ingestion/provenance_snapshot.py`.

1. Compute and validate the complete bounded bundle in temporary local storage.
2. Upload immutable objects with create-only generation preconditions. A
   repeated upload may reuse identical bytes; conflicting content must fail.
3. Verify the complete manifest, object hashes, and recorded generations.
4. Publish the registered run/generation and readiness pointer only after every
   object is complete. Update mutable pointers with compare-and-swap.
5. Readers resolve registered manifests and pinned objects, using bounded local
   caches. Do not rely on FUSE metadata-cache freshness for mutable pointers.
6. Keep retrieval DB generation, publication lock, and pending/ready recovery
   coordinated. A crash after DB commit must not serve an older file generation.

Cloud Storage generation preconditions support create-only writes and reject
stale conditional updates. They do not make the DB/object-store operation a
single transaction; test each failure boundary explicitly.
[Cloud Storage request preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions)

Apply this boundary to raw snapshots, normalized bundles, retrieval bundles,
analysis bundles, and provenance publication. Retain local filesystem support.
Do not enable unsafe directory-rename settings as the release fix.

Job contract:

- `ocean-anemone-sync`: inventory by default; explicit reviewed scope and limits
  required for execution; no database mutation or embedding permission.
- Separate explicit normalization/import/materialization/analysis operations,
  through reviewed batch job templates or a strict stage allowlist. Do not run
  the entire legacy pipeline merely to import ANEMONE.
- One task, parallelism one, zero automatic retries; a proposed initial
  30-minute timeout. Manual reruns are idempotent and recorded.
- Mount username/password files from pinned Secret Manager versions only in
  the acquisition job. No credentials in args, logs, images, manifests, or git.
- Dedicated least-privilege acquisition identity; separate reviewed database
  and model permissions for downstream jobs. Serving remains read-only for
  research artifacts and cannot start in-process ingestion.
- Pin image digests and capture commit, contract, recipe, job execution,
  snapshot, normalization, retrieval, analysis, and provenance IDs in a
  credential-free operation report.
- Test cancellation, lost connection, size overflow, conflicting publishers,
  stale pointer/cache, and replay after DB commit. Failed staging is not served.

Size local staging for compressed data, decompression, normalization, outputs,
and upload overhead; Cloud Run memory is not an unlimited filesystem. Validate
with the chosen pilot before fixing resource settings.

### 5C. Approve and acquire the pilot

Decisions needed before authenticated inventory or paid execution:

| Decision | Proposed default; not yet approved |
| --- | --- |
| Dataset | One explicit MiFish sample canary, then one named sequencing run; prefer Miyagi/Onagawa only if inventory confirms useful coverage |
| Download limits | Canary: at most 20 inventoried files and 64 MiB selected transfer; run: no more than current contract limits of 2,000 files and 512 MiB, reduced to the reviewed inventory |
| Analysis | Both methods separately, genus baseline, explicit environmental-only policy, minimum one read; species and threshold sensitivity are separate recipes |
| Resources | Hard file/byte/row/timeout/model-request limits plus an operator-approved cloud/model spend ceiling |
| Governance | Confirm provider use, attribution, redistribution/export, retention, and automated-access conditions; record reviewer/date/source |
| Credentials | Fresh ten-day download credential delivered outside chat/repository; named renewal owner and expiry recorded without the secret |

Do not assume a password previously pasted into chat is suitable for deployment.
Do not widen scope automatically if a run exceeds limits. Review metadata,
controls, assay protocols, both assignment outputs, and missing-file reports
before executing. FASTQ and image files remain unselected.

Inventory and downloads are not proof of successful scientific integration.
Run the entire pipeline first against an isolated database and artifact prefix:
acquire → validate/normalize → dry-run merge → explicit merge → materialize →
bounded embedding refresh → analyses → provenance snapshot → evaluation.

Reconcile counts at each stage. Reimport the same snapshot and verify no
duplicate canonical rows or changed scientific outputs. Use synthetic changed
snapshots to verify retraction, inactive rows, and history if no real update is
available; do not fabricate an updated provider dataset.

### 5D. Qualify research outputs and environmental evidence

- Review raw-row-to-detection provenance and independently recompute selected
  composition/diversity/method results from the complete cohort, not top-K.
- Inspect environmental, negative-control, internal-standard, and unknown
  classifications; report unavailable or unpaired controls explicitly.
- Convert provider environmental metadata only with verified units. Do not
  treat source copies/mL as an independently calibrated result.
- Add source-specific CTD/SST extraction into the existing typed observation
  contract only where useful overlap exists. Retain source hashes/row locators,
  measured coordinates, UTC precision, depth, domain, footprint and coverage.
- Require reviewed site/unit/linkage profiles. Missing or out-of-footprint
  matches remain unavailable. No nearest-date substitution or causal claims.

No qualified CTD/SST overlap is **not** a blocker for the ANEMONE-only release;
record that limitation. Claim live cross-source validation only after an actual
qualified pair has been verified end to end.

Turn `evaluation/edna_research_cases.json` into reproducible evaluated requests
with real analysis IDs and saved request options, sources, context, answers,
model/version, audit outputs, and researcher verdicts. Keep live cases separate
from synthetic negative controls. Cover generic eDNA retrieval and explicit
analysis chat, both methods, unknown controls, read-count interpretation,
unresolved rank, zero versus missing, rejected SST linkage, stale runs, and
mixed-source regression questions.

Release gate: every citation in accepted evaluation answers resolves; no
unsupported abundance, accuracy, contamination-free, absence, or causal claim
is accepted. Record denominators and failures, not only a summary trust score.
Choose the query set and latency/cost bounds before the model evaluation.

### 5E. Migrate, deploy, verify, and release

Only after the preceding gates and explicit deployment authorization:

1. Record current deployed images, schema head, corpus generation, provenance
   pointer, user-metadata boundaries, and bucket namespace/retention settings.
2. Create a database backup and verify isolated restore. Rehearse additive
   migrations from the currently deployed schema, including authentication and
   chat tables; bootstrap and verify the complete required schema.
3. Run approved jobs with the same immutable application image used in staging.
   Reconcile data counts, hashes, method coverage, active rows and embeddings.
4. Generate and publish analyses and provenance after their inputs are ready.
5. Deploy a no-traffic candidate revision; test authenticated viewer/researcher/
   admin permissions, direct API/export access, historical citations, navigation,
   current/stale state, and unaffected CTD/SST/metagenome workflows.
6. Promote only after checks pass. Record image digests, job IDs, schema and
   artifact IDs, evaluation evidence, and rollback instructions.
7. Update versions/changelog/handoff, commit/push when authorized, and publish
   `v0.4.0` only after the release commit, deployed images, and evidence agree.
   Images must be built from an identified committed revision; release metadata
   can be a follow-up commit if it records post-deployment execution IDs.

Rollback: retain the prior application revision and immutable artifacts. Do
not automatically downgrade/drop corpus tables or restore over new user/chat
records. Pause affected serving/jobs on an integrity failure. Reconcile the
canonical corpus, embeddings, readiness pointer, and provenance together before
resuming; restoring an old pointer alone cannot undo a DB import. Rehearse the
chosen recovery procedure in isolation and retain audit history.

## 4. Expected change areas

- Analysis registry/verifier, provenance descriptors/snapshots, table/context
  readers, and corresponding API/local/PostgreSQL regression tests.
- Structured retrieval filters in API, unified orchestration, SQL/local
  retrievers, and diagnostics.
- Shared local/GCS bundle-store abstraction and publication failure tests.
- Acquisition and explicit downstream job templates, template renderer,
  resource/secret/IAM configuration, and pilot operation-report tooling.
- Pilot recipe/profile examples containing no credentials or real source data;
  evaluation runner/cases and authenticated research workflow checks.
- GCP runbooks, integration roadmap, TESTING, handoff, and release records.

## 5. Acceptance checklist

- [x] A1 integrity, A2 historical provenance, and A3 pre-ranking scope fixed.
- [x] Local and simulated GCS publication failure/concurrency/replay tests pass.
- [ ] Real GCS/Cloud Run and resource/cost validation pass.
- [ ] Pilot URL, budgets, credential delivery and provider conditions approved.
- [ ] Real bounded import validated in isolation; repeat import reconciled.
- [ ] Independent scientific checks and model answer review recorded.
- [ ] Cross-source availability truthfully documented; no unqualified links.
- [ ] Authenticated UI/API/export and legacy-source regressions pass.
- [ ] Backup/restore, migrations, readiness checks and rollback rehearsed.
- [ ] Current CI/build/dependency/security gates pass on the release commit.
- [ ] Authorized deployment verified and `v0.4.0` evidence published.

## 6. Audit verification record

On 2026-09-03 the backend suite passed 555 tests (7 service-gated skips), with
76.17% CI-boundary coverage. Fourteen frontend tests, typecheck, production
build, active Python Ruff checks, dependency consistency, a single Alembic head
(`20260902_0007`), and diff whitespace checks passed.

All 7 PostgreSQL integration tests also passed on a fresh, migrated PG16/
pgvector test database. An initial invocation omitted CI's prerequisite
migration step and failed 4 tests; rerunning with that setup on a new database
passed. The disposable audit container was stopped and removed afterward.
Existing Starlette/httpx, NumPy/netCDF, and Alembic deprecation/runtime warnings
remain; production-image validation is still a PR5 gate.

A1 and A2 were reproduced against disposable synthetic bundles; A3 used an
isolated ranked-backend stub. The temporary reproduction script is outside the
repository at `/private/tmp/ocean-pr5-audit.3V4ut3/reproduce.py`; permanent
regression tests are required during 5A. G1 is supported by code/template review
and official storage documentation, not a live GCP experiment.

The local preview tab and servers were closed and its disposable database was
removed. Synthetic scratch artifacts were retained. No production state or
provider data was changed; no runtime fixes were applied in this audit.
