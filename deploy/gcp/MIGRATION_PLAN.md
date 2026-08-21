# GCP prototype migration plan

This plan moves the current local prototype to GCP in independently testable
stages. No stage advances until its integration gate passes. The initial
financial envelope is **JPY 10,000 per calendar month** for project
`data-infra-infobio`.

## Current cloud baseline

Live state verified through 2026-08-20:

- project billing is enabled and the linked JPY billing account is open;
- the project is in organization `735965963562`;
- the required foundation and runtime APIs are enabled;
- Artifact Registry repository `onagawa-source-chat` exists in
  `asia-northeast1`, contains the tested API and frontend images, and has
  cleanup rules in dry-run mode;
- service accounts `onagawa-app` and `onagawa-jobs` exist with no user-managed
  keys;
- the database, Auth.js signing, internal API signing, and Google OAuth client
  secrets each have one enabled version;
- regional bucket `data-infra-infobio-prototype-data` has public access
  prevention, uniform bucket-level access, versioning, and the reviewed
  lifecycle policy enabled; GCP's default seven-day soft-delete protection
  remains enabled;
- Cloud SQL instance `onagawa-postgres`, Cloud Run migration job
  `onagawa-migrate`, and the authenticated multi-container Cloud Run service
  `onagawa-source-chat` are ready;
- project, Cloud Run, and Cloud SQL budget controls are configured; and
- the billing account has a Billing Account Administrator who can create and
  manage budgets.

The persistent database, authenticated serving foundation, Phase 5 corpus,
and Phase 6 Vertex runtime are live. The bounded seed contains 1,860 raw
objects, 14,231 corpus rows, and 323 retrieval documents. All 323 retrieval
documents now have 768-dimensional `gemini-embedding-001` embeddings with
provider provenance. Authenticated chat traffic uses `gemini-3.6-flash` on
Vertex AI through workload identity.

## Cost-control model

A normal Cloud Billing budget sends alerts but does not stop usage. The plan
therefore uses three layers:

1. a project-wide monthly alert budget;
2. service or `cost_component` label budgets for attribution and alerts; and
3. technical ceilings on every resource.

Cloud Run also supports a Preview spend-cap budget. The Cloud Run envelope is
**JPY 2,500/month**, with the enforced trigger set lower at **JPY 2,250/month**
to leave 10% headroom for delayed enforcement. It covers the serving service
and all Cloud Run Jobs together. It cannot distinguish jobs by label, so the
component budgets below remain alerts rather than hard stops. Spend-cap
enforcement is not instantaneous, and in-flight work can still exceed the
trigger slightly.

Do not automate disabling billing for the whole project. Disabling billing can
stop every service and can eventually delete resources. Persistent resources,
including Cloud SQL and Cloud Storage, also continue accruing fixed charges
when ordinary alert budgets are exceeded. Their resource-size and retention
ceilings are the primary controls.

### Monthly prototype envelope

| Component | JPY/month | Budget or technical ceiling |
| --- | ---: | --- |
| Cloud SQL PostgreSQL | 4,000 | Alert budget; `db-f1-micro`, zonal, no replicas, 10 GB SSD, automatic growth limited to 20 GB |
| Cloud Run serving | 1,200 | `cost_component=serving`; minimum 0, maximum 1 instance, concurrency 20 |
| Cloud Run migration job | 100 | `cost_component=migration`; manual only, one task, no retry, 15-minute timeout |
| Cloud Run pipeline job | 400 | `cost_component=pipeline`; dry-run default, manual execution, one task, no retry, 60-minute timeout |
| Cloud Run embedding job | 500 | `cost_component=embedding`; dry-run default, manual execution, batch size 32, one task, no retry, 30-minute timeout |
| Cloud Run evaluation job | 300 | `cost_component=evaluation`; quick suite first, one task, no retry, 60-minute timeout |
| Cloud Storage | 500 | Alert budget; one regional bucket; keep at most three noncurrent versions and delete them after 30 days |
| Cloud Build | 400 | Alert budget; manual builds only at first; 40-minute build timeout; no automatic branch trigger |
| Artifact Registry | 200 | Alert budget; keep five recent versions and remove older versions after 30 days |
| Secret Manager | 100 | Alert budget; four application secrets; no scheduled access polling |
| Logging and Monitoring | 300 | Alert budget; normal application logs only; no debug payloads or request bodies |
| Model runtime reserve | 1,000 | Vertex only; no model VM; chat limited to one Cloud Run instance and 10 requests/user/minute; output, timeout, retry, batch, and manual-job ceilings enforced in code and deployment |
| Network and unclassified reserve | 1,000 | Covered by the project-wide budget; investigate any usage here before raising the envelope |
| **Project total** | **10,000** | Monthly alert budget at 50%, 75%, 90%, and 100%, plus a 95% forecast alert |

Budget amounts are operating guardrails, not cost forecasts or guarantees. Set
them below the maximum amount actually available because billing reports and
spend-cap enforcement can be delayed. Any increase requires an explicit review
of the prior seven days of cost by service and SKU.

### Budget ownership and notifications

- A principal with project-budget update permission creates and edits the
  project budget and the Cloud Run spend cap. Billing Account Administrators
  retain account-wide management access.
- Keep default IAM recipients enabled so Billing Account Administrators and
  Billing Account Users receive alerts.
- For a single-project budget, also notify project owners.
- Use `cost_component` labels from the deployment templates for advisory
  component budgets. The project-wide budget catches unlabeled or unsupported
  charges.
- Do not connect an automatic billing-disable action during the prototype.

## Migration order and integration gates

### Phase 0: governance and cost controls

Create no runtime resources.

Status on 2026-08-03: **complete**. The Cloud Billing Budget API is enabled and
the project-scoped Billing console shows the two Phase 0 controls plus the
Phase 3 database control:

- `data-infra-infobio-monthly-guardrail`: JPY 10,000 monthly, actual alerts at
  50%, 75%, 90%, and 100%, and a forecast alert at 95%;
- `data-infra-infobio-cloud-run-spend-cap`: Cloud Run only, JPY 2,250 monthly
  enforced trigger, default notifications at 50%, 80%, and 100%, status
  `Configured`;
- `data-infra-infobio-cloud-sql-alert`: project `data-infra-infobio` and Cloud
  SQL only, JPY 4,000 monthly, actual alerts at 50%, 75%, 90%, and 100%, and a
  forecast alert at 95%.

All three controls notify Billing Account Administrators/Users and project
owners.
The CLI account still cannot enumerate account-wide budgets, so live checks
must use the project-scoped Billing console unless its IAM is expanded.

1. Enable only the Cloud Billing Budget API.
2. Create the JPY 10,000 monthly project alert budget.
3. Reserve JPY 2,500 for Cloud Run and create a JPY 2,250 enforced spend-cap
   trigger in the Billing console.
4. Record the budget owner and alert recipients.
5. Confirm which project-budget editors can raise the alert budget or lift the
   spend cap, and keep that access limited to project and billing operators.

Gate:

- budget scope is exactly `data-infra-infobio`;
- actual thresholds at 50%, 75%, 90%, and 100% and the 95% forecast threshold
  are visible;
- the Cloud Run spend cap is `Configured` at JPY 2,250 with 50%, 80%, and 100%
  notifications;
- both billing administration and project-owner recipients are confirmed; and
- no runtime API or component was created as part of this phase.

### Phase 1: non-runtime foundation

Run `prepare-foundation.sh` only after Phase 0 passes. It enables the required
APIs and creates the Artifact Registry repository, workload service accounts,
empty Secret Manager containers, and a regional data bucket.

Status on 2026-08-03: **complete**. The guarded script created the foundation
in `asia-northeast1` with bucket `data-infra-infobio-prototype-data`. The
storage lifecycle is active, the Artifact Registry cleanup policy remains in
dry-run mode, all secret containers have zero versions, and no Cloud Run or
Cloud SQL runtime exists.

Apply the prepared retention policies after reviewing them:

```sh
gcloud storage buckets update "gs://DATA_BUCKET" \
  --lifecycle-file=deploy/gcp/storage-lifecycle.json

gcloud artifacts repositories set-cleanup-policies onagawa-source-chat \
  --project=data-infra-infobio \
  --location=asia-northeast1 \
  --policy=deploy/gcp/artifact-cleanup-policy.json \
  --dry-run
```

Leave the Artifact Registry policy in dry-run until its matches have been
reviewed. Apply it later with `--no-dry-run`.

Gate:

- no user-managed service-account keys exist;
- `onagawa-app` can view data objects but cannot write them;
- `onagawa-jobs` can write data objects;
- only the named identities can access the intended secret containers;
- public access prevention and uniform bucket-level access are enabled; and
- the storage lifecycle and registry cleanup dry-run match only intended data.

### Phase 2: build and immutable artifacts

Run local tests before spending Cloud Build time, then submit `cloudbuild.yaml`
manually. Do not create a branch trigger yet.

Status on 2026-08-03: **complete**. Source commit `dfde9b9` passed Ruff,
400 backend tests (with 3 skipped), the frontend typecheck, and the frontend
production build. Manual Cloud Build
`09350352-a1cb-4c2e-b459-1ee17bb7f81d` published both images with the same
build tag:

- API: `sha256:b0b1243badc7062cd2ca7ed9a9165785618d15c0734b0b54b48650aa933b2ab0`
- Frontend: `sha256:17392ca04ed9b270e40473193682aabf1cbfdec12305a356504a098e76be284c`

The Cloud SQL backup fixes then passed Ruff and 401 backend tests (with 3
skipped). Backend-only build `6e36e1e9-ac25-4273-a49f-3fbef9a8510f`
published the current PostgreSQL 16-compatible API image:

- API: `sha256:ffe6480bfe5d2626d628bb179fc019e6ab148c771cae1132bddbb230f8f958d2`

All five deployment templates rendered as valid YAML using non-secret pending
endpoint/client values, with application secrets represented only by Secret
Manager references. Artifact Registry remains in cleanup dry-run mode and
keeps the five newest versions. No Cloud Run service, Cloud Run Job, or Cloud
SQL instance was created.

Phase 4 build `810380c1-40bc-46ea-9725-1dc7eb5c4512` then passed the repository
Python lint/tests, frontend typecheck, and production build for source commit
`81b0c70`. It published the API and frontend images under the same immutable
build tag used by the serving revision.

Gate:

- backend tests and lint pass;
- frontend typecheck and production build pass;
- both images are stored under one immutable Cloud Build ID;
- a rendered manifest contains no unresolved tokens or secret values; and
- the registry cleanup policy preserves the five newest image versions.

### Phase 3: database and schema

Cloud SQL is the first persistent, always-billed runtime component. Create it
only after the previous phases pass. Use the guarded
`create-cloud-sql.sh`, create the database user out of band, add the database
secret version, and run the migration job manually.

Status on 2026-08-03: **database foundation and recovery check complete;
data-dependent integration gate pending**.

- `onagawa-postgres` is RUNNABLE in `asia-northeast1-c` on PostgreSQL 16
  Enterprise with `db-f1-micro`, zonal availability, deletion protection,
  10 GB SSD storage, and a 20 GB automatic-growth ceiling.
- Automated backups and point-in-time recovery are enabled with seven retained
  backups and seven days of transaction logs.
- Database `onagawa_rag`, built-in user `onagawa_app`, and enabled database
  secret version 1 exist. The secret value was never written to the repository
  or emitted in command output.
- Migration execution `onagawa-migrate-8qrll` completed once with no retry,
  installed the `vector` extension, and left all 16 expected tables present.
- Recovery execution `onagawa-migrate-rpbkb` used the immutable API image
  above, completed successfully in 17.4 seconds, and restored an 85,751-byte
  custom archive into a disposable database. Its SHA-256 was
  `fbf4c2d8507ef6772329a9c14be1190d88f27b602c4428117292beef1814c3b1`;
  all table row counts matched and the disposable database was removed.
- The job has one task, parallelism one, no retries, a 15-minute timeout, and
  `cost_component=migration`. Cloud Run has no serving service yet.

The two live PostgreSQL integration modules and repeated corpus upsert require
the representative data subset scheduled for Phase 5. They remain mandatory
before the database gate is marked fully complete; they are not treated as
evidence for enabling public traffic.

Gate:

- instance tier, zonal availability, deletion protection, 10 GB initial
  storage, and 20 GB growth ceiling match the plan;
- PostgreSQL 16 and the `vector` extension are available;
- Alembic and corpus bootstrap complete once with no retry;
- both PostgreSQL integration modules pass against the migrated database;
- repeated upsert is idempotent; and
- a backup is verified by restoring it to a disposable database.

### Phase 4: restricted serving and authentication

Deploy the multi-container Cloud Run service with no public traffic first. The
Next.js container remains the ingress and FastAPI remains a localhost sidecar.
Keep the existing Auth.js Google OIDC flow and Cloud SQL-backed invitations and
roles.

Status on 2026-08-04: **deployed and accepted for the single-admin cloud
prototype**.

- Service `onagawa-source-chat` revision `onagawa-source-chat-00004-s5v` is
  Ready in `asia-northeast1` and receives 100% of traffic at
  `https://onagawa-source-chat-469489188516.asia-northeast1.run.app`.
- The frontend and API sidecar use build
  `88b6a119-67f7-46c6-9820-04e22627086f`. FastAPI listens only inside the
  Cloud Run instance, and Cloud SQL and the future model endpoint have no
  public route.
- Minimum instances is zero, maximum instances is one, and concurrency is 20.
  The `cost_component=serving` label and JPY 2,250 Cloud Run spend cap remain
  in effect.
- Google Auth Platform uses an internal Tohoku University audience. The live
  OAuth callback, the accepted 30-day admin invitation, the Cloud SQL-backed
  admin session, logout, and subsequent login all passed in the hosted UI.
- With explicit operator approval, `allUsers` has the Cloud Run Invoker role so
  a browser can reach the frontend. Unauthenticated users are redirected to
  `/login`, and direct access to `/api/backend/health/live` returns 401. The
  application remains invitation-only through Google OIDC and its database
  authorization layer.
- The live System page reports Cloud SQL available and shows the absent corpus
  and model runtime as expected degraded states. Missing Phase 5 artifacts no
  longer prevent the remaining diagnostics from loading, and the absent Phase
  6 model produces a concise warning instead of an error traceback.
- The new revision produced no error-level entries during acceptance checks,
  and log searches found no application secret names or access/refresh token
  markers.
- The automated authentication suite covers viewer, researcher, admin,
  invitation, and suspension behavior. The sole live admin was not suspended
  or demoted because that could lock out the project operator; Phase 7 still
  requires two invited test identities for the full multi-user path.
- Authenticated revision `onagawa-source-chat-00003-vff` is the immediate,
  database-compatible rollback target. Revision `onagawa-source-chat-00002-sdj`
  remains an earlier authenticated fallback. The initial one-container reservation
  revision `onagawa-source-chat-00001-pns` is a non-production placeholder and
  must not receive traffic.

Gate:

- service maximum is one instance and minimum is zero;
- `/health/live` succeeds through an authenticated operator path;
- FastAPI, Cloud SQL, and the model endpoint are not publicly reachable;
- login callback, invitation acceptance, viewer/researcher/admin permissions,
  logout, and suspension all pass;
- secrets and tokens do not appear in logs; and
- a previous image can receive traffic without a database downgrade.

Only after this gate passes should browser traffic be allowed to reach the
frontend.

### Phase 5: storage and batch pipeline

Status on 2026-08-20: **complete for the no-embedding prototype corpus**.

The current complete raw source set is already a bounded prototype seed:

- 12 required CTD/metagenome files, 36,549,398 bytes;
- 1,848 SST NetCDF files, 52,609,972 bytes; and
- 1,860 objects and 89,159,370 bytes in total.

The SST contract requires at least 1,800 files, so an arbitrary smaller SST
sample would fail the production validation contract. Upload the complete
raw-only seed, but do not upload locally generated normalized/serving outputs,
pipeline history, evaluation artifacts, or database backups. Generate a
content-addressed manifest first and require the cloud raw prefix to match its
object and byte totals.

Execute Phase 5 in four separately approved stage groups:

1. raw upload, validation-only, and full `--dry-run --no-embed` planning;
2. artifact generation through validation, ingestion, retrieval-document
   construction, pre-analysis, and reliability, with no database mutation;
3. a read-only upsert plan followed by an archive verification and disposable
   restore test; and
4. one transactional no-embedding upsert, then the identical upsert again as
   an idempotency check.

The local reference corpus produces 207 sample-registry rows, 323 retrieval
documents, 286 anchor events, 496 cross-source links, and 1,849 provenance
records. The database upsert plan contains 14,231 incoming rows across eight
tables. Treat those as review baselines, not permission to ignore a justified
environment-specific difference.

Keep the pipeline at one task, zero retries, 2 CPU, 4 GiB memory, and an
initial 30-minute timeout. Stop after the first failed run instead of retrying.
Keep embeddings disabled and stay inside the JPY 400 monthly pipeline envelope
and the shared JPY 2,250 Cloud Run spend cap.

Live execution record:

- Cloud Build `88b6a119-67f7-46c6-9820-04e22627086f` passed its lint, backend,
  and frontend gates in 7m52s and published immutable API and frontend images.
- Job `onagawa-pipeline` is Ready with one task, zero retries, a 30-minute
  timeout, 2 CPU, 4 GiB, the jobs service account, Cloud SQL attachment, and a
  writable GCS FUSE mount. Its stored default remains `--dry-run --no-embed`.
- The raw-only upload verified 1,860 objects and 89,159,370 bytes. Manifest
  `manifests/phase5-raw-v1.json` records collection SHA-256
  `eeb63298a80eb4b7d777fc6f6d5394d503f345cd30509ac9e6d667b716188cad`.
- Validation execution `onagawa-pipeline-rxkfj` completed in 1m03s. It passed
  all 12 CTD/metagenome source checks and found exactly 1,848 SST NetCDF files.
  Full dry-run execution `onagawa-pipeline-r2xb6` completed in 59s with seven
  planned stages, no blockers or warnings, database connectivity, backup
  tooling, and no artifact or database mutations.
- Non-database execution `onagawa-pipeline-blbk5` completed all five selected
  artifact stages in 24m12s. GCS FUSE emitted transient 429 retries while
  registering 1,848 small SST objects, but the single task completed within its
  cap. Production optimization should stage or compact those small objects
  instead of increasing the cost ceiling.
- Cloud artifacts match the reference: 10,955 CTD profiles, 162 CTD summaries,
  82 metagenome samples, 1,848 SST points, 79 SST daily summaries, 286 anchor
  events, 323 retrieval documents, 496 cross-source links, five analysis
  documents, four reliability documents, and 1,849 provenance entries.
- Isolated backup execution `onagawa-pipeline-ppgc7` verified an 88,192-byte
  archive with SHA-256
  `f9ebb453dffa230184138239cf8fbfdde242dc023e475a276cffacc366606477` and
  removed its disposable restore database. The guarded first upsert execution
  `onagawa-pipeline-shdzq` then inserted the expected 14,231 corpus rows without
  resetting or replacing application rows.
- Idempotency execution `onagawa-pipeline-9d2gf` first restored and verified a
  populated 1,205,375-byte archive with SHA-256
  `e398c2576ee897927edf69544dd784b9b274c5316fa5f48b771011292628b250`,
  removed the disposable database, and reported zero inserts, zero updates,
  and 14,231 unchanged rows across all eight corpus tables.
- Serving revision `onagawa-source-chat-00004-s5v` uses the same immutable
  images and explicitly points `SST_NETCDF_DIR` and `HIMAWARI_RAW_DIR` at the
  GCS mount. Authenticated browser checks show Raw, Corpus, SST, and Database
  ready; 15 of 15 derived artifacts present; all expected table counts; and
  no active pipeline job. Unauthenticated requests still redirect to OIDC.
- Phase 5 did not enable a model runtime or generate embeddings. Those changes
  were introduced only after the Phase 6 backup, migration, canary, evaluation,
  and serving gates passed.

Gate:

- dry-run produces the expected stages without mutations;
- the raw prefix matches the uploaded manifest's 1,860 objects and total bytes,
  checksum-only synchronization reports no pending changes, and the manifest
  collection digest is recorded;
- validation, provenance manifests, and artifact freshness checks pass;
- the limited pipeline creates expected row and object counts;
- a second upsert reports zero inserts and zero updates;
- a pre-mutation backup and restore test pass; and
- noncurrent object versions obey the lifecycle policy.

### Phase 6: embeddings and model runtime

Do not create an Ollama VM as part of the baseline migration. It would add an
always-on compute cost that is not protected by the Cloud Run spend cap.
Implement the existing `model_runtime.py` provider boundary for a native Vertex
runtime first, or approve a separately costed private Ollama design.

Start with a small embedding sample and the quick evaluation job. Apply an
eligible service spend cap or a strict API quota and application-level request
limit before enabling general chat traffic.

Status on 2026-08-20: **complete**. The native adapter uses Application Default
Credentials and the `google-genai` SDK without downloaded keys. The Vertex AI
API is enabled; `onagawa-jobs` and `onagawa-app` have Vertex AI User and no
broader model-runtime role. `gemini-embedding-001` uses explicit retrieval
document/query task types and 768 output dimensions, preserving the pgvector
schema. `gemini-3.6-flash` uses a 1,600-token output ceiling, zero thinking
budget, a 120-second client timeout, and at most three bounded attempts for
429/5xx responses. Hidden SDK retries are disabled.

Execution evidence:

- pre-migration backup `20260820T130422Z-phase6-pre-migration-onagawa_rag.dump`
  restore-tested successfully with SHA-256
  `4291ec35a9af09c0c71fa2c7db07dc766014f2d263a297005be075c2f3e6fb9f`;
- migration execution `onagawa-migrate-792vs` upgraded the database to
  `20260820_0003` and verified all 16 tables plus pgvector;
- credential probe `onagawa-embedding-b6hsz` returned one 768-dimensional
  vector, the 16-document canary `onagawa-embedding-crxn4` committed cleanly,
  and full refresh `onagawa-embedding-rh88n` completed the remaining 307
  documents in ten successful batches;
- idempotency execution `onagawa-embedding-sdtcn` selected zero documents and
  made no Vertex request;
- strict quick evaluation `onagawa-evaluation-jpn4x` completed all 20 cases
  without errors: retrieval precision was 100% in every mode, source coverage
  was 70% in every mode, and Full-mode citation accuracy was 100%; and
- serving revision `onagawa-source-chat-00006-ms2`, built from immutable image
  tag `5b9c22ef-2b12-4903-a3d5-ecf50e7ffe3b`, receives 100% of traffic, runs
  as `onagawa-app`, scales from zero to one instance, and has no Ollama
  endpoint. An authenticated browser smoke test loaded all 323 documents and
  returned a `gemini-3.6-flash` answer with seven valid citations, no invalid
  citations or warnings, and a 100% trust score.

The embedding and evaluation jobs remain manual, have zero task retries, and
store safe dry-run/one-question defaults. General chat is limited to ten
requests per user per minute; the service remains at maximum one instance.
Billing export data can lag, so the JPY 1,000 reserve remains an operating
guardrail rather than a hard provider-level spending cap. The canary, full
refresh, strict evaluation, and one live smoke query stayed within the planned
bounded request counts; review posted billing data before raising any limit.

Completed execution order:

1. build and test the immutable image while Vertex remains disabled;
2. back up and restore-test Cloud SQL, then apply the provenance migration;
3. enable the Vertex AI API and grant Vertex AI User only to `onagawa-jobs`;
4. run one credential/dimension probe with no database writes;
5. update 16 rows, verify provider/model/dimension metadata and retrieval;
6. update the remaining rows and prove an identical rerun selects zero rows;
7. run one known evaluation question in Full mode, then the quick suite;
8. grant the serving identity access and switch the service only after all
   gates and the measured cost review pass.

Gate:

- model credentials use workload identity, not downloaded keys;
- request, token, and batch limits are configured;
- a small embedding batch has the expected dimension and row count;
- retrieval and citation checks pass against known questions;
- timeout, quota-exceeded, and unavailable-model paths fail safely; and
- the bounded request-count estimate fits the JPY 1,000 model reserve, and
  posted billing data is reviewed before any ceiling is raised.

### Phase 7: end-to-end prototype release

Run the full integration path with the existing administrator and one invited
researcher before inviting the wider research team. The approved researcher is
`akane.kitamura.e7@tohoku.ac.jp`. Viewer-only and suspended-user boundaries
remain covered by automated authorization tests; do not suspend a real user as
part of the reduced live cohort.

Status on 2026-08-21: **implementation in progress**. The execution procedure,
hard request/model limits, recovery sequence, and go/no-go criteria are defined
in `docs/PHASE7_RELEASE_RUNBOOK.md`. The reusable probe is dry-run by default,
requires exact production-host confirmation plus an external private cookie
file to execute, and cannot exceed five concurrent requests, five minutes, 300
reads, or 18 chat calls in one run. The entire release exercise is capped at 32
chat generations. No Phase 7 scale, quota, pool, timeout, or budget increase is
approved.

Execution order:

1. freeze the Phase 6 revision, IAM, database, job, billing, and application
   baseline;
2. create and restore-test a full `phase7-pre-release` logical backup;
3. pass local tests, production build, probe safety tests, and one bounded
   authenticated admin journey;
4. have the researcher validate their own OIDC, role boundary, chat, evidence,
   and feedback path without sharing or impersonating their session;
5. deploy one immutable release candidate and prove application/database state
   persists across the revision;
6. run the capped mixed-load test while observing Cloud Run, Cloud SQL, Vertex,
   and application logs;
7. route traffic to the previous revision and forward again, then exercise a
   disposable full-database restore; and
8. complete posted 24-hour and seven-day cost reviews before the wider-team
   go/no-go decision.

Gate:

- sign in -> query -> retrieval -> model response -> citations -> feedback is
  successful;
- pipeline status, evaluation runs, and audit events survive a new Cloud Run
  revision;
- a controlled load test stays within one instance and the configured database
  connection pool;
- budget labels appear in cost reporting;
- rollback and database-restore runbooks are exercised; and
- the first 24-hour and seven-day cost reviews remain inside the envelope.

After seven stable days, maximum Cloud Run instances may increase from one to
two only if measured database connections and the remaining monthly budget
support it.

## Stop conditions

Pause migration and investigate before creating the next component when:

- actual spend reaches 75% of any component envelope earlier than expected;
- forecast spend reaches 95% of the project budget;
- a resource appears without `environment=prototype` and a component label;
- Cloud SQL grows past 15 GB;
- a job requests retry, parallelism, or a longer timeout;
- logs contain secrets, tokens, prompts with restricted data, or full request
  bodies; or
- a phase gate fails twice without an understood root cause.

## GCP references

- [Cloud Billing budgets and alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [Preview spend-cap budgets](https://cloud.google.com/billing/docs/how-to/budgets-spend-caps)
- [Cloud Run maximum instances](https://cloud.google.com/run/docs/configuring/max-instances)
- [Cloud SQL PostgreSQL instance settings](https://cloud.google.com/sql/docs/postgres/instance-settings)
- [Cloud Storage lifecycle management](https://cloud.google.com/storage/docs/lifecycle)
- [Artifact Registry cleanup policies](https://cloud.google.com/artifact-registry/docs/repositories/cleanup-policy-overview)
