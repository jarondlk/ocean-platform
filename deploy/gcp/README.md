# GCP prototype deployment

This directory contains the templates, guarded preparation scripts, and
operational guidance for the live managed GCP prototype. Applying a template or
running a guarded script is always an explicit operator action; repository
checkout, rendering, tests, and Cloud Build do not provision runtime resources
automatically.

Follow [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md) for the phased deployment order,
integration gates, JPY 10,000 monthly prototype envelope, per-component
budgets, and technical cost ceilings. Cost controls are Phase 0 and must be in
place before the foundation or any runtime component is created.

## Current deployed milestone

Verified on 2026-08-25:

- project `data-infra-infobio`, region `asia-northeast1`;
- OCEAN Platform GitHub release `v0.2.1`;
- full Cloud Build `8e4c7d4b-f723-40ef-9278-1d647b54111d`;
- Cloud Run service `ocean-platform`, revision `ocean-platform-00004-8tb`,
  100% traffic;
- Artifact Registry `ocean-platform`; service accounts `ocean-platform` and
  `ocean-jobs`; secrets and jobs under the `ocean-*` prefix;
- Cloud SQL `ocean-postgres` / `ocean_platform` is PostgreSQL 16 and RUNNABLE;
- bucket `data-infra-infobio-ocean-data` contains the verified copied data;
- former `onagawa-source-chat` is private and deletion-protected
  `onagawa-postgres` is stopped for reversible rollback; the two legacy
  runtime identities are disabled;
- reviewed Artifact Registry cleanup is active for both repositories, and
  transient Cloud Build source archives expire after 30 days;
- minimum zero/maximum one service instance, concurrency 20; and
- GitHub `production` deployment status `success`.

See [`../../docs/GCP_RESOURCE_AUDIT.md`](../../docs/GCP_RESOURCE_AUDIT.md) for
the current inventory, absence checks, housekeeping controls, and the exact
rollback resources that still require explicit approval before deletion.

The live URL is
[`https://ocean-platform-469489188516.asia-northeast1.run.app`](https://ocean-platform-469489188516.asia-northeast1.run.app).

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

## Baseline APIs

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

Compute Engine remains optional. Enable Vertex AI only when executing the
Phase 6 credential probe and canary described below.

See [`AUTHENTICATION.md`](AUTHENTICATION.md) for the selected authentication
transfer, callback URL, provider identity rules, and IAP/Identity Platform
tradeoffs.

## Foundation preparation

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

Create an Artifact Registry Docker repository named `ocean-platform` in
`asia-northeast1`, then submit both images:

```sh
gcloud builds submit \
  --project=data-infra-infobio \
  --config=cloudbuild.yaml \
  .
```

Cloud Build produces immutable images tagged with its build ID. Replace
`IMAGE_TAG` in `service.template.yaml` with that ID.

## Render without deploying

The renderer accepts only non-secret values and writes ignored
`*.rendered.yaml` files:

```sh
python scripts/render_gcp_templates.py \
  --image-tag=BUILD_ID \
  --public-app-url=https://SERVICE_URL \
  --data-bucket=DATA_BUCKET \
  --oidc-client-id=GOOGLE_OAUTH_CLIENT_ID \
  --ollama-private-url=https://PRIVATE_MODEL_URL
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
- `OLLAMA_PRIVATE_URL`
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

## Cloud Run Jobs

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

Before replacing the service:

1. Render the template and review it without secrets.
2. Run the migration job and verify its successful execution.
3. Deploy the service without public access and run authenticated health checks.
4. Register the final OIDC callback URL.
5. Grant public invocation only to the frontend service after authentication
   succeeds.
6. Keep Cloud Run at one maximum instance until Cloud SQL pool behavior, model
   capacity, and seven days of cost are measured.
