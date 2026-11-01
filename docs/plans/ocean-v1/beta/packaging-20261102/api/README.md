# Independent beta API container preparation

This is additive packaging for `api.v1_host`, not a cloud image or a deployed
service. The parent host/API receipts accept the application behavior separately.
No prior application, migration, deployment or scientific file is changed.

The official Docker registry returned Python's `3.12.15-slim-bookworm` index
digest `sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70`;
the Linux/amd64 child is
`sha256:57d96f71de145a98e7ceca18ee4ade77bba4103a33a72dfaea026b23625c6bf0`.
The Dockerfile pins the multi-platform index and installs the existing locked
runtime requirements with `--require-hashes --only-binary=:all:`. Wheel/platform
availability, installed import behavior, image vulnerability scanning and actual
container startup remain build/acceptance gates; local checks do not claim them.

The source-only context follows static local imports, including package
initializers, from `api.v1_host` and app metadata. It includes all reviewed
migration Python sources, the Alembic config/template and explicit package
entry. It refuses fixture/test/data paths, `api/main.py`, symbolic-link sources,
uncommitted selected bytes and pre-existing output directories. It copies no
credentials, scientific files, entire checkout, virtualenv, frontend, legacy
deployment scripts or user-modified unrelated files. Package initializers create
a wider transitive code closure than the exposed API routes; inclusion is not
runtime activation or permission to acquire data/call models. Dynamic optional
imports and runtime data access still need actual image/integration evidence.

After the source commit exists, from the repository root:

```sh
.venv/bin/python deploy/gcp/beta/api/prepare_context.py \
  --revision FULL_REVIEWED_SOURCE_COMMIT \
  --output /private/tmp/ocean-v1-beta-api-NEW_CONTEXT
```

Every copied source must equal its Git object at that exact commit. The context
records the per-file source identity. A later reviewed Cloud Build can consume
only this context and produce an immutable digest. No upload or image build is
performed by this command or checkpoint. Do not submit the entire repository as
the build context; it contains unrelated and scientific work.

The image runs as UID/GID10001 with root-owned application bytes. Default `serve`
execs the separate ASGI factory on loopback8000, one process, no trusted proxy
headers or access logs. It does not migrate, start a worker or load scientific
fixtures. The ingress frontend must be a separate same-instance container;
port8000 must never be the public ingress port. API startup already requires
the exact live PostgreSQL head and current account authority.

Explicit production variables are:

- `DEPLOYMENT_ENV=production`, `OCEAN_V1_PROJECT_ID=ocean-v1-beta-20261101`.
- `OCEAN_V1_SQL_CONNECTION_NAME`: actual selected connection in this beta project,
  `asia-northeast1`, with instance name `ocean-v1-beta-*`; never inferred or created
  by the package. Cloud SQL itself is not yet provisioned by this checkpoint.
- `OCEAN_V1_DATABASE_URL`: private secret with `postgresql+psycopg2`, database
  `ocean_v1_beta`, an explicit `ocean_v1_*` user/password and either that exact
  Cloud SQL Unix socket or explicit loopback connector port. `DATABASE_URL` must
  be absent. Live connector routing/IAM remain separate acceptance requirements.
- `OCEAN_V1_DATABASE_USER`: exact corresponding independent user.
- `OCEAN_V1_HOST_CONFIG`: private absolute mounted config path; project, database
  and revision must match the packaged source manifest. The host enforces the
  remaining strict JSON schema. `OCEAN_V1_INTERNAL_AUTH_SECRET` is a separate
  private secret shared only with the frontend token signer.
- All four execution flags remain false. Read capability flags are explicit
  later deployment inputs; a bare host has unavailable scientific services.

No secret values are accepted in Docker build arguments, context or command
arguments. Keep password/DSN/internal signing values in runtime secret mounts.

The same image has a deliberately separate `migrate` operation. It additionally
requires database user `ocean_v1_migrator`, exact project/database confirmations,
and a fresh process. `--check-only` validates configuration without opening the
database. The actual operator first reads `current_database(), current_user`
through its validated DSN. Only then it sets `DATABASE_URL` inside its own process
before importing the unchanged Alembic environment, verifies the single packaged
head and upgrades explicitly to `20261027_0021`. There is no arbitrary revision,
downgrade, stamp, reset, table-create fallback or deployment-triggered migration.
An immutable candidate image, approved target/grants/backup, actual schema/history
readbacks and rollback procedure remain required before invoking it on GCP.

```sh
python /opt/ocean/beta_entry.py migrate \
  --confirm-project ocean-v1-beta-20261101 \
  --confirm-database ocean_v1_beta --check-only
```

The local verifier checks these accidental-target boundaries and imports the
selected source tree in an isolated temporary copy with connection attempts
blocked. It is not a Docker/Linux/container/cloud startup test or another native
migration rehearsal. Owned temporary files are removed by the context manager.
Run it without repeating unchanged application/native suites:

```sh
.venv/bin/python docs/plans/ocean-v1/beta/packaging-20261102/api/verify.py
```
