# Testing and CI

## Current release evidence

For OCEAN Platform release `v0.3.0`, the local release gate passed 473 backend
tests with 3 skipped checks, Ruff, 8 frontend navigation tests, the frontend
typecheck and 24-route production build, `pip check`, a single Alembic head,
and a production npm audit with zero vulnerabilities. The immutable Cloud
Build, deployed revision, and production checks are recorded in the GitHub
release.

For OCEAN Platform release `v0.2.3`, the local release gate passed 473 backend
tests with 3 skipped checks and 74.54% aggregate coverage, Ruff, the frontend
typecheck and 24-route production build, `pip check`, a single Alembic head,
and a production npm audit with zero vulnerabilities. The immutable Cloud
Build, deployed revision, bounded job canaries, and authenticated production
checks are recorded in the GitHub `production` deployment for the release.

For OCEAN Platform release `v0.2.2`, the local backend suite passed 471 tests
with 3 skipped checks; one GCS snapshot test requires the optional local
`google-cloud-storage` package. Ruff, the frontend typecheck, the 24-route
production Next.js build, and full Cloud Build
`da3045fd-e774-47a0-85a7-df1bd831a7d2` passed. The imported Cloud SQL database
reported all 16 required tables with pgvector enabled and every audited row
count matched the source. Public-boundary checks, Google OIDC, all 14
authenticated user/admin routes, a live Vertex AI trust-report query, and the
bounded migrate, pipeline, embedding, and one-question evaluation jobs also
passed. CI runs for pushes to `main` and `gcp-dev` and for pull requests
targeting `main`/`master`.

This is a point-in-time release record, not a substitute for rerunning the
commands below after changes.

Post-release remediation validation on 2026-08-26 JST passed 473 backend
tests with 3 skipped checks, Ruff, frontend typecheck/build, zero production
npm vulnerabilities, and full Cloud Build
`9764872c-41b4-45ec-ac58-d77c7d9dac86`. Cloud Run executions
`ocean-migrate-744jh`, `ocean-pipeline-q8ktm`, `ocean-embedding-g4qvz`, and
`ocean-evaluation-rpkct` completed successfully on that image.

## Local Verification

### v0.4.0 release candidate — 2026-09-03

- Backend after the PR security fix: 638 passed, 9 PostgreSQL-gated skips,
  77.11% coverage; Ruff and
  dependency consistency passed.
- Nine additional local-artifact cases cover unsafe keys, resolved root
  containment, sibling-prefix confusion and file/directory symlinks. The
  28-test artifact/API/audit subset passed. The CodeQL finding is corrected in
  code, not suppressed; require the updated PR check to pass before deployment.
- Frontend: all 14 navigation tests, typecheck and 24-route production build
  passed; production npm audit reported zero vulnerabilities.
- API/frontend version metadata is `0.4.0`. Scientific classification behavior
  is unchanged: unknown remains excluded from environmental-only analyses.
- Classification workflow completion and real researcher acceptance are
  explicitly deferred to the [next patch](ANEMONE_NEXT_PATCH.md). They must
  not be reported as passed release checks.
- GitHub CI, cloud backup/migration and live deployment evidence must be
  verified separately and recorded in the release record before publication.

### ANEMONE non-target contract and draft proposal — 2026-09-03

- 629 backend tests passed, 9 PostgreSQL-gated skips, 77.08% CI-boundary
  coverage. All 72 focused acquisition/normalization/review/job tests, Ruff,
  diff checks and the unchanged single Alembic head `20260903_0008` passed.
  No database schema or frontend files changed in this follow-up.
- Nine new regression cases cover either/both optional non-target TSVs at
  sample/run scope, inventory limits, no payload GETs, no non-target detections,
  unchanged required target files and scientific IDs, exact approved contract
  hashes, historical normalization/template replay and unknown-hash rejection.
- The retained real pilot was checked read-only: all five proposal evidence
  rows match the source, review parsing and normalization reject the draft,
  six raw snapshot files remain byte-identical, and 70 detections remain with
  unknown classification and unchanged unreviewed v2 normalization identity.
- The API image copies the archived contract into its build context; the
  archive is not excluded by `.dockerignore`. No new image was built, source
  downloaded, canonical sample changed or paid cloud operation performed.
  See the [draft proposal](ANEMONE_PILOT_CLASSIFICATION_PROPOSAL.md).

### ANEMONE classification review — 2026-09-03

- 620 backend tests passed, 9 PostgreSQL-gated skips, 77.08% CI-boundary
  coverage; Ruff, diff checks and the single Alembic head passed.
- All 9 PostgreSQL integration checks passed in CI order on a fresh disposable
  PG16/pgvector database. Migration from `20260902_0007` to `20260903_0008`,
  review import/replay, unchanged source metadata/detections, API review detail,
  explicit reversion to unknown and anchor inactivation were verified.
- Tests reject draft/invalid/stale/mismatched/duplicate/oversized reviews and
  recognized provider-classification overrides. They verify registered review
  delivery, manifest tampering, immutable replay, review-sensitive identities,
  exact normalized-artifact links for same-snapshot review variants, retained
  citations and full review records in ZIP exports. Unmigrated imports and
  readiness checks fail closed rather than discarding review evidence.
- Read-only checks on the real canary produced an unapproved one-sample draft
  with 19 candidate metadata rows. Validation retained all 70 detections and
  unknown classification; its pre-v2 normalization remained readable by ID.
  No actual reviewer decision was supplied or applied.
- The synthetic test container was removed after readiness reported all 23
  tables and no missing review column. Original real canary files and backup
  were not changed. No cloud, live-model or production migration was performed.
  See [operator workflow](ANEMONE_CLASSIFICATION_REVIEW.md).

### Real ANEMONE canary — 2026-09-03

One bounded real sample passed local source reconciliation, rolled-back import,
idempotent import/materialization, full-text retrieval, exact provenance,
signed mock-provider role/export checks, and database backup/isolated restore.
Unknown classification correctly prevents environmental diversity output.
This does not establish scientific acceptance or live cloud/model behavior.
See [`ANEMONE_PILOT_2026-09-03.md`](ANEMONE_PILOT_2026-09-03.md).

The NLTK reachability regression adds three cases; all 34 quality-metric tests
passed. It verifies the application's ROUGE-L path does not call the advisory's
model-artifact APIs; it is not a patch for the upstream dependency.
The full backend rerun passed 586 tests, 8 PostgreSQL-gated skips and 76.75%
coverage; Ruff and diff checks also passed. The canary database container was
removed after a verified backup/restore; artifacts and its backup were retained.

### ANEMONE PR5 implementation — 2026-09-03

- Backend: 583 passed, 8 PostgreSQL-gated skips; 76.75% CI-boundary coverage.
- PostgreSQL: all 8 integration tests passed separately against a freshly
  migrated disposable PG16/pgvector database, including import rollback/replay,
  pre-ranking membership filters and publication-generation checks.
- Frontend: 14 tests, typecheck and production build passed.
- Ruff, dependency consistency, one Alembic head (`20260902_0007`) and
  `git diff --check` passed. The acquisition CLI's default offline plan and
  evaluation CLI help were also checked without provider credentials.
- The temporary database was removed. No live provider download, real GCS
  validation, new authenticated browser smoke, model evaluation or deployment
  was performed. Local object-store and fake GCS protocol tests are not a
  substitute for the rollout gates in
  [`ANEMONE_PR5_PLAN.md`](ANEMONE_PR5_PLAN.md).

### ANEMONE follow-up audit — 2026-09-03 (historical)

Fresh verification passed 555 backend tests (7 service-gated skips), 76.17%
CI-boundary coverage, all 7 PostgreSQL integration checks after applying
migrations on a disposable PG16/pgvector database, 14 frontend tests,
typecheck/build, Ruff, dependency consistency, one Alembic head, and diff checks.
The preview and disposable audit database are stopped. No GCP/live-model
validation was performed in this audit.

Those pre-implementation gates did not cover three reproduced review gaps: incomplete
analysis-manifest acceptance, lost historical analysis provenance after a
rerun, and membership filtering after top-K retrieval. The findings and
permanent regression tests are recorded in
[`ANEMONE_PR5_PLAN.md`](ANEMONE_PR5_PLAN.md). PR5 now fixes all three; real pilot
and deployment verification remain pending.

### Development setup

Install development dependencies:

```bash
./scripts/bootstrap_dev.sh
source .venv/bin/activate
```

The bootstrap script creates an isolated Python 3.12 environment and installs
the fully transitive development lock with `--require-hashes`. Runtime,
analysis, and archived Streamlit dependencies are separately locked in
`requirements/runtime.txt`, `requirements/analysis.txt`, and
`requirements/archive.txt`.

For browser testing of the permission-aware UI without organization OIDC
credentials, run both services with `AUTH_MODE=required`,
`DEPLOYMENT_ENV=test`, matching `INTERNAL_AUTH_SECRET` values, and
`ENABLE_MOCK_LOGIN=true`. Generate the three required scrypt password hashes
with `python scripts/hash_mock_password.py` and assign them to
`MOCK_VIEWER_PASSWORD_HASH`, `MOCK_RESEARCHER_PASSWORD_HASH`, and
`MOCK_ADMIN_PASSWORD_HASH`. The login page exposes three fixed accounts:
`viewer@mock.invalid`, `researcher@mock.invalid`, and `admin@mock.invalid`.
Each is created once in the isolated test database on first API use so foreign
keys, role changes, suspension, chat, feedback, and audit behavior use the same
application-metadata path as provider-backed users. This harness is rejected in
staging and production and does not replace the final real-provider callback
smoke test. Run it only against an isolated test environment because its
mutations are real within that environment.

Run the backend suite and the same coverage boundary used by CI:

```bash
AUTH_MODE=disabled DEPLOYMENT_ENV=test PERSIST_LOCAL_CHAT=false \
python -m pytest tests/ -q --tb=short \
  --cov=api \
  --cov=config \
  --cov=db \
  --cov=preprocessing \
  --cov=ingestion \
  --cov=orchestration \
  --cov=schema \
  --cov=evaluation \
  --cov-report=term-missing \
  --cov-fail-under=70
```

Run the active Python lint boundary:

```bash
python -m ruff check \
  api config.py db evaluation ingestion orchestration preprocessing \
  retrieval schema scripts tests
```

The lint configuration in `pyproject.toml` covers active Python code. Archived
reference code is intentionally outside this boundary.

### ANEMONE acquisition

Run the PR1 contract and acquisition suite:

```bash
python -m pytest tests/test_anemone_ingestion.py -q
```

The suite uses synthetic HTML and TSV/XZ fixtures plus a temporary localhost
Basic-auth server. It tests sample/run scope validation, secret redaction,
inventory-only behavior, interpreted-file selection, FASTQ exclusion,
file/byte limits, unknown and missing roles, XZ and TSV schema failures,
redirect rejection, ETag change detection, interrupted-transfer resume,
immutable snapshots, idempotency, and CLI output. It never contacts ANEMONE
and does not require a live credential.

Live authenticated access is a separate manual smoke test. Run inventory first
against one reviewed sample URL, inspect the JSON limits and file roles, then
use `--execute`. Store credentials outside the repository through the
file-backed configuration documented in `docs/SECURITY.md`. Do not use a live
ANEMONE scope in CI.

Run the PR2 normalization, lineage, and loader unit suite:

```bash
python -m pytest \
  tests/test_anemone_normalization.py \
  tests/test_load_db_upsert.py \
  tests/test_lineage.py \
  tests/test_bootstrap_database.py \
  -q
```

Normalization is validate-only unless `--execute` is supplied. Activation is
an additional explicit action:

```bash
python scripts/normalize_anemone.py --snapshot-id SNAPSHOT_ID
python scripts/normalize_anemone.py \
  --snapshot-id SNAPSHOT_ID --execute --activate
python scripts/load_db.py --upsert --dry-run --json
python scripts/load_db.py --upsert --json
```

The loader uses the activated `current.json` bundle by default. An explicit
different normalization ID is rejected unless the operator also supplies
`--allow-anemone-noncurrent`; the override is recorded in the result. PR2
loads no retrieval documents or embeddings for ANEMONE.

### ANEMONE retrieval and evidence navigation (PR3)

```bash
python -m pytest tests/test_edna_document_builder.py \
  tests/test_edna_materializer.py tests/test_local_retriever.py \
  tests/test_api_edna.py tests/test_prompt_builder.py tests/test_lineage.py \
  tests/test_provenance_snapshot.py -q
```

The disposable PostgreSQL suite also verifies active documents across multiple
provider scopes, independent assignment methods, non-featured taxon filtering,
metadata-only embedding preservation, scientific-correction invalidation,
read API source locators, and scoped document inactivation. Never point these
migration/downgrade tests at a research or production database.

The operator sequence, after a verified backup and canonical load, is:

```bash
python scripts/materialize_edna_retrieval.py
python scripts/materialize_edna_retrieval.py --execute
python scripts/update_embeddings.py
python scripts/build_provenance_manifest.py --publish
```

The first command is read-only. The full manual pipeline uses the same order;
`--no-embed` omits the full-pipeline embedding stage. eDNA JSONL/Parquet artifacts
are separate from the legacy corpus, and a content/provider/model fingerprint
guards the local embedding cache.

Frontend unit tests cover eDNA URL round-trips and invalid filters. Browser
smoke checks use synthetic canonical rows: both methods visible initially;
select a detection; reload; Back/Forward; invalid ID and missing active sample;
confirm exact sample/assay/method IDs and source hashes remain available. PR3
verification on 2026-09-02 passed 524 backend tests, 6 isolated PostgreSQL tests,
12 frontend tests, typecheck/build, and the 70% coverage floor (75.39%).

### ANEMONE PR4 scientific analysis

Verification completed 2026-09-03 JST:

- 555 backend tests passed; 7 PostgreSQL-only checks skipped in that suite;
  aggregate CI-boundary coverage **76.17%** (70% required).
- All **7 PostgreSQL integration tests passed separately** against a fresh
  disposable pgvector/PostgreSQL 16 database; migrations through
  `20260902_0007` applied successfully. The new test covers timestamped end-date
  queries, consistent analysis input reads, actual concurrent materializers,
  generation-registry agreement and failed artifact publication.
- 14 frontend tests, typecheck and production build passed. Ruff, `pip check`,
  single Alembic head and `git diff --check` passed; npm production audit found
  zero vulnerabilities.
- Synthetic browser checks verified cold-load/exact result selection, reload,
  Back/Forward, method-separated environmental rows, keyboard plot-to-result
  navigation, source-sample links and CSV export. Historical runs were labeled
  and did not offer current-analysis chat. No live provider/model evaluation.
- Development preview used explicit disabled auth; Auth.js emitted missing
  local host/secret configuration messages while the development bypass served
  requests. This was not an OIDC/authentication smoke test. Temporary preview
  servers and the disposable test container have been stopped; only synthetic
  scratch artifacts remain under the temporary directory.
- Existing Starlette/httpx, NumPy/netCDF and Alembic deprecation/runtime warnings
  remain visible in test output; there were no failed checks.

The three PR3 review regressions have tests in `test_pr3_review_fixes.py` and
the PostgreSQL suite. Scientific fixtures cover known alpha/beta values,
unresolved/conflicting taxonomy, empty compositions, protocol partitions,
paired method differences, explicit controls, units, distance/time/depth/domain,
SST footprints/coverage, byte/row caps, immutable corruption/freshness, source
scope, provenance snapshot roundtrips and export escaping.

Generate a reviewed analysis manually (set `DATABASE_URL` using the existing
local secret configuration, never command-line credentials):

```bash
python scripts/run_edna_analysis.py --recipe data/analysis/edna_recipe.json
python scripts/run_edna_analysis.py --recipe data/analysis/edna_recipe.json --execute
# Optional typed, source-backed observation snapshot:
python scripts/run_edna_analysis.py --recipe data/analysis/edna_recipe.json \
  --environment data/analysis/reviewed_environment.json --execute
```

Start from `analysis_contracts/edna_v1.json` and replace the placeholder cohort.
Dry-run computes validation/results without publishing. Executed bundles live
under `data/analysis/edna/<analysis_id>/`. The optional Admin `edna_analysis`
stage uses `EDNA_ANALYSIS_RECIPE`; no scheduled job or live profile is enabled.
The CLI is the explicit environmental-input entry point; the Admin stage does
not implicitly discover observation files. Currentness compares canonical
inputs and runtime/algorithm; external observations are pinned snapshots and
must be explicitly refreshed by the operator.

Manual answer-review scenarios are in `evaluation/edna_research_cases.json`.
For the PR5 pilot, select the matching reviewed analysis for each case, capture
the exact request/answer/citations, and assess the expected scientific limits.
Passing deterministic citation checks is not evidence of study validity or
successful live model evaluation.

Verify the frontend:

```bash
cd frontend
npm ci
npm test
npm run typecheck
npm run build
```

### Evidence navigation deep links

Citation navigation uses validated, bookmarkable internal URLs. Raw retrieval
documents open `/provenance?view=trace&doc_id=...`; sample-backed documents can
also open `/explore?view=tables&sample_id=...` and the matching CTD or taxa data
view. Remote-sensing documents open the SST view with an exact ISO date range.
Published analysis and reliability contexts open `/data` with their exact
`context_id`. These full-page actions open a new tab so the originating chat
and its in-memory answer remain available.

The focused frontend tests cover URL construction, identifier/date validation,
source-specific routes, context-to-workbench mappings, and refusal to route
unknown context artifacts. Browser verification should additionally cold-load
one CTD, metagenome, SST, analysis, and reliability link; refresh each target;
exercise back/forward navigation; and confirm malformed identifiers display an
explicit error without loading a default record.

## PostgreSQL Integration

The normal suite skips the gated PostgreSQL integration modules. Against a
disposable migrated PostgreSQL/pgvector database:

```bash
DATABASE_URL=postgresql://onagawa:password@127.0.0.1:5432/onagawa_rag \
RUN_POSTGRES_INTEGRATION=1 \
AUTH_MODE=disabled \
DEPLOYMENT_ENV=test \
python -m pytest \
  tests/integration/test_app_metadata_postgres.py \
  tests/integration/test_operational_postgres.py \
  tests/integration/test_anemone_postgres.py \
  -q
```

The tests verify migrated tables, invite acceptance, user persistence,
database-backed mock identity suspension, audited invitation mutations,
shared rate-limit behavior, the eDNA schema, idempotent eDNA merge,
scientific-correction reporting, and scoped inactivation. Their records are
isolated and cleaned up.

Exercise the database mutation safety path:

```bash
python scripts/load_db.py --upsert --json
python scripts/load_db.py --upsert --json
python scripts/database_backup.py create --label local-check --restore-test
```

The repeated load must be idempotent. The backup command verifies archive
integrity and restores into a disposable database before removing it.

## CI Checks

`.github/workflows/tests.yml` defines:

- backend tests, a 70% aggregate coverage floor, and active Python linting;
- frontend lockfile installation, focused unit tests, typechecking, and
  production build;
- a real pgvector service, Alembic migration, metadata/shared-rate-limit
  integration tests, repeated transactional upserts, and backup restore testing;
- dependency review for public repositories or private repositories with GitHub
  Code Security enabled.

Workflow token permissions are read-only. Official actions are pinned to full
commit SHAs and dependency updates are monitored by
`.github/dependabot.yml`.

For a private repository with GitHub Code Security, set the repository Actions
variable `GH_CODE_SECURITY_ENABLED=true`. Enable these repository settings:

- dependency graph;
- Dependabot alerts and security updates;
- secret scanning and push protection when available;
- CodeQL default setup for Python and JavaScript/TypeScript.

Protect the default branch with the backend, frontend, PostgreSQL integration,
and applicable dependency-review checks.

Package-advisory audits that send dependency metadata to third-party services
are not enabled by this repository configuration. Add them only after the
repository owner approves the service and data-sharing implications.
