# Production Deployment

## Managed GCP Prototype

The managed GCP prototype is live. It uses a public Cloud Run frontend with a
private FastAPI sidecar, Cloud SQL PostgreSQL/pgvector, Cloud Storage, Secret
Manager, Cloud Run Jobs, Google OIDC, and Vertex AI. The production application
URL is
[`https://ocean-platform-469489188516.asia-northeast1.run.app`](https://ocean-platform-469489188516.asia-northeast1.run.app).
See [`deploy/gcp/README.md`](../deploy/gcp/README.md) for templates and current
operations.

Current release record as of 2026-09-03:

- OCEAN Platform [GitHub release `v0.4.0`](https://github.com/jarondlk/ocean-platform/releases/tag/v0.4.0),
  source `a63885a573b18eb92c184fb88fdb85b5aae3cb09`, build
  `76b31adb-28d6-4daa-a9cc-f114d36bd753`, revision `ocean-platform-v040-a63885a`;
- previous revision `ocean-platform-v030-1bb38b8` and pre-release backup retained;
  review corpus/publication compatibility before rollback, without schema
  downgrade or overwriting later user/chat records;
- Cloud Run service `ocean-platform`, with minimum zero, maximum one instance,
  concurrency 20, and an immutable release-tagged image;
- Artifact Registry `ocean-platform`, runtime identities `ocean-platform` and
  `ocean-jobs`, Cloud SQL `ocean-postgres` / `ocean_platform`, OCEAN secrets,
  OCEAN jobs, and bucket `data-infra-infobio-ocean-data`;
- former `onagawa-source-chat` service private and deletion-protected
  `onagawa-postgres` stopped as reversible rollback resources, with both
  legacy runtime identities disabled;
- keep-five/delete-after-30-days Artifact Registry cleanup active and 30-day
  expiry applied to transient Cloud Build source archives;
- 325 documents/embeddings including the unknown-classification pilot;
  schema head `20260903_0008`, verified backup/isolated restore and authenticated
  source-citation checks. See [operations and known limitations](RELEASE_0.4.0_OPERATIONS.md).

The dated GCP inventory and remaining destructive retirement candidates are
recorded in [`GCP_RESOURCE_AUDIT.md`](GCP_RESOURCE_AUDIT.md).

The standalone Compose topology below remains the supported self-hosted
alternative. Its configuration examples do not describe the current GCP
service.

The required migration sequence, integration gates, and cost controls are in
[`deploy/gcp/MIGRATION_PLAN.md`](../deploy/gcp/MIGRATION_PLAN.md). Install the
project budget and Cloud Run spend cap before enabling runtime APIs.

The Cloud Run serving revision uses `JOB_EXECUTION_MODE=external`. Database
migrations, pipeline runs, and evaluations belong in run-to-completion jobs;
they must not be launched as daemon threads or startup migrations in an
autoscaled web instance.

The Evaluation page can browse runs, reports, analytics, questions, and
comparisons. Its start controls currently surface the external-runner boundary;
operators execute the bounded `ocean-evaluation` Cloud Run Job until a
least-privilege UI-to-job bridge is implemented.

## Standalone Compose Topology

The production Compose file is intended for a single application host:

```text
Internet
  -> TLS reverse proxy
  -> 127.0.0.1:3000 (Next.js)
  -> private Compose network
       -> FastAPI:8000
       -> PostgreSQL:5432
       -> approved private Ollama endpoint
```

Do not use `compose.yml` or `deploy/compose/app.yml` as production
definitions. They intentionally publish development ports, mount the repository,
and enable reload behavior. `deploy/compose/production.yml` publishes only
Next.js to host loopback.

## Required Configuration

Copy `deploy/env/production.example` to a secret-managed location outside the
repository, replace every placeholder, and pass that populated file explicitly
with `--env-file`. At minimum, set:

```dotenv
DEPLOYMENT_ENV=production
AUTH_MODE=required
AUTH_ALLOWED_PROVIDERS=oidc
PERSIST_LOCAL_CHAT=false
ENABLE_MOCK_LOGIN=false

AUTH_URL=https://rag.example.org
AUTH_TRUST_HOST=false
AUTH_SECRET=<independent random value>
INTERNAL_AUTH_SECRET=<different independent random value>
INTERNAL_AUTH_ISSUER=ocean-platform-frontend
INTERNAL_AUTH_AUDIENCE=ocean-platform-api

OIDC_ISSUER=https://identity.example.org
OIDC_CLIENT_ID=<provider client id>
OIDC_CLIENT_SECRET=<provider client secret>
OIDC_PROVIDER_NAME=Managed identity provider
OIDC_PROVIDER_ID=oidc

CORS_ORIGINS=https://rag.example.org
POSTGRES_USER=ocean
POSTGRES_PASSWORD=<random database password>
POSTGRES_DB=ocean_platform
DATABASE_URL=postgresql://ocean:<url-encoded-password>@postgres:5432/ocean_platform
OLLAMA_BASE_URL=http://<private-ollama-host>:11434
```

Generate the two signing secrets independently:

```bash
openssl rand -base64 48
openssl rand -base64 48
```

Do not commit the generated values. Restrict the environment file to the service
account. If the reverse proxy must provide the public host dynamically, enable
`AUTH_TRUST_HOST=true` only when the proxy overwrites untrusted `Host`,
`Forwarded`, and `X-Forwarded-*` headers.

Select a managed OIDC provider that supplies hosted email/password sign-in,
password recovery, MFA, lockout, and abuse protection. The application login
page displays one neutral **Sign in** action; it does not collect or store
production passwords. `ENABLE_MOCK_LOGIN` is only a local test harness and
cannot be enabled in staging or production.

Register this exact provider callback:

```text
https://rag.example.org/api/auth/callback/oidc
```

## Start and Verify

Validate expansion before starting:

```bash
podman compose \
  --env-file /secure/path/onagawa-production.env \
  -f deploy/compose/production.yml \
  config --quiet
```

Start the services:

```bash
podman compose \
  --env-file /secure/path/onagawa-production.env \
  -f deploy/compose/production.yml \
  up -d --build
```

The API container applies Alembic migrations before starting FastAPI. Bootstrap
the first administrator from an API container:

```bash
podman compose \
  --env-file /secure/path/onagawa-production.env \
  -f deploy/compose/production.yml \
  exec api \
  python scripts/invite_user.py admin@example.org \
  --role admin \
  --account-type internal
```

Verify:

- the reverse proxy returns HTTPS only;
- `/health/live` is reachable through internal monitoring;
- unauthenticated access to `/stats` is rejected;
- the API and database host ports are closed;
- viewer, researcher, and admin navigation and API permissions match
  `docs/SECURITY.md`;
- a suspended user is rejected on the next request;
- security headers are present on an application response.

## TLS and Proxy

Terminate TLS at a maintained reverse proxy and forward only to
`127.0.0.1:3000`. Redirect HTTP to HTTPS. Add HSTS only after the HTTPS
configuration and certificate renewal path have been tested; an incorrect
long-lived HSTS policy can lock users out.

Do not route external traffic to FastAPI, PostgreSQL, or Ollama. The frontend
proxy is the browser-to-API boundary and attaches the short-lived internal
identity token.

## Backups and Restore

Back up the complete PostgreSQL database, not only scientific corpus tables.
The application metadata tables contain users, invitations, chat history,
feedback, and audit events.

The pipeline automatically creates and verifies a PostgreSQL custom-format
archive before a database mutation. To exercise the same path directly:

```bash
python scripts/database_backup.py create --label pre-release --restore-test
python scripts/database_backup.py verify data/backups/<archive>.dump
python scripts/database_backup.py restore-test data/backups/<archive>.dump
```

Each archive is written atomically with a SHA-256 sidecar manifest, table row
counts, and archive metadata. `--restore-test` restores into a disposable
database, compares recorded counts, and drops the disposable database. The
production API image includes PostgreSQL client tools and
`deploy/compose/production.yml` persists `/app/data/backups` in a dedicated
volume.

Before launch, operators must still:

1. schedule the verified backup command or managed PostgreSQL backups;
2. define retention and off-host storage;
3. encrypt backup media and restrict access;
4. apply migrations to the restored copy;
5. verify user, chat, feedback, and audit-event counts;
6. record recovery time and recovery point objectives.

Generated data artifacts under `data/` require a separate backup decision.
Corpus data can often be regenerated, while provenance manifests and evaluation
run history may be operationally important.

## Secret Rotation

Rotate secrets after suspected exposure and on the operator's normal schedule:

1. stop new traffic;
2. rotate the OIDC client secret at the provider;
3. generate new, distinct `AUTH_SECRET` and `INTERNAL_AUTH_SECRET` values;
4. rotate the database password and update `DATABASE_URL`;
5. restart the frontend and API together;
6. revoke existing provider sessions when warranted;
7. review audit events and logs for suspicious activity.

Changing signing secrets invalidates active sessions or in-flight internal
tokens. The internal token lifetime is at most 120 seconds.

## Scaling

Production and staging rate-limit counters are stored atomically in PostgreSQL
and are shared by API workers. Horizontal deployment must still point every
worker at the same migrated database, and an internet-facing gateway should
apply additional connection and volumetric limits.

## Rollback

Application rollback must not automatically downgrade the database. Keep the
previous image, create and restore-test a database backup before migrations,
and confirm that the previous code can read the upgraded schema. Use Alembic
downgrade only after reviewing the migration's data-loss behavior.
