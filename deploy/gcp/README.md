# GCP prototype deployment

This directory prepares the application for a managed GCP prototype without
provisioning resources from the repository.

## Target topology

- One Cloud Run service with Next.js as the ingress container and FastAPI as a
  localhost sidecar.
- Cloud SQL for PostgreSQL 16 with the `vector` extension.
- Cloud Storage mounted at `/mnt/onagawa-data` for scientific artifacts and job
  outputs.
- Secret Manager for the database URL, signing secrets, and OIDC client secret.
- Cloud Run Jobs for migrations, ingestion, embedding refresh, and evaluation.
- A private Ollama endpoint for the first prototype. `model_runtime.py` is the
  provider boundary for a future Vertex AI implementation.

The serving revision sets `JOB_EXECUTION_MODE=external`. This deliberately
prevents an autoscaled web instance from starting daemon-thread pipeline or
evaluation work. Operators execute the existing CLI scripts as Cloud Run Jobs.

## Baseline APIs

Enable these after billing is linked:

```sh
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  servicenetworking.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=data-infra-infobio
```

Compute Engine and Vertex AI remain optional until the model-hosting decision
is final.

## Build

Create an Artifact Registry Docker repository named `onagawa-source-chat` in
`asia-northeast1`, then submit both images:

```sh
gcloud builds submit \
  --project=data-infra-infobio \
  --config=cloudbuild.yaml \
  .
```

Cloud Build produces immutable images tagged with its build ID. Replace
`IMAGE_TAG` in `service.template.yaml` with that ID.

## Required template values

Copy `service.template.yaml` to an untracked working file and replace:

- `PROJECT_ID`
- `REGION`
- `ARTIFACT_REPOSITORY`
- `IMAGE_TAG`
- `CLOUD_SQL_INSTANCE`
- `PUBLIC_APP_URL`
- `OIDC_ISSUER`
- `OIDC_CLIENT_ID`
- `OLLAMA_PRIVATE_URL`
- `DATA_BUCKET`

Do not put secret values in the rendered YAML. Create these Secret Manager
secrets and grant the Cloud Run service account Secret Accessor:

- `onagawa-auth-secret`
- `onagawa-internal-auth-secret`
- `onagawa-oidc-client-secret`
- `onagawa-database-url`

The `onagawa-app` service account needs only the roles required by the
configured revision:

- Cloud SQL Client
- Secret Manager Secret Accessor for the four named secrets
- Storage Object User on the scientific-data bucket

Use a separate job service account later if pipeline operators need broader
write or model-invocation permissions.

The database URL for a Cloud SQL Unix socket has this shape:

```text
postgresql://USER:PASSWORD@/onagawa_rag?host=/cloudsql/PROJECT_ID:REGION:CLOUD_SQL_INSTANCE
```

## Cloud Run Jobs

Use the API image with an overridden command instead of running migrations or
durable work during web-container startup:

```sh
gcloud run jobs create onagawa-migrate \
  --project=data-infra-infobio \
  --region=asia-northeast1 \
  --image=API_IMAGE \
  --command=python \
  --args=-m,alembic,upgrade,head
```

Create the pipeline job with a safe dry-run default:

```sh
gcloud run jobs create onagawa-pipeline \
  --project=data-infra-infobio \
  --region=asia-northeast1 \
  --image=API_IMAGE \
  --command=python \
  --args=scripts/run_pipeline.py,--dry-run,--json \
  --task-timeout=3600s \
  --max-retries=1
```

Both jobs also require the same database secret, Cloud SQL connection, data
volume, model settings, and service identity as the API sidecar. Add those
settings when the backing resources exist, then execute jobs manually.

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
6. Keep Cloud Run maximum instances low until Cloud SQL pool behavior and model
   capacity are measured.
