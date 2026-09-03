# Handoff Document - OCEAN Platform

> **Last updated**: 2026-09-03 JST
> **Repository**: `jarondlk/ocean-platform`
> **Current status**: OCEAN Platform release `v0.3.0` is live on Cloud Run service `ocean-platform`. The invite-only Next.js + FastAPI application uses Google OIDC, the OCEAN Cloud SQL/pgvector data plane, Vertex AI, verified Provenance snapshots, and `ocean-*` Cloud Run Jobs. The former service is private and its deletion-protected SQL instance is stopped as a reversible rollback boundary; local Ollama development and the archived Streamlit reference remain supported.

---

## 1. Executive Summary

This repository contains a provenance-aware Retrieval-Augmented Generation
system for marine environmental monitoring in Miyagi Prefecture, Japan. It
combines CTD water profiles, metagenome sequencing outputs, and satellite SST
observations into a citation-grounded question-answering system with
cross-source evidence expansion and deterministic answer citation auditing.

The project has moved from a Streamlit-first research UI to a more cloud-ready
application shape:

- **Frontend**: Next.js academic UI in `frontend/`
- **Backend**: FastAPI service in `api/`
- **Database**: PostgreSQL 16 + pgvector through `compose.yml`
- **LLM runtime**: Ollama, usually host-run locally; optional compose overlay
- **Ingestion**: manual batch-run pipeline scripts, not automatic ingestion
- **Provenance**: strict raw-source contracts, SHA-256 manifests, row hashes,
  lineage inspection, and transactional upsert planning
- **Identity**: invite-only OpenID Connect through Auth.js; viewer, researcher,
  and admin permissions are re-resolved from PostgreSQL on every API request
- **Feedback**: persisted chat interactions, thumbs-up/down reasons/comments,
  and an audited admin review/export workbench
- **Production boundary**: fail-closed configuration, private API/database
  topology, shared PostgreSQL rate limits, enforcing security headers, verified
  backups, and CI security checks
- **Archive**: old Streamlit app and Streamlit container overlay preserved in
  `archive/legacy-streamlit/`

The active development direction is now Next.js + FastAPI. Streamlit should be
used only as historical reference and parity material.

---

## 2. What Changed Recently

### ANEMONE gated rollout started (2026-09-03)

- The user authorized this order: review/commit/push and CI, bounded real pilot
  validation, merge `gcp-dev` into `main` while keeping both, GCP deployment and
  verification, then GitHub release `v0.4.0`. This supersedes earlier statements
  that committing or proceeding with the gated rollout was not authorized.
- This commit records the accumulated PR1–PR5 implementation, tests and operator
  plans. It is not a release or evidence that live pilot validation passed.
- Pilot execution still requires an exact sample/run URL, approved transfer and
  spend bounds, fresh file/Secret Manager credentials, provider-condition review
  and researcher review of outputs. Do not infer these choices from permission
  to start the sequence. Do not merge, deploy or release ahead of those gates.
- Local checks were repeated before committing: backend/coverage and frontend
  tests/typecheck/build. GitHub CI must then validate the pushed commit,
  including the migrated PostgreSQL integration suite.

### ANEMONE PR5 local implementation (2026-09-03)

- The prior audit's three findings are fixed: analyses require a complete
  registered manifest and consume verified bytes; provenance retains every
  registered run; sample/method constraints reach SQL/local retrieval before K.
- Added bounded immutable object storage with GCS generation preconditions and
  retained registration indexes. Local POSIX staging replaces bucket directory
  renames. Analysis reads do not write staging; retrieval cache is serialized,
  capped at 512 MiB and checksum-verified against fresh readiness pointers.
- Canonical import marks eDNA pending before commit. PostgreSQL eDNA retrieval
  resumes only when the published pointer matches `corpus_publication`.
  Materializer locking spans DB commit and conditional readiness publication.
- New `run_anemone_job.py` separates acquisition, normalization, eDNA-only
  import/rollback validation, materialization, recipe publication, analysis and
  provenance. It defaults to an offline plan. Operation reports are persisted
  without arbitrary exception bodies or credential values.
- GCP templates are opt-in, use pinned image/secret identifiers and separate
  acquisition credentials. No IAM grants or jobs were applied. Processing mounts
  legacy data read-only; `EDNA_CACHE_DIR` must be local POSIX storage.
- Saved-answer evaluation verifies exact analysis/result IDs, citations,
  provenance and explicit human review. It makes no model calls and does not
  turn deterministic checks into a scientific-accuracy claim.
- Operator runbook: [`deploy/gcp/ANEMONE_PILOT.md`](deploy/gcp/ANEMONE_PILOT.md).
  Status and remaining gates: [`docs/ANEMONE_PR5_PLAN.md`](docs/ANEMONE_PR5_PLAN.md).
- Final verification: 583 backend tests passed (8 PostgreSQL-gated skips),
  76.75% CI-boundary coverage, all 8 separately run PostgreSQL integration tests,
  14 frontend tests, typecheck/build, Ruff, dependency consistency and diff
  checks passed. Alembic retains one head, `20260902_0007`. The disposable
  PostgreSQL container and its synthetic databases were removed.
- Still pending: approved pilot/limits/conditions, fresh credential delivery,
  real cloud and resource checks, scientific/model review, authenticated
  browser/permission/export checks, backup/restore and rollback rehearsal,
  deployment and `v0.4.0`. No live environmental profile is enabled.
- All PR1–PR5 changes remain uncommitted on `gcp-dev`. No real ANEMONE download,
  GCP mutation, commit, push, version bump or release was performed in this turn.
  Keep the academic, direct UI policy; no frontend redesign was introduced.

### ANEMONE PR1–PR4 audit and PR5 plan (2026-09-03)

- Preview tab and local frontend/API servers are closed. The disposable
  synthetic preview database was removed; temporary scratch artifacts remain.
- Three open findings supersede any implication below that PR4 is accepted:
  direct analysis reads can accept a table omitted from its manifest (P1),
  rerunning a recipe removes old citations from the generated provenance index
  (P2), and analysis membership/method filters run after top-K retrieval (P2).
  The first two were reproduced with isolated synthetic bundles; the third
  with a ranked-backend stub. No runtime fixes were applied in this audit.
- GCP execution is separately gated on storage-safe publication. Existing
  directory-rename publishers are not validated for the bucket mount; the
  live namespace/settings were not inspected. Prefer local staging plus
  immutable object uploads and generation-conditional publication, reusing the
  existing GCS provenance-store pattern.
- The actionable plan is [`docs/ANEMONE_PR5_PLAN.md`](docs/ANEMONE_PR5_PLAN.md):
  repair these findings, add cloud-safe publication/jobs, approve a bounded
  pilot and fresh credential delivery, validate scientific/chat outputs,
  rehearse migration/rollback, then authorized deployment and `v0.4.0`.
- A selected pilot URL/run, provider conditions, spend/resource bounds and
  credential-renewal owner remain open. No qualified CTD/SST overlap is assumed;
  unavailable overlap does not block the ANEMONE-only research workflow.
- Fresh audit gates: 555 backend tests passed with 7 service-gated skips,
  76.17% coverage, 14 frontend tests, typecheck/build, Ruff, dependency
  consistency, one Alembic head and diff checks passed. All 7 PostgreSQL checks
  passed separately after CI's migration prerequisite on a fresh disposable
  database; its container was removed. Existing tests do not cover the three
  audit failures. Keep the concise academic UI policy.
- Work remains uncommitted on `gcp-dev`. This audit updates planning documents
  only; no commit, push, live download, production migration or GCP deployment.
  The live `v0.3.0` status above is the last recorded release, not reverified here.

### ANEMONE PR4 implementation and PR3 repairs (2026-09-03)

- PR3 review findings below are resolved: explicit eDNA scope now controls
  supplementary context/audit, shared UTC intervals include complete end dates,
  and locked immutable-generation publication prevents stale/mixed fallback
  files. Migration `20260902_0007` records the ready corpus generation.
- PR4 adds explicit cohort/method/rank/control recipes; method-separated read
  composition, diversity, turnover, sequence-paired method reports, controls,
  standards, unit-qualified metadata and reviewed environmental matching.
- Analyses retain complete inputs/results/recipe/runtime in hashed immutable
  bundles. Read APIs, CSV/ZIP exports, exact citations/provenance, current versus
  historical status, and Data → eDNA analysis are implemented. Chat requires an
  explicit compatible current analysis; metrics never come from retrieved top-K.
- Environmental observations are explicit typed input, not automatic admission
  of legacy CTD/SST artifacts. A reviewed site/unit/domain/time/depth/coverage
  profile is required; no live profile is enabled. Raw eDNA generic cross-source
  expansion remains disabled. No read-count abundance inference, contamination
  subtraction, invented calibration, or inferential significance is supported.
- Keep the concise academic UI policy: scientific labels/units, no marketing
  descriptions, duplicated headings, or unexplained trust scores. Short IDs are
  for display only; exact identifiers remain recoverable in traces and exports.
- CLI and current scope are documented in `docs/ANEMONE_PR4_PLAN.md` and
  `docs/TESTING.md`; manual research answer cases are in
  `evaluation/edna_research_cases.json`. PR5 retains pilot approval, provider
  conditions/credentials, source-specific environmental extraction/review,
  live evaluation, backed-up GCP migration/jobs, deployment and `v0.4.0`.
- Work remains uncommitted on `gcp-dev`, alongside the existing PR1–PR3 changes.
  No push, real-data import or GCP mutation was performed. Historical planning
  and verification entries below are superseded by this record and TESTING.md.
- Final gate: 555 backend tests, 76.17% coverage, 7 separately run PostgreSQL
  checks, 14 frontend tests, typecheck/build, Ruff, dependency/diff checks and
  synthetic browser verification passed. Temporary servers/container stopped.
  Pending retrieval publication is reported as unavailable in Admin inventory
  and health, preserving the manual repair path without serving stale files.

### ANEMONE PR3 Review and PR4 Plan (2026-09-02, historical)

- A follow-up review found three open PR3 issues: explicit eDNA filters do not
  constrain supplementary analysis context, date-only end filters exclude
  timestamped observations on that day, and fallback publication can race
  after the materializer releases its DB transaction/advisory lock.
- The first two were reproduced with isolated in-memory fixtures; the third
  is a static concurrency finding. The focused PR3 suite passed 62 tests but
  does not cover these failures. Prior full-suite results below are historical,
  not proof that these review gaps are resolved. Fix them before acceptance.
- The proposed implementation contract is now in
  [`docs/ANEMONE_PR4_PLAN.md`](docs/ANEMONE_PR4_PLAN.md): explicit cohort/rank/
  method/control recipes, descriptive diversity and turnover, sequence-paired
  method comparison, control/standard reports, unit-qualified environmental
  context, immutable result provenance, read APIs and compact analysis UI.
- PR4 starts with the three prerequisite repairs. It must not pool assignment
  methods, equate read counts with organism abundance, silently remove
  controls, or inject analyses unrelated to the selected cohort. Use direct
  academic labels and preserve the existing no-marketing-copy UI policy.
- CTD/SST linking requires approved space/time/depth/domain profiles, measured
  or source-backed coordinates, and verified SST footprint/valid coverage.
  Legacy bay centroids/time-only links are ineligible. No live ANEMONE overlap
  was established. Missing qualified matches do not block the other analyses.
- The plan explicitly proposes descriptive associations, not automatic
  significance, causal claims, occupancy models, or predictive reliability
  scores. These need a later reviewed study/replicate design. PR5 retains live
  pilot approval, credentials, GCP operations, evaluation, and release.
- This turn changed planning/handoff documents only; it did not fix code,
  commit, push, download live data, migrate a database, or deploy.

### ANEMONE eDNA Integration PR1–PR3 (2026-09-02)

- The next planned MVP is ANEMONE DB MiFish eDNA metabarcoding integration,
  targeting release `v0.4.0`.
- A bounded authenticated inspection confirmed paired FASTQ files, sample and
  experiment metadata, internal standards, and separate QCauto and
  QCauto/95%-3NN community tables.
- ANEMONE is a new `edna_metabarcoding` source family with provider
  `anemone`; it must not be merged into the current shotgun `metagenome`
  source.
- The MVP ingestion boundary is interpreted compressed TSV data. FASTQ files
  are inventoried and cited but are not downloaded or processed by default.
- PR1 now implements secure bounded acquisition and a versioned raw-data
  contract. The command inventories exact sample/run scopes by default and
  requires `--execute` to download only the five interpreted TSV/XZ roles.
- The client keeps Basic-auth values out of arguments and manifests, rejects
  cross-origin redirects before credentials can be forwarded, applies file and
  byte limits, resumes validator-backed partial transfers, validates XZ and TSV
  structure, and publishes immutable content-addressed snapshots.
- Synthetic fixtures and a localhost Basic-auth server cover acquisition and
  failure behavior without contacting ANEMONE. No live source data is in git.
- PR2 implements deterministic normalization into seven immutable Parquet
  artifacts, explicit activation, six additive PostgreSQL corpus tables,
  eDNA anchor events, exact source-row lineage, and read-only upsert planning.
- The dedicated transactional merge retains stable IDs, separates scientific
  corrections from provenance-only refreshes, preserves controls and both
  assignment methods, and marks missing rows inactive only within the selected
  provider sample/run scope. It never deletes scientific or provenance rows.
- Local verification passed 40 focused PR1/PR2 tests. The full backend suite
  passed 503 tests with 5 expected service-gated skips and 76.03% coverage;
  Ruff, `pip check`, one Alembic head, and `git diff --check` also passed.
- The PostgreSQL integration module is wired into CI and passed two tests on
  an isolated no-volume pgvector/PostgreSQL 16 container, covering upgrade,
  downgrade/re-upgrade safety, idempotency, scientific corrections,
  provenance-only refreshes, first/last-seen history, and scoped inactivation.
- PR3 is implemented locally, with its contract and verification record in
  [`docs/ANEMONE_PR3_PLAN.md`](docs/ANEMONE_PR3_PLAN.md). It fixes one bounded
  retrieval document per active assay/assignment method, database-wide active
  corpus materialization, explicit method/control handling, structured eDNA
  filters and APIs, a compact bookmarkable Data view, exact evidence export,
  and source-file provenance. Migration `20260902_0006` extends the retrieval
  metadata and active lifecycle without replacing legacy rows.
- The default manual pipeline now loads canonical rows, materializes eDNA,
  refreshes embeddings, then publishes provenance. Provenance-only changes
  preserve embeddings; scientific text changes clear them. Local JSONL/Parquet
  artifacts include all active scopes, and the local embedding cache is keyed
  by document content plus model/provider identity.
- The eDNA Data view has explicit method/control/place/time filters,
  pagination, sample/assay/detection selection, source links, and CSV export.
  Both methods and unknown control states remain visible by default. No
  marketing copy or redundant evidence heading was added.
- Source snapshots, file hashes, canonical row locators, normalized artifacts,
  and detection-set identity participate in provenance. Publication fails
  closed for incomplete eDNA references.
- PR3 verification: 524 backend tests passed, 6 service-gated skips, 75.39%
  aggregate coverage; all 6 PostgreSQL integration tests passed separately on
  a clean no-volume pgvector/PostgreSQL 16 container. The 12 frontend tests,
  typecheck, production build, production npm audit (zero vulnerabilities),
  Ruff, `pip check`, one Alembic head, and diff checks passed. Synthetic browser
  checks verified exact detection selection, refresh, Back/Forward, both-method
  defaults, and malformed/missing destinations. Temporary preview services and
  fixture containers were torn down after verification.
- No commit, push, live ANEMONE download, production migration, GCP mutation,
  or deployment was performed. PR4 owns scientific analyses and reviewed eDNA
  cross-source expansion; PR5 owns the bounded live pilot and release.
- The implemented PR2 contract remains documented in
  [`docs/ANEMONE_PR2_PLAN.md`](docs/ANEMONE_PR2_PLAN.md). No live database
  migration, ANEMONE data load, GCP change, or deployment was performed.
- The detailed plan, fixed cross-PR decisions, open scientific decisions, and
  acceptance gates are in
  [`docs/ANEMONE_INTEGRATION_PLAN.md`](docs/ANEMONE_INTEGRATION_PLAN.md).
- No ANEMONE credential, live source file, schema migration, database row, GCP
  resource, or production setting is part of PR1. Any temporary password shared
  during discovery must be regenerated before an operator smoke test.

### Evidence Navigation Release v0.3.0 (2026-08-31)

- Citation evidence now links to validated, bookmarkable provenance, sample,
  CTD, taxa, SST, derived-analysis, and reliability destinations.
- `/data`, `/explore`, and `/provenance` restore supported scientific views and
  identifiers from URL state and fail clearly on invalid or unpublished
  destinations.
- Analysis context links restore the exact published workspace, including the
  cross-bay CTD comparison, and reliability links restore the cited check.
- Evidence, Settings, and Admin surfaces use concise academic labels and omit
  redundant product copy, helper blurbs, and duplicate context banners.
- FastAPI and frontend package metadata report `0.3.0`. Local release gates
  passed 473 backend tests with 3 skipped checks, Ruff, the frontend's 8 tests,
  typecheck and 24-route production build, `pip check`, a single Alembic head,
  and a zero-vulnerability production npm audit.
- No database schema, corpus, model, identity, job, quota, scaling, or budget
  change accompanies this release. The `v0.2.3` revision remains the immediate
  application rollback point.

### Maintenance Release v0.2.3 (2026-08-26)

- The Pipeline availability summary now counts only derived artifacts whose
  API freshness class is `recent`. Raw inputs are excluded from its denominator
  and the label is explicitly **Recent derived artifacts**.
- The frontend freshness contract is a closed TypeScript union matching the
  backend values (`recent`, `aged`, `archival`, `missing`, and `unknown`), so
  an unsupported class fails typechecking instead of silently displaying 0%.
- FastAPI and frontend package metadata report `0.2.3`. Local release gates
  passed 473 backend tests with 3 skipped checks, Ruff, 74.54% coverage, the
  frontend typecheck and 24-route production build, `pip check`, a single
  Alembic head, and a zero-vulnerability production npm audit.
- The exact source SHA, Cloud Build, Cloud Run revision, and bounded canary
  executions are preserved in the GitHub `production` deployment and release.
  Revision `ocean-platform-00007-2dp` remains the application rollback point.

### OCEAN Platform Cutover (2026-08-25)

- Release `v0.2.2` completed phase 8: Artifact Registry `ocean-platform`,
  service accounts `ocean-platform` and `ocean-jobs`, Cloud SQL
  `ocean-postgres` / `ocean_platform`, `ocean-*` jobs and secrets, and bucket
  `data-infra-infobio-ocean-data` now form the live data plane.
- Cloud Build `da3045fd-e774-47a0-85a7-df1bd831a7d2` passed the full test and
  image pipeline. Revision `ocean-platform-00006-noz` initially served 100%
  traffic before the post-release remediation revision recorded below.
- The database migration preserved all 16 tables and audited row counts. Job
  executions `ocean-migrate-glml5`, `ocean-pipeline-q8x99`,
  `ocean-embedding-trv4b`, and `ocean-evaluation-skf6f` passed their bounded
  validation gates.
- The former `onagawa-source-chat` service is private. `onagawa-postgres` is
  stopped with deletion protection; restarting it and explicitly restoring
  service access remains the rollback path during the retention window.
- The application logo and favicon assets were removed. All five checked-in
  product screenshots are logo-free.
- Post-release Cloud Build `9764872c-41b4-45ec-ac58-d77c7d9dac86` deployed
  revision `ocean-platform-00007-2dp` and the same API image to all four active
  OCEAN jobs. Their bounded canaries passed, explicit model allowlists and the
  90-day retention setting are deployed, and the four orphan `onagawa-*` job
  definitions were removed.

The preceding `v0.2.0` cutover established the canonical product identity:

- Release `v0.2.0` establishes **OCEAN Platform** — Ocean Coastal Ecosystem
  Archive Nexus (OCEAN) — as the canonical product and repository identity.
- Cloud Build `d2b38c01-526a-4827-bd9d-2d05948e2350` passed the full backend,
  frontend, and image pipeline. Targeted frontend build
  `2754b49a-6963-4efb-91c2-bdeb3d4a97c2` produced the public-asset fix.
- Cloud Run service `ocean-platform`, revision `ocean-platform-00002-rhc`,
  received 100% of its traffic at the OCEAN URL during the parallel-service
  transition. Phase 8 has since replaced its legacy data-plane references.
- At the `v0.2.0` cutover, Google OIDC temporarily retained the former
  origin/callback for rollback and added the OCEAN origin/callback. The former
  entries were removed before `v0.2.2`; only the OCEAN origin/callback is now
  active. Administrator sign-in and every user/admin route were validated
  against the new service.
- The primary navigation now has one **Admin** entry. `/admin` contains
  Overview, Users, Feedback, Pipeline, Database, System, and Debug sections.
  `/pipeline`, `/database`, `/system`, and `/debug` are compatibility
  redirects into the Admin workspace.
- The deployed Evaluation UI reads saved runs, reports, analytics, questions,
  standard/ablation controls, and comparisons. The `v0.2.0` validation used
  historical execution `onagawa-evaluation-rw7mm`; production execution now
  uses the manual `ocean-evaluation` Cloud Run Job boundary.
- Local release validation passed 455 backend tests with 3 skipped checks,
  Ruff, frontend typecheck/build, and the Cloud Build test/build pipeline.
- No schema migration, pipeline mutation, embedding refresh, quota increase,
  scale increase, or budget increase accompanied the Admin release.

### Repository Structure Cleanup

The old root-level Streamlit files were moved into an in-repo archive:

| Old root path | New archive path | Reason |
| --- | --- | --- |
| `app.py` | `archive/legacy-streamlit/app.py` | Previous monolithic Streamlit UI; no longer active root entrypoint |
| `Containerfile` | `archive/legacy-streamlit/Containerfile` | Streamlit-specific container image |
| `docker-compose.app.yml` | `archive/legacy-streamlit/docker-compose.app.yml` | Streamlit-specific compose overlay |

The archived Streamlit app was adjusted so it can still import project modules
from the repository root when intentionally run from the archive path.

### Documentation Updated

- `README.md` now presents Next.js + FastAPI as the normal application path.
- `README.md` keeps Streamlit documentation as an archived parity reference.
- `README.md` documents linked cross-source evidence, answer trust reports,
  invite-only authorization, feedback review, production safeguards, and the
  current 450+ test suite.
- `README.md` now includes the 2026-08-25 OCEAN release status and screenshots
  captured from the authenticated Cloud Run service.
- `docs/ROADMAP.md` records the manual batch-ingestion direction and cloud UI
  migration direction, including completed citation rendering, linked evidence,
  trust report, and screenshot refresh work.
- `docs/SECURITY.md`, `docs/DEPLOYMENT.md`, and `docs/TESTING.md` define the
  authorization model, supported production topology, residual risks, and
  release verification.
- `archive/README.md` and `archive/legacy-streamlit/README.md` explain what is
  archived, how to intentionally run it, and where the active prototype docs
  live.

### Manual Pipeline Improvement

- Added `scripts/run_pipeline.py` as the safe manual batch orchestrator.
- Added pipeline preflight API support.
- Added durable pipeline manifests at `data/pipeline_runs/{run_id}/manifest.json`.
- Added run history/detail APIs for pipeline runs.
- Expanded the `/pipeline` page with preflight checks, active/background job
  status, artifact freshness, per-stage logs, run history, selected manifest
  JSON, artifact diffs, and log-tail inspection.
- Added tests for preflight command planning, reset blockers, dry-run manifest
  creation, active job discovery, artifact freshness, stage-log parsing, run
  history, and run detail retrieval.

### Milestone Readiness Hardening

- Added strict contracts for every raw tabular source plus the 1,848-file SST
  collection, including schema, identifiers, dates, duplicate detection,
  cross-file sample/run agreement, file hashes, and prior-run row-count checks.
- Corrected the `gn.consistency.tsv` column interpretation and optional Kraken
  group-header handling found by the stricter validation.
- Added source-row hashes and transactional staging-table upserts. The default
  pipeline now preserves unchanged embeddings and requires an explicit reset
  flag for full replacement.
- Added atomic custom-format PostgreSQL backups with SHA-256 sidecars, archive
  verification, row-count manifests, and isolated restore tests. Pipeline
  preflight requires a backup stage before database mutation.
- Moved production/staging rate-limit counters to PostgreSQL, switched CSP to
  enforcement, and dropped container capabilities while running application
  processes as non-root users.
- Split runtime, development, analysis, and archived-app dependencies into
  hash-verified transitive locks and added a Python 3.12 bootstrap script.
- Pinned production base images by digest, pinned the patched Auth.js beta,
  and overrode the frontend's transitive Sharp and PostCSS packages to patched
  releases. Routine npm installs do not submit dependency metadata to the
  registry audit endpoint; CI dependency review and Dependabot remain enabled.
- Browser validation found and fixed two frontend integration issues: enforced
  CSP now permits the Next.js evaluation runtime only in development, and the
  same-origin proxy guard compares state-changing requests with the effective
  browser-facing host/protocol while continuing to reject foreign or missing
  origins.
- Added an opt-in development email/password harness on `/login` for fixed
  viewer, researcher, and admin mock accounts. Passwords are supplied only as
  environment-injected scrypt hashes. It creates normal signed Auth.js/internal
  JWT sessions without database fixtures, is disabled by default, and fails
  closed if enabled in staging or production.
- Raised the aggregate coverage floor to 70% and added focused tests for
  database safety, raw validation, query orchestration, analysis, evaluation,
  and remote sensing.

### Repository Audit and Mutsu Correction

- Corrected bay code `M` to **Mutsu Bay** across active UI labels, retrieval
  naming, prompt context, preprocessing text documents, evaluation fixtures,
  README study-site documentation, and tests.
- Removed the old hardcoded `M` coordinate fallback from active retrieval and
  anchor-event generation. `M` coordinates should come from source metadata
  until a trusted Mutsu coordinate policy is added.
- Regenerated `data/serving/retrieval_documents.jsonl`,
  `data/serving/retrieval_documents.parquet`, and
  `data/canonical/anchor_events.parquet` from the corrected code.
- Reloaded the local PostgreSQL database with `python scripts/load_db.py --reset --embed`
  so the live `/database`, `/chat`, and retrieval surfaces no longer show stale
  generated bay-label text.
- Audited all active routes in the browser at `http://127.0.0.1:3002`: `/`,
  `/explore`, `/data`, `/database`, `/pipeline`, `/provenance`, `/evaluation`,
  `/chat`, `/system`, `/debug`, plus `/analysis` and `/evidence` compatibility
  redirects. No fatal render text or top-level layout overflow was found.
- Audited major internal expert views: Data observations/CTD/taxa/SST/derived
  analysis/reliability; Pipeline status/run/logs/history; Provenance
  manifest/document trace/upsert dry-run; Evaluation
  runs/analytics/questions/standard/ablation/compare.
- Active-path sweeps are clean for old or misspelled M-bay labels; remaining old
  labels are only in historical generated evaluation CSVs and archived
  Streamlit reference files.

### Provenance Manifest and Upsert Dry-Run

- Added `ingestion/lineage.py` as the traceability-first manifest layer.
- Added `scripts/build_provenance_manifest.py` for manual manifest inspection
  and optional manifest writing under `data/provenance/`.
- Added read-only `scripts/load_db.py --upsert --dry-run --limit-keys N --json` support.
- Added FastAPI endpoints:
  - `GET /provenance/manifest`
  - `GET /provenance/trace/{doc_id}`
  - `GET /provenance/upsert-dry-run`
- Added a Next.js `/provenance` page with manifest tables, document trace
  lookup, embedding treatment, raw trace payload inspection, and manual dry-run
  controls.
- Added synthetic tests for lineage construction, content-hash comparison,
  embedding-refresh planning, and provenance API contracts.

The upsert implementation now stages each corpus table, compares logical keys
and source-row hashes, and applies inserts/updates in one transaction. It
retains and reports stale keys rather than deleting them. Unchanged retrieval
documents retain their embeddings.

### Data and Analysis UI Consolidation

- Removed `Analysis` from the top-level sidebar.
- Combined source observations, CTD, taxa, SST, derived analysis, and
  reliability review under `/data`.
- Replaced `/analysis` with a compatibility redirect to `/data?view=analysis`.
- Extracted the former analysis page into `frontend/components/AnalysisWorkbench.tsx`
  so derived-analysis and reliability views can be embedded without duplicating
  chart/table logic.

### Explore and Evidence UI Consolidation

- Removed `Evidence` from the top-level sidebar.
- Combined normalized table exploration, time-series review, sample detail, and
  evidence retrieval under `/explore`.
- Replaced `/evidence` with a compatibility redirect to `/explore?view=evidence`.
- Extracted the former evidence page into `frontend/components/EvidenceWorkbench.tsx`
  so the retrieval diagnostics can live inside the corpus workbench without a
  second page implementation.

### Trustworthy Multi-Source Answering and Citation Audit

- Added linked evidence expansion for retrieval/chat requests through
  `expand_evidence` and `max_linked_sources`.
- Retrieval now returns primary `sources`, separate `linked_sources`, and
  diagnostics for expected, retrieved, and missing source families.
- Chat prompts include a linked cross-source evidence section when corroborating
  anchor-event neighbors are available.
- Added deterministic answer auditing in `orchestration/answer_audit.py`.
- Chat responses can include `answer_audit` with trust level, trust score,
  citation resolution records, invalid citation warnings, source-family
  requirements, linked-source use, and analysis/reliability context use.
- Citation requirements are context-aware: cited `[analysis_*]` documents can
  satisfy trend/correlation/diversity requirements, cited `[reliability_*]`
  documents can satisfy validation/trust requirements, and raw measurement
  questions still require raw source citations.
- Added Chat settings for linked evidence expansion and the trust-report toggle.
- Added a clean expert-facing Trust Report panel with summary metrics, warning
  table, requirement table, and citation-resolution table.
- Added `frontend/components/MarkdownAnswer.tsx` so answer text renders
  headings, lists, code blocks, tables, links, emphasis, and citation chips
  without using unsafe HTML injection.

### Invite-Only Authorization and Feedback

- Added Auth.js OpenID Connect login with verified-email invitation acceptance;
  there is no public registration or local password store.
- Recorded the cloud authentication decision: use a managed OIDC provider that
  presents hosted email/password sign-in and owns password recovery, MFA,
  lockout, and abuse controls. The application shows one neutral production
  **Sign in** action and never stores production passwords. Local mock mode
  hides the provider action completely.
- Added viewer, researcher, and admin roles. Research, commercial, and internal
  are account-type metadata, not permission-bearing roles.
- Added default-deny FastAPI route policies, current-role/status resolution on
  every request, immediate suspension, and self-demotion/self-suspension
  protection for administrators.
- Added persistent chat interactions and thumbs-up/down feedback with reason
  codes and optional comments.
- Added administrator user/invitation management plus a filtered feedback
  review and CSV export surface. Security-sensitive changes write audit events.
- Added fail-closed production configuration, bounded short-lived internal
  tokens, request/body limits, read-only SQL defense in depth, response security
  headers, and per-user production rate limits.
- Added Alembic-backed metadata integration testing, coverage enforcement,
  pinned CI actions, Dependabot configuration, a production Compose topology,
  and security/deployment/testing runbooks.

### Prototype Screenshot Refresh

- Replaced the prior local captures with authenticated OCEAN Platform Cloud Run
  screenshots from 2026-08-25.
- Current screenshot files under `docs/screenshots/`:
  `prototype_overview.png`, `prototype_explore_evidence.png`,
  `prototype_data_analysis.png`, `prototype_provenance.png`, and
  `prototype_chat_trust_report.png`.
- The Chat screenshot was captured after a real Vertex AI query and shows the
  Answer Trust Report with context-aware citation requirements.

### Active Stack Clarified

The active container stack is:

- `Containerfile.api` for FastAPI
- `frontend/Containerfile` for Next.js
- `compose.yml` for PostgreSQL/pgvector
- `deploy/compose/app.yml` for FastAPI + Next.js
- `deploy/compose/ollama.yml` for optional containerized Ollama

The root no longer contains a Streamlit entrypoint.

### Local Artifacts Cleaned

Ignored local clutter was removed during the final repo health check:

- `.DS_Store`
- `.pytest_cache/`
- `__pycache__/`
- `frontend/tsconfig.tsbuildinfo`

The ignored `onagawa_sst_subset/` directory was intentionally left alone
because it is the local SST raw-data source needed for full regeneration.

---

## 3. Current Technology Stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js, React, TypeScript |
| API | FastAPI, Pydantic schemas |
| RAG orchestration | Python modules in `orchestration/` and `retrieval/` |
| Database | PostgreSQL 16 + pgvector |
| Search | pgvector cosine similarity + PostgreSQL full-text search + RRF |
| LLM | Vertex AI `gemini-3.6-flash` on GCP; Ollama `qwen2.5:14b-instruct` locally |
| Embeddings | Vertex AI `gemini-embedding-001` on GCP; Ollama `nomic-embed-text` locally, both 768 dimensions |
| Data processing | pandas, Parquet, xarray, netCDF4, SciPy |
| Containers | Cloud Run multi-container service and Jobs on GCP; Podman/Docker Compose locally |
| Tests | pytest backend/API/unit tests; Next.js typecheck/build |

---

## 4. Directory Map

```text
ocean-platform/
├── api/                              # FastAPI service and endpoint logic
├── archive/
│   └── legacy-streamlit/             # Archived Streamlit app and overlay
├── data/                             # Tracked clean-clone artifacts + ignored generated outputs
├── db/                               # SQLAlchemy models, connection helpers, vector store
├── docs/                             # Security, deployment, testing, roadmap, screenshots
├── evaluation/                       # Benchmark, questions, metrics, reports, statistics
├── frontend/                         # Next.js academic UI
├── ingestion/                        # File inventory, provenance registry, lineage manifests
├── orchestration/                    # Prompt construction and RAG context injection
├── preprocessing/                    # CTD, metagenome, SST, pre-analysis, reliability
├── retrieval/                        # Document builder, hybrid retriever, local fallback
├── schema/                           # Anchor-event construction
├── scripts/                          # Manual batch pipeline and evaluation CLIs
├── tests/                            # 450+ unit, API, and integration tests
├── config.py                         # Paths, model defaults, thresholds
├── Containerfile.api                 # FastAPI container
├── compose.yml                        # Default local PostgreSQL/pgvector
├── deploy/                            # Compose, environment, and GCP configuration
├── requirements/                      # Python inputs and hash-verified locks
├── README.md                         # Public project guide
└── .env.example                      # Local environment template
```

### Archive Policy

Keep active code in its module directories, dependency sets in `requirements/`,
and deployment configuration in `deploy/`. Move only retired material that is
still useful as reference into `archive/`.

Current archive contents:

- `archive/legacy-streamlit/app.py`
- `archive/legacy-streamlit/Containerfile`
- `archive/legacy-streamlit/docker-compose.app.yml`
- `archive/legacy-streamlit/README.md`

Do not archive generated caches. Delete them locally instead.

---

## 5. Current Application Surface

The current UI is a practical academic interface. Avoid marketing-style pages,
large copy blocks, decorative cards, or flashy layouts. The user persona is an
expert researcher/operator who benefits from dense controls, transparent state,
and reproducible run information.

| Route | Purpose |
| --- | --- |
| `/` | Overview, corpus summary, tab feature map, backend signals |
| `/explore` | Corpus workbench for tables, filters, summaries, charts, sample detail, and evidence retrieval |
| `/data` | Combined domain workbench for observations, CTD, taxa, SST, derived analysis, and reliability |
| `/analysis` | Compatibility redirect to `/data?view=analysis` |
| `/provenance` | Traceability manifest, document lineage, embedding treatment, upsert dry-run |
| `/evaluation` | First-class evaluation suite with background jobs and detailed controls |
| `/chat` | Citation-grounded RAG chat with expert retrieval/model knobs, linked evidence, Markdown answer rendering, and answer trust reports |
| `/settings` | Per-user language, formatting, and interface preferences |
| `/login` | Neutral Google OIDC entry point for invited accounts |
| `/evidence` | Compatibility redirect to `/explore?view=evidence` |
| `/admin` | Admin-only workspace overview and subnavigation |
| `/admin/users` | Invitations, roles, account types, and suspension controls |
| `/admin/feedback` | Feedback review, evidence detail, and CSV export |
| `/admin/pipeline` | Pipeline preflight, state, runs, logs, and artifact freshness |
| `/admin/database` | Schema inspection and structured read-only table tools |
| `/admin/system` | API, database, model, artifact, and runtime status |
| `/admin/debug` | Debug payloads and low-level diagnostics |
| `/pipeline`, `/database`, `/system`, `/debug` | Compatibility redirects into `/admin/*` |

Visual direction:

- Default white backgrounds
- Academic, practical, compact layouts
- Baby-blue accents:
  - `#56B4E9` for rules, focus, outgoing icons
  - `#dceff8` for quiet dividers
  - `#f3fbff` for code/debug backgrounds
  - `#247fae` for high-contrast blue text
- Expert controls are acceptable when clearly grouped and labeled
- Hover help is preferable to visible explanatory copy for specialized knobs
- Keep visible copy academic, direct, and minimal. Use scientific labels,
  identifiers, actions, status, and errors only. Do not add marketing copy,
  eyebrows, taglines, prose subheaders, helper blurbs, or duplicate context
  banners when the page title, selected control, table, or URL already conveys
  the same state.

---

## 6. FastAPI Surface

The main backend file is `api/main.py`. Key endpoint groups:

| Group | Endpoints |
| --- | --- |
| Health/statistics | `GET /health`, `GET /stats`, `GET /models` |
| Pipeline | `GET /pipeline/status`, `POST /pipeline/preflight`, `POST /pipeline/jobs`, `GET /pipeline/jobs/{job_id}`, `GET /pipeline/jobs/{job_id}/log`, `POST /pipeline/jobs/{job_id}/cancel`, `GET /pipeline/runs`, `GET /pipeline/runs/{run_id}` |
| Provenance | `GET /provenance/manifest`, `GET /provenance/trace/{doc_id}`, `GET /provenance/upsert-dry-run` |
| Debug | `GET /debug` |
| Data page | `GET /data/catalog`, `GET /data/ctd-profile/{sample_id}`, `GET /data/taxa/{sample_id}`, `GET /data/sst` |
| Evaluation | `GET /evaluation/catalog`, `GET /evaluation/preflight`, `POST /evaluation/runs/standard`, `POST /evaluation/runs/ablation`, `GET /evaluation/jobs/{job_id}`, `POST /evaluation/jobs/{job_id}/cancel`, `GET /evaluation/runs`, `GET /evaluation/runs/{run_id}`, `GET /evaluation/runs/{run_id}/report`, `POST /evaluation/compare` |
| Analysis | `GET /analysis` |
| Database | `GET /database/schema`, `GET /database/table` |
| Explore | `GET /explore/catalog`, `GET /explore/table`, `GET /explore/summary`, `GET /explore/timeseries`, `GET /explore/sample/{sample_id}` |
| Evidence/chat | `GET /documents`, `POST /retrieve`, `POST /chat` |

`POST /retrieve` and `POST /chat` accept `expand_evidence` and
`max_linked_sources`. `POST /chat` also accepts `run_answer_audit` and returns
`linked_sources`, `retrieval_diagnostics`, and optional `answer_audit`.

Database access is intentionally GET-only through validated schema and table
inspection endpoints. Free-form SQL execution and its permission were removed;
add future analytical reports as server-defined, structured endpoints.

---

## 7. Data Lifecycle

The system currently supports manual batch ingestion and rebuilds. It does not
yet support automatic watching, scheduled ingestion, or incremental cloud data
sync.

### Current Manual Lifecycle

1. **New source files arrive**
   - CTD TSV files go under `data/raw/ctd/`
   - Metagenome TSV/TXT files go under `data/raw/meta/`
   - SST NetCDF source files are local/ignored under `onagawa_sst_subset/`

2. **Ingestion and normalization**
   - Run `python scripts/ingest.py`
   - Provenance is recorded with SHA-256 hashes
   - Normalized parquet artifacts are written under `data/normalized/`

3. **Anchor events and retrieval documents**
   - Run `python scripts/build_retrieval_docs.py`
   - Cross-source links and anchor events are generated under `data/canonical/`
   - Retrieval documents are emitted under `data/serving/`

4. **Pre-analysis**
   - Run `python scripts/run_pre_analysis.py`
   - Ecological analysis parquet outputs and `analysis_documents.jsonl` are
     generated under `data/analysis/`

5. **Reliability ensurance**
   - Run `python scripts/run_reliability.py`
   - Cross-source validation outputs and `reliability_documents.jsonl` are
     generated under `data/reliability/`

6. **Database backup, load, and embeddings**
   - Run `python scripts/database_backup.py create --restore-test`
   - Run `python scripts/load_db.py --upsert --embed`
   - Corpus inserts/updates commit transactionally; stale rows are reported
   - Only new or changed retrieval documents require fresh embeddings

7. **Traceability and dry-run planning**
   - Run `python scripts/build_provenance_manifest.py --write --run-id <run_id>`
   - Optionally run `python scripts/load_db.py --upsert --dry-run --limit-keys 25 --json`
   - Inspect `/provenance` for source hashes, artifact versions, document
     trace paths, embedding treatment, and upsert planning

8. **Application use**
   - Next.js calls FastAPI
   - FastAPI uses PostgreSQL when available
   - Retrieval falls back to local JSONL/BM25/numpy when PostgreSQL is down

### Manual Batch Runner

The data workflow now has a single manual batch command. It is still not
automatic ingestion: no watcher, scheduler, queue, or cloud sync starts this
without an explicit operator action.

```bash
python scripts/run_pipeline.py --validate-only
python scripts/run_pipeline.py --preflight-only --stages full
python scripts/run_pipeline.py --execute --tag 2026-07-manual-refresh --embed
```

`scripts/run_pipeline.py` is dry-run by default. Real execution requires
`--execute`; the normal path creates a verified backup before transactional
upsert. A destructive full replacement additionally requires `--reset-db`.
Runs write `progress.json`, `run.log`, `run_meta.json`, and `manifest.json`
under `data/pipeline_runs/{run_id}/`.

The `/pipeline` page can start background jobs, run preflight checks, inspect
active/background job status, show per-stage logs, list run history, inspect
manifests, report artifact freshness, and display artifact diffs.

### Provenance and Incremental-Load Planning

The provenance and mutation plan remain inspectable before execution:

```bash
python scripts/build_provenance_manifest.py --limit-documents 500
python scripts/build_provenance_manifest.py --write --run-id 2026-07-lineage-check
python scripts/load_db.py --upsert --dry-run --limit-keys 25 --json
```

The manifest currently records:

- Raw file existence, SHA-256, collection fingerprints, registry counts, and
  latest processing run where available
- Derived artifact paths, producer stage, table mapping, key columns, row
  counts, schema hashes, and file hashes
- Retrieval document IDs, source type, source keys, content hashes, metadata
  hashes, and inferred source artifacts/files
- Embedding treatment for the manifest document window, including model,
  dimension, database status, and refresh candidates

The upsert dry-run compares current artifacts against PostgreSQL logical keys
and reports planned inserts, updates, stale existing keys, and embedding
refresh candidates. The mutating mode uses the same contract inside one
transaction; stale rows are not automatically deleted.

---

## 8. Container and Runtime Modes

### Database Only

```bash
podman compose up -d
```

Starts PostgreSQL/pgvector on host port `5433`.

### Recommended Local App Stack

```bash
podman compose -f compose.yml -f deploy/compose/app.yml up -d --build
```

Starts PostgreSQL, FastAPI, and Next.js. FastAPI connects to Ollama on the host
through `http://host.containers.internal:11434`.

### Optional Containerized Ollama

```bash
OLLAMA_BASE_URL=http://ollama:11434 podman compose -f compose.yml -f deploy/compose/app.yml -f deploy/compose/ollama.yml up -d --build
```

Use this only when the LLM runtime should live inside compose too. On macOS,
host Ollama is usually faster and simpler than Ollama inside the Podman VM.

### Archived Streamlit Parity Check

```bash
podman compose -f compose.yml -f archive/legacy-streamlit/docker-compose.app.yml up -d --build
```

Use this only to compare historical Streamlit behavior with the Next.js UI.

---

## 9. Testing and Verification

Current ANEMONE PR5 local verification is recorded in section 2 above and
[`docs/TESTING.md`](docs/TESTING.md). The following table records the historical
`v0.3.0` release validation; its live checks have not been repeated for PR5:

| Check | Result |
| --- | --- |
| `pytest` | 473 passed, 3 skipped in the `v0.3.0` release validation; 74.54% aggregate coverage |
| Coverage boundary | 74.54% aggregate; required floor is 70% |
| PostgreSQL metadata integration | Passed against migrated local PostgreSQL/pgvector |
| Security-boundary Ruff check | Passed |
| `npm run typecheck` | Passed |
| Production-configured `npm run build` | Passed |
| Production API and frontend container builds | Passed; non-root runtime and pinned frontend dependency versions confirmed |
| Browser route smoke test | Passed all 14 user/admin routes on the authenticated OCEAN Cloud Run service with no access-denied or application-error states |
| Browser interaction smoke test | Explore search, all Data views, database probe, pipeline preflight, provenance dry-run, evaluation views, and citation-grounded chat passed |
| Production frontend container browser test | Passed overview data load and state-changing retrieval probe; strict CSP and 403 cross-origin rejection confirmed |
| OIDC browser integration | Passed authorization-code flow with PKCE/state/nonce, invitation consumption, viewer/researcher/admin sessions, role navigation/direct-route gates, sign-out, audit records, and immediate suspension using an isolated local issuer |
| Development mock-login browser test | Passed viewer/researcher/admin signed logins, invalid-password handling, permission-aware navigation, direct-route denial, admin-only pages, sign-out, and non-persistence checks |
| Production Compose expansion | Passed |
| Strict raw-source validation | Passed for all 12 tabular sources and 1,848 SST files |
| Full default pipeline | Passed all 7 stages, including verified backup and idempotent upsert |
| `git diff --check` | Passed |

Current test modules:

| Area | Files |
| --- | --- |
| Authorization, feedback, and security | `test_auth.py`, `test_security_config.py`, `test_rate_limit.py`, `test_chat_feedback.py`, `test_admin_feedback.py` |
| API and UI backend contracts | `test_api_explore.py`, `test_api_pipeline.py`, `test_api_provenance.py`, `test_api_evaluation.py`, `test_api_retrieve.py`, `test_api_schemas.py` |
| Core data/provenance | `test_common.py`, `test_provenance.py`, `test_lineage.py`, `test_anchor_events.py` |
| Retrieval/prompting/audit | `test_local_retriever.py`, `test_prompt_builder.py`, `test_answer_audit.py` |
| Evaluation/reliability | `test_reliability.py`, `test_evaluation.py`, `test_questions.py`, `test_quality_metrics.py`, `test_report.py`, `test_statistical_analysis.py` |
| PostgreSQL metadata integration | `integration/test_app_metadata_postgres.py` |

Use the CI-equivalent commands in `docs/TESTING.md` before larger commits.
At minimum:

```bash
pytest
cd frontend
npm run typecheck
npm run build
```

For docs-only commits, at minimum run:

```bash
git diff --check
```

---

## 10. Key Files To Understand First

| Priority | File | Why |
| --- | --- | --- |
| 1 | `config.py` | Central paths, model defaults, and fail-closed API configuration |
| 2 | `api/auth.py` | Identity resolution, permission matrix, default-deny authorization |
| 3 | `frontend/auth.ts` | OIDC provider, invite acceptance, session enrichment |
| 4 | `api/main.py` | Active backend surface and middleware registration |
| 5 | `api/schemas.py` | Frontend/backend contracts and bounded payloads |
| 6 | `frontend/app/*/page.tsx` | Active UI routes |
| 7 | `frontend/components/AppShell.tsx` | Permission-aware navigation and page shell |
| 8 | `orchestration/unified.py` | Prompt builder, retrieval dispatch, linked evidence, context injection |
| 9 | `orchestration/answer_audit.py` | Citation resolution, trust scoring, and context-aware requirements |
| 10 | `retrieval/hybrid_retriever.py` | PostgreSQL vector + FTS retrieval |
| 11 | `retrieval/local_retriever.py` | Local fallback retrieval without PostgreSQL |
| 12 | `docs/SECURITY.md` | Authorization matrix, trust boundaries, limitations, release checklist |

---

## 11. What Is Complete

| Area | Status |
| --- | --- |
| Core data pipeline | CTD, metagenome, SST normalization and retrieval-document build path exist |
| Provenance | Strict raw validation, SHA-256 file registry, row hashes, traceability manifest, document trace API/UI, and upsert dry-run exist |
| Anchor/cross-source linking | Anchor events and cross-source links exist |
| Retrieval | PostgreSQL hybrid retrieval and local fallback exist |
| Trustworthy multi-source answering | Primary retrieval, linked cross-source evidence expansion, source-family diagnostics, and chat/evidence controls exist |
| Prompting | Provenance-aware citations plus linked evidence and analysis/reliability injection exist |
| Answer trust report | Deterministic citation audit, context-aware citation requirements, warnings, exportable tables, and Chat UI toggle exist |
| Evaluation | Standard/background runs, ablation controls, run browser, reports, comparison |
| Pipeline UI | Manual batch job controls, preflight checks, active/background job status, artifact freshness, per-stage logs, run history, manifests, and artifact diffs exist |
| Database UI | Schema, table browsing, and read-only query surface exist |
| Data exploration | Combined Explore corpus workbench plus combined Data domain workbench exist for expert browsing |
| System/debug | Status and debug surfaces exist |
| Invite-only identity | OIDC, invitations, viewer/researcher/admin roles, suspension, audit events, and a production-forbidden development mock-login harness exist |
| User feedback | Persisted chat interactions, feedback revisions, admin review/filter/export exist |
| Security boundary | Fail-closed production config, default-deny authorization, bounded tokens/input, rate limits, headers, and SQL defense in depth exist |
| CI and integration | 70% coverage enforcement, security lint, pinned actions, hash-verified dependency locks, and PostgreSQL metadata/operations integration exist |
| Containerization | Database-only, Next/FastAPI, optional Ollama, production private-service, and archived Streamlit modes exist |
| Archive | Legacy Streamlit root files are preserved under `archive/legacy-streamlit/` |

---

## 12. Known Limitations

| Limitation | Notes |
| --- | --- |
| Ingestion is manual | No automatic file watcher, scheduler, queue, or cloud object-store sync yet |
| Backup retention/PITR | The live Cloud SQL instance keeps seven backups and seven days of PITR; continue periodic logical-export and restore drills |
| Stale-row deletion | Transactional upsert reports but does not delete database keys missing from the incoming artifacts |
| Production operations remain operator-managed | Cloud Run/Cloud SQL are live; secret rotation, retention enforcement, posted-cost review, alerting, and incident drills remain operator responsibilities |
| Ollama is local-only | GCP uses native Vertex AI; host/container Ollama remains an optional local-development runtime |
| Streamlit is archived | Do not add new active features to `archive/legacy-streamlit/app.py` |
| Screenshots are point-in-time | `docs/screenshots/` contains authenticated OCEAN Cloud Run captures from 2026-08-25 |
| Trust report is deterministic | The current audit checks supplied evidence and citations; it is not an LLM-as-judge semantic faithfulness scorer |
| Integration scope is focused | PostgreSQL migrations, metadata, shared rate limiting, backup/restore, and repeated upserts are integration-tested; most RAG and scientific tests remain synthetic |
| Auth.js beta | Auth.js 5 is exact-pinned at beta.32; regression-test any upgrade |
| Managed OIDC deployment | Google OIDC is live and verified for the administrator and approved researcher; broader identity-provider recovery/MFA policy remains external to the application |
| Evaluation execution | Serving instances deliberately reject in-process jobs; the UI start controls are not yet connected to the external Cloud Run evaluation job |
| Security operations require repository settings | CodeQL and dependency automation exist; branch/environment protections, retention enforcement, cost review, and alerting still require operator review |
| Historical milestone plan | `docs/PRE_MILESTONE_VALIDATION_PLAN.md` records the completed local gate; current cloud release evidence is in the Phase 7 and GCP runbooks |

---

## 13. Recommended Next Work Order

### 1. Review the local PR1–PR5 implementation

The worktree contains PR1 acquisition, PR2 canonical ingestion, PR3 serving,
and PR4 analyses. Preserve all existing changes. The earlier PR3 review fixes
are implemented; do not repeat that obsolete work order. The three later
findings in [`docs/ANEMONE_PR5_PLAN.md`](docs/ANEMONE_PR5_PLAN.md) are also fixed:
complete registered-manifest verification, historical citation retention, and
cohort/method filtering before ranking, with permanent regression tests.

Review/commit the accumulated changes by logical responsibility when requested.
Keep the scope and credential boundaries in
[`docs/ANEMONE_INTEGRATION_PLAN.md`](docs/ANEMONE_INTEGRATION_PLAN.md):

- rerun the targeted acquisition/normalization suites, disposable PostgreSQL
  integration test, and full backend gate;
- inspect the raw and normalized manifests, migration, provider-scoped merge,
  lineage output, and negative security tests;
- confirm the diff contains no credential or live ANEMONE source data;
- use a regenerated credential only for an optional one-sample inventory smoke
  test outside CI.

Do not add retrieval behavior, frontend routes, analyses, GCP jobs, or live
data to the PR1/PR2 boundary.

### 2. Validate the real PR5 pilot and release

Use [`docs/ANEMONE_PR5_PLAN.md`](docs/ANEMONE_PR5_PLAN.md) as the current
rollout sequence. Local code and audit repairs are implemented; next:

1. review the object-store/job implementation and validate it on approved GCP resources;
2. approve the pilot, provider conditions, credentials and resource budgets;
3. validate a real bounded import and research/chat outputs in isolation;
4. rehearse backup, migrations and rollback, then perform authorized GCP
   deployment, verification, and `v0.4.0` release.

PR4's biodiversity/control/method analysis and typed environmental adapter
already exist. Source-specific environmental extraction/profile review remains
a pilot task; do not enable a live linkage without qualified observations.

Preserve the cross-PR decisions in the integration plan. Do not call read
counts organism abundance, collapse assignment methods, or link nationwide
ANEMONE observations to regional SST by date alone.

Use [`docs/ANEMONE_PR3_PLAN.md`](docs/ANEMONE_PR3_PLAN.md) as the PR3
implementation record and review checklist. In particular, build the searchable eDNA
corpus from all active canonical database rows rather than only the latest
normalized-bundle pointer, keep both assignment methods visible when no filter
is selected, exclude inactive documents everywhere, and keep UI labels direct
and minimal.

The implemented PR2 specification is
[`docs/ANEMONE_PR2_PLAN.md`](docs/ANEMONE_PR2_PLAN.md). Its key repository-level
decision is a dedicated, provider-scoped eDNA merge: stable current records are
updated, missing records become inactive, and no scientific or provenance row
is deleted. This avoids retaining removed detections as current evidence while
preserving immutable PR1 snapshots and the existing global no-stale-delete
policy.

### 3. Scheduled-Update Operationalization

Before handing scheduled updates to operators:

- Choose encrypted off-host backup storage and retention
- Decide whether and when stale database keys may be deleted
- Record recovery time and recovery point objectives
- Add deployment-specific artifact snapshots and log retention

### 4. Evaluation Suite Hardening

Continue treating evaluation as first-class:

- Connect the Standard/Ablation start controls to `ocean-evaluation` through
  a least-privilege, bounded Cloud Run Jobs execution bridge
- Calibrate the existing opt-in LLM-as-judge scoring against a reviewed
  benchmark and separate judge model
- Review retention and access rules for judge prompts, scores, and rationale
- Add a direct Markdown report download alongside the existing CSV exports
- Persist an approved baseline designation and enforce reviewed regression
  thresholds in release gates
- Expand and calibrate the existing latency, citation, quality, and
  distribution analytics for multi-run release decisions

### 5. Production Operations and Security Follow-Through

The bounded GCP prototype and single-host alternative both exist. Before a
wider cohort or multiple workers:

- Enable protected CI, Dependabot security updates, CodeQL, and secret scanning
- Complete the manual release checklist in `docs/SECURITY.md`
- Keep FastAPI and Cloud SQL private behind the Cloud Run frontend/sidecar
  boundary; retain TLS reverse-proxy guidance for standalone Compose only
- Export verified PostgreSQL backups and important artifacts to encrypted
  off-host storage
- Decide artifact storage: local volume, NAS, S3-compatible object store, or
  managed bucket
- Add deployment health checks, log retention, and incident contacts
- Add gateway-level volumetric limits before internet-facing horizontal scaling

### 6. Database and SQL Improvements

- Expand PostgreSQL integration coverage beyond metadata/invitation flows
- Keep Alembic migrations additive and rollback-reviewed
- Extend the provenance manifest with embedding run IDs
- Define an opt-in, policy-backed stale-row deletion workflow
- Continue tightening read-only SQL validation and identifier quoting

### 7. UI Parity and Expert UX

Use `archive/legacy-streamlit/app.py` only as parity reference. Implement all
new work in Next.js/FastAPI.

Potential parity checks:

- Confirm all old Streamlit data views have Next.js equivalents
- Add compact export/download controls for tables and evaluation reports
- Add richer pipeline freshness and data lineage indicators

---

## 14. Operational Gotchas

1. PostgreSQL uses host port `5433`, not default `5432`.
2. `DATABASE_URL` differs inside compose vs on the host.
3. `OLLAMA_BASE_URL` is usually `http://localhost:11434` on host and
   `http://host.containers.internal:11434` from app containers.
4. `deploy/compose/app.yml` does not start Ollama unless combined with
   `deploy/compose/ollama.yml`.
5. `onagawa_sst_subset/` is ignored but needed for full SST regeneration.
6. `data/` includes tracked clean-clone artifacts, while many regenerated
   outputs are ignored by `.gitignore`.
7. Analysis and reliability JSONL files are prompt-injection bridges. If they
   are missing, those contexts silently become empty.
8. Evaluation temperature defaults to deterministic behavior. Raising it can
   make run comparisons noisy.
9. The local retriever fallback keeps the app useful without PostgreSQL, but it
   is not equivalent to pgvector search.
10. Archived Streamlit files should not be edited for new product behavior.

---

## 15. Commit Readiness Checklist

Before committing larger code changes:

```bash
git status --short
git diff --check
pytest
cd frontend
npm run typecheck
npm run build
```

Before committing docs-only changes:

```bash
git status --short
git diff --check
```

Ignored local artifacts that can be deleted, not archived:

- `.DS_Store`
- `.pytest_cache/`
- `__pycache__/`
- `frontend/tsconfig.tsbuildinfo`

Ignored local artifacts that may be intentionally kept:

- `onagawa_sst_subset/`
- optional raw satellite staging directories
