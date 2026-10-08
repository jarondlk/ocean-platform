# GCP prototype deployment

This directory contains the templates, guarded preparation scripts, and
operational guidance for the live managed GCP prototype. Applying a template or
running a guarded script is always an explicit operator action; repository
checkout, rendering, tests, and Cloud Build do not provision runtime resources
automatically.

[`MIGRATION_PLAN.md`](MIGRATION_PLAN.md) is the historical initial-migration
record; retain its dated resource evidence and cost-control rationale, but do
not treat it as the current release order. Use
[`../../docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md) and the completed
[v0.7.4 operations record](../../docs/RELEASE_0.7.4_OPERATIONS.md) for the
current deployment. Earlier records retain their dated evidence.
The user later allowed up to **JPY 100,000/month** for the project while asking
for import optimization first. This does not change any budget alert or
component limit automatically. The historical database compute and 10 GiB SSD
list estimate in that performance plan is about JPY 10,835/month, excluding other project costs,
backups, networking and taxes; verify the actual bill and alert settings before
further paid changes. See the
[performance recovery plan](../../docs/ANEMONE_IMPORT_PERFORMANCE_PLAN.md).
Cost controls must be in place before runtime resources are created.

## Current deployed milestone

v0.7.4 was verified on 2026-10-08 JST: 100% traffic on
`ocean-platform-v074-patch1008`, runtime/tag source `f73d5fd`.
See [operations](../../docs/RELEASE_0.7.4_OPERATIONS.md) for accepted digests,
backup/restore, provisional analysis publication, normal admin Chat/CSV,
preservation and cleanup. Five manual jobs were aligned without execution;
both superseded acquisition jobs remain unchanged. No new provider downloads.
Schema/auth/IAM/mounts/resources/canonical scientific publications are preserved.
The provisional Miyagi demo is explicitly user-approved; formal identities/areas
and remaining spatial objectives stay open. Immediate rollback is v0.7.3.

The following base-release inventory was verified at the 2026-10-06 JST rollout.
See [v0.7.2 operations](../../docs/RELEASE_0.7.2_OPERATIONS.md) for exact
build/digests, private backup/restore, unchanged schema, acceptance and cleanup.

- Project `data-infra-infobio`, region `asia-northeast1`.
- GitHub release `v0.7.2`, exact tag/runtime source `03638e6`, 100% traffic at that rollout on
  `ocean-platform-v072-patch1006`; schema `20261005_0016`.
- Canonical auth/CORS origin `https://oceaninfobio.com`; five manual jobs aligned
  to the exact API image without execution. API storage is read-only; job mode is
  external. v0.7.1 isolated normal role QA and fresh v0.7.2 admin/history QA
  passed; cleanup passed. SQL disk is 15 GiB, with growth limit 20 GiB.
- Artifact Registry `ocean-platform`; identities `ocean-platform`/`ocean-jobs`,
  Cloud SQL `ocean-postgres` / `ocean_platform` (PostgreSQL 16), private bucket
  `data-infra-infobio-ocean-data`. Retained limits: min zero/max one, concurrency 20.
- Corpus remains 7,319 documents/embeddings, including 6,996 eDNA; 3,498 source
  occurrences/assays and 349,638 assignment rows. Scientific classification,
  physical identity/areas and historical SST decisions remain unresolved.
- Compatible v0.7.1 rollback and all historical rollback tags retained. Temporary
  v072 callback/tags/verifier/QA revision/restore database were removed.
- Live mobile QA (#107) is explicitly deferred; sign-out (#108), OS maintenance
  (#104) and real demos/evidence (#89/#102/#103) remain separate open work.

The deployed standalone frontend reports source-map-js 1.2.2, resolving #110.
Published tags remain immutable. Read the
[pre-deployment audit](../../docs/PRE_DEPLOYMENT_AUDIT_2026-10-06.md) and
[script inventory](../../scripts/README.md) before cloud work. The generic
bootstrap templates are not the current service specification; derive patches
from a freshly read serving definition and preserve secrets, IAM, mounts,
resources, canonical auth and rollback routes. Never replay old rendered YAML.

See [`../../docs/GCP_RESOURCE_AUDIT.md`](../../docs/GCP_RESOURCE_AUDIT.md) for
the historical post-cutover inventory, absence checks, housekeeping controls,
and rollback resources that require explicit approval before deletion. Rerun
the live audit before making current retirement, budget, IAM, or capacity
decisions.

The canonical live URL is
[`https://oceaninfobio.com`](https://oceaninfobio.com). The default Cloud Run
URL remains available for rollback and operations; Auth.js redirects it to the
canonical origin.

## v0.6.0 rollout (2026-10-01)

GitHub v0.6.0 is published at `91d8567`, with passing remote checks and an
immutable source-archive build. A fresh backup restored across all 28 tables,
and the standard migration job applied `20261001_0014`. Revision
`ocean-platform-v060-sec1001` is Ready at 100% production traffic from the checked
security amendment `6fd37eb`; all five manual jobs use its API image. Read-only
live runtime QA and post-cutover anonymous HTTP checks passed. The user approved
promotion with authenticated UI/history and repeated scientific-answer QA
deferred. The temporary `v060-candidate` tag was removed; the v0.5.0 rollback
route remains. Follow the [v0.6.0 operations record](../../docs/RELEASE_0.6.0_OPERATIONS.md)
for exact evidence and deferred checks; do not apply stale rendered templates.

## Target topology

- One Cloud Run service with Next.js as the ingress container and FastAPI as a
  localhost sidecar.
- Cloud SQL for PostgreSQL 16 with the `vector` extension.
- Cloud Storage mounted read-only by the serving API and read-write by
  operator-run jobs.
- Secret Manager for the database URL, signing secrets, and OIDC client secret.
- Cloud Run Jobs for migrations, ingestion, embedding refresh, and evaluation.
- Immutable Provenance snapshots published by the pipeline job and read
  directly from Cloud Storage by the serving API.
- Google OIDC through the existing Auth.js flow, with application invitations
  and roles retained in Cloud SQL.
- Vertex AI through Application Default Credentials and the Cloud Run service
  identity. No downloaded service-account key or always-on model VM is used.

The serving revision sets `JOB_EXECUTION_MODE=external`. This deliberately
prevents an autoscaled web instance from starting daemon-thread pipeline or
evaluation work. Operators execute the existing CLI scripts as Cloud Run Jobs.
The Evaluation UI can read all stored results and prepare bounded run controls,
but its Start actions intentionally receive the external-runner response until
a least-privilege Cloud Run Jobs execution bridge is implemented. Do not work
around this boundary by enabling local/background-thread execution in the
serving revision.
It also sets `PROVENANCE_READ_MODE=snapshot`, so manifest and document-trace
requests read a verified immutable object and never rebuild lineage through the
GCS FUSE mount. Follow
[`../../docs/PROVENANCE_SNAPSHOT_RUNBOOK.md`](../../docs/PROVENANCE_SNAPSHOT_RUNBOOK.md)
for validation, publication, rollout, and rollback.
The serving template uses Vertex AI with the same bounded generation settings
as the passing evaluation job. Grant Vertex AI User to `ocean-platform`
only immediately before this reviewed revision is deployed; keep maximum
instances at one and the shared `/chat` limit at 10 requests per user per
minute.

## Baseline APIs (initial provisioning)

Enable these after billing is linked:

```sh
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=data-infra-infobio
```

Compute Engine remains optional. Vertex AI is already in use by production.
The Phase 6 enablement/grant/canary sequence below describes initial onboarding,
not an instruction to change existing IAM during a routine patch.

See [`AUTHENTICATION.md`](AUTHENTICATION.md) for the selected authentication
transfer, callback URL, provider identity rules, and IAP/Identity Platform
tradeoffs.

## Foundation preparation (initial provisioning only)

`prepare-foundation.sh` is guarded by `CONFIRM_GCP_PROJECT` and creates only
APIs, the Artifact Registry repository, service accounts, empty secret
containers, the data bucket, and least-privilege bindings. It does not create
secret versions, Cloud SQL, jobs, or a Cloud Run service.

`create-cloud-sql.sh` is separately guarded by
`CONFIRM_BILLABLE_GCP_PROJECT`. Review the selected tier and expected cost
before running it. The script deliberately does not accept or generate a
database password.

Neither script is run as part of tests or builds.

`upload-data.sh` uploads only the bounded Phase 5 raw seed: the 12 required
CTD/metagenome files under `data/raw` and the NetCDF files under
`onagawa_sst_subset`. It never uploads generated artifacts, evaluations,
pipeline history, or database backups, and it never deletes local or remote
objects.

Dry-run is the default. Before contacting Cloud Storage, the script rejects
missing or unexpected input files and builds a SHA-256 manifest with the exact
destination, size, and digest of every object:

```sh
DATA_BUCKET=data-infra-infobio-ocean-data \
  ./deploy/gcp/upload-data.sh
```

After reviewing the dry-run, an upload requires both an explicit mode and an
exact bucket confirmation:

```sh
DATA_BUCKET=data-infra-infobio-ocean-data \
CONFIRM_DATA_BUCKET=data-infra-infobio-ocean-data \
UPLOAD_MODE=apply \
  ./deploy/gcp/upload-data.sh
```

The apply path uses checksum comparisons, verifies the remote raw object and
byte totals, then writes the manifest under `manifests/`. The current seed is
1,860 objects and 89,159,370 bytes. Do not use `gcloud storage rsync data/`.

## Build

A routine image patch does not rerun foundation, SQL creation or raw seed upload.
Freeze the exact clean source commit, run CI-equivalent checks, then build both
images. The ordinary build below runs source checks and npm production audit; it
does not replace candidate image/runtime/security acceptance.

Create an Artifact Registry Docker repository named `ocean-platform` in
`asia-northeast1`, then submit both images:

```sh
gcloud builds submit \
  --project=data-infra-infobio \
  --config=cloudbuild.yaml \
  .
```

Cloud Build produces images tagged with its build ID; resolve and record exact
digests for acceptance/deployment. The reusable candidate gate additionally
checks isolated PostgreSQL migration/restore, runtime imports, HTTP/auth
boundaries, non-root/tooling/capabilities, and full unsuppressed image scans:

```sh
gcloud builds submit --project=data-infra-infobio \
  --config=deploy/gcp/cloudbuild-candidate-qa.yaml \
  --substitutions=_QA_REPORT_PREFIX=candidate-qa .
```

Reports default to `gs://PROJECT_ID_cloudbuild/candidate-qa/BUILD_ID/`; a
reviewed release-specific `_QA_REPORT_PREFIX` can override that path. Scan exit
zero means report collection, not security acceptance. Review all findings
against #104 and require the patched dependency in the exact runtime image.
`cloudbuild-frontend.yaml` is an operator-only single-image rebuild helper; it
does not run the combined source, migration or image-acceptance gates.

## Render without deploying (bootstrap/recovery examples)

The renderer accepts only non-secret values and writes ignored
`*.rendered.yaml` files:

```sh
python scripts/render_gcp_templates.py \
  --image-tag=BUILD_ID \
  --public-app-url=https://oceaninfobio.com \
  --data-bucket=DATA_BUCKET \
  --oidc-client-id=GOOGLE_OAUTH_CLIENT_ID \
  --output-dir=/tmp/ocean-template-review
```

Review every rendered file before using `gcloud run services replace` or
`gcloud run jobs replace`. Rendering does not contact GCP.

## Required template values

Copy `service.template.yaml` to an untracked working file and replace:

- `PROJECT_ID`
- `PROJECT_NUMBER`
- `REGION`
- `ARTIFACT_REPOSITORY`
- `IMAGE_TAG`
- `CLOUD_SQL_INSTANCE`
- `PUBLIC_APP_URL`
- `OIDC_PROVIDER_ID`
- `OIDC_PROVIDER_NAME`
- `OIDC_ISSUER`
- `OIDC_CLIENT_ID`
- `DATA_BUCKET`

Do not put secret values in the rendered YAML. Create these Secret Manager
secrets and grant the Cloud Run service account Secret Accessor:

- `ocean-auth-secret`
- `ocean-internal-auth-secret`
- `ocean-oidc-client-secret`
- `ocean-database-url`

The `ocean-platform` service account needs only the roles required by the
configured revision:

- Cloud SQL Client
- Secret Manager Secret Accessor for the four named secrets
- Storage Object Viewer on the scientific-data bucket

The separate `ocean-jobs` identity receives Cloud SQL Client, access to the
database secret, and Storage Object User. Phase 6 adds Vertex AI User to this
job identity only; the serving identity receives it after evaluation passes
and general chat is explicitly approved.

The database URL for a Cloud SQL Unix socket has this shape:

```text
postgresql://USER:PASSWORD@/ocean_platform?host=/cloudsql/PROJECT_ID:REGION:CLOUD_SQL_INSTANCE
```

Add secret versions only after the OAuth client and database user exist.
Never pass secret values as renderer arguments or place them in rendered YAML.

## Cloud Run Jobs (bootstrap examples)

Render the migration, pipeline, embedding, and evaluation templates alongside
the service. The migration job runs the combined bootstrap command so both
Alembic-managed application tables and the current scientific corpus schema
exist before serving:

```sh
gcloud run jobs create ocean-migrate \
  --project=data-infra-infobio \
  --region=asia-northeast1 \
  --image=API_IMAGE \
  --command=python \
  --args=scripts/bootstrap_database.py,--json
```

The pipeline template has a safe dry-run default, explicitly disables
embeddings, has zero automatic retries, and starts with a 30-minute task
ceiling. After its preflight output is reviewed, override `--dry-run` with
`--execute` only for an operator-approved stage group. Database mutation must
retain `--no-embed`; model work belongs to Phase 6.

```sh
gcloud run jobs create ocean-pipeline \
  --project=data-infra-infobio \
  --region=asia-northeast1 \
  --image=API_IMAGE \
  --command=python \
  --args=scripts/run_pipeline.py,--dry-run,--no-embed,--json \
  --task-timeout=1800s \
  --max-retries=0
```

When `load_db` is selected, the runner inserts `backup_database` first. That
stage now creates and verifies a custom PostgreSQL archive and restores it into
a disposable database before the transactional upsert can start.

Both jobs also require the same database secret, Cloud SQL connection, data
volume, model settings, and service identity as the API sidecar. Add those
settings when the backing resources exist, then execute jobs manually.

### Phase 6 Vertex canary

The embedding job uses `gemini-embedding-001` with 768 output dimensions, so
the existing pgvector column does not need a dimension rewrite. Corpus and
query requests use `RETRIEVAL_DOCUMENT` and `RETRIEVAL_QUERY` respectively.
Authentication is workload identity through Application Default Credentials.

The checked-in job is non-billable by default: it runs `--dry-run --limit 16`.
After the new image and database migration pass, advance manually in this
order:

1. enable `aiplatform.googleapis.com` and grant `roles/aiplatform.user` only to
   `ocean-jobs`;
2. execute `scripts/update_embeddings.py --probe` to validate credentials and
   the 768-dimensional response without database writes;
3. execute `--limit 16`, verify 16 rows have Vertex provider/model/dimension
   provenance, and run known retrieval checks;
4. refresh the remaining rows, then repeat the command and require zero
   candidates;
5. run the evaluation job's one-question/one-mode default before expanding to
   the quick suite.

Provider failures abort the transaction. Automatic Cloud Run retries are zero,
SDK retry attempts are capped at three for 429/5xx responses, input truncation
is disabled, the SDK's hidden retry layer is disabled, each request has a
120-second timeout, and no failed batch falls back to duplicate sequential
calls.

For the citation-focused RAG path, Vertex reasoning tokens are disabled so the
1,600-token response ceiling is reserved for the visible grounded answer. Any
generation that ends with a non-`STOP` finish reason (including `MAX_TOKENS`)
is treated as a failed evaluation instead of being scored as a valid answer.
The evaluation CLI exits nonzero when any case records an error, so Cloud Run
cannot report a partially failed benchmark as a successful gate.
The shared grounded prompt also caps answers at 500 words and requires a valid
citation in each factual paragraph or bullet, preserving useful answers inside
the token ceiling instead of merely increasing the spending limit.

The bucket mount is a prototype compatibility bridge for the current
filesystem-oriented pipeline. Cloud Storage FUSE does not turn object storage
into a fully POSIX filesystem. Before production, move job state transitions
and atomic manifests to a database or native Cloud Storage object operations.

## Deployment safety

For an existing deployment, use [current operations](../../docs/RELEASE_0.7.4_OPERATIONS.md)
and the [audit checklist](../../docs/PRE_DEPLOYMENT_AUDIT_2026-10-06.md). Create
a zero-traffic revision from the fresh live definition, verify exact images and
normal candidate access, then promote after acceptance. Preserve existing IAM and
canonical/fallback callbacks; remove only any explicitly approved temporary
callback. The initial provisioning sequence below is historical bootstrap
guidance, not an instruction to reset production access.

Before replacing the service:

1. Render the template and review it without secrets.
2. Run the migration job and verify its successful execution.
3. Deploy the service without public access and run authenticated health checks.
4. Register the final OIDC callback URL.
5. Grant public invocation only to the frontend service after authentication
   succeeds.
6. Keep Cloud Run at one maximum instance until Cloud SQL pool behavior, model
   capacity, and seven days of cost are measured.
