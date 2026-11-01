# Independent v1 API host checkpoint — 2026-11-01 JST

Local implementation passes **35 tests and 9 actual disposable PostgreSQL
checks**. No cloud database, provider/model call, scientific execution or
deployment is performed by this checkpoint.

`api/v1_host.py` is a separate ASGI factory. It does not import `api.main`, use
`DATABASE_URL`, create tables, upgrade migrations or start background workers.
Its production entry requires an explicit config path and prefixed database and
signing-secret variables. Startup reads the actual PostgreSQL database name and
single Alembic head `20261027_0021`; missing or mismatched schema rejects startup.
Only a selected-project Cloud SQL socket or explicit loopback database connector,
an `ocean_v1_` database and an `ocean_v1_` database user are accepted. This static
check is not live IAM/network/credential-content attestation.

The host verifies short-lived HS256 tokens against its independent secret and
exact `ocean-v1-frontend` issuer / `ocean-v1-api` audience. It rejects mock
providers, multi-audience tokens, invalid identities and ambiguous headers.
Every request resolves the current user/role/status in the explicit database;
global `AUTH_MODE=disabled` cannot bypass it. **The first checkpoint requires
explicitly enrolled independent v1 accounts.** It does not import legacy accounts
or enroll users by matching email, and it does not yet add invitation acceptance.
The production frontend's `/me` check must deny unenrolled or revoked users.

Only the fixed read/status/history/evidence/artifact and cancellation-intent
routes are exposed. New research, synthesis, experiments, approvals and context
editing are rejected. Each request rechecks execution flags. A supplied bundle
with a queue, controller, model runtime or experiment executor is rejected.
The explicit database engine backs the shared PostgreSQL rate limiter; no global
limiter connection is used. Host, request size and query restrictions remain
independent of browser/session policy enforced by the frontend host.

`compose_read_services` builds real catalogue/browser/investigation/run/evidence/
answer services from explicit sealed registrations, snapshot store, current
scientific/access/discovery policy and cursor key. Optional proposal histories
require explicit environment descriptors. There is no default dataset authority,
snapshot discovery, fixture import or legacy fallback. The bare production
entry has no scientific provider configured and correctly reports unavailable
catalogue/research capabilities. It is not a fabricated empty catalogue or an
accepted scientific-data deployment. Supplying the actual reviewed provider and
independent account enrollment remain integration/configuration gates.

## Production entry contract

The non-secret [pending example](api-host.pending.json) requires the candidate
revision before use. Credentials are environment values mounted by the actual
runtime; never place their values in this repository.

```sh
OCEAN_V1_HOST_CONFIG=/absolute/private/path/api-host.json \
  .venv/bin/uvicorn api.v1_host:create_from_environment --factory \
  --host 127.0.0.1 --port 8000
```

Also provide `OCEAN_V1_DATABASE_URL` and `OCEAN_V1_INTERNAL_AUTH_SECRET` privately.
Set the relevant read capability flags explicitly; all four execution flags
must remain false. The sidecar accepts only configured loopback Host values.
The frontend proxy uses root `/me`, `/v1/runtime`, `/catalogue/*` and `/research/*`
API paths with a fresh internal token, no browser cookies or user bearer token.

## Actual acceptance and limitations

- Unit/service tests exercise authentication, account/role changes, revocation,
  exact token/Host boundaries, closed work/legacy paths, body bounds, source
  binding, no migration/implicit database fallback and a real four-family sealed
  fixture through the new composition factory. A durable count run and retained
  receipt are prepared before the read-only host is installed; its HTTP status,
  receipt listing/reopen and cross-owner denial pass without dispatch wiring.
- The native production entry uses a new owned PostgreSQL18 cluster. Actual
  fresh migrations are an explicit operator subprocess. The entry uses its
  prefixed DSN despite a deliberately unusable global legacy DSN; current user,
  revocation and shared limiter are verified, while the schema/head/user inventory
  remain unchanged by host startup. The server is stopped, status3/closed port/
  absent PID observed, and all owned temporary files removed.
- First unit iterations corrected test-only missing idempotency/provider/DTO
  assumptions. The earlier 34-case pass and native receipt remain historical;
  exact-audience hardening adds the 35th case and a fresh native capture. Original
  accepted native source snapshots remain under `native-accepted/`.
- The first native invocation was sandbox-denied at port probing before any
  server started. Owned empty directories were removed; the separately allowed
  loopback run passed. No permission denial is relabelled an application failure.
- SQLite injection is an explicit test seam and is rejected unless
  `DEPLOYMENT_ENV=test`. It is never available through the production entry.
  Actual Cloud Run/Cloud SQL/OAuth/snapshot wiring and all live release gates
  remain unrun; this receipt is not live readiness or deployment acceptance.

```sh
DEPLOYMENT_ENV=test AUTH_MODE=disabled .venv/bin/python -m pytest tests/test_v1_host.py -q
.venv/bin/python docs/plans/ocean-v1/beta/bootstrap-20261101/verify.py
```

Stateful native reproduction requires a new simple run directory:

```sh
DEPLOYMENT_ENV=test AUTH_MODE=disabled .venv/bin/python \
  docs/plans/ocean-v1/beta/bootstrap-20261101/native_rehearsal.py \
  --run-directory native-new-run
```

The harness refuses existing output directories and may require local loopback
permission. Do not repeat it for unchanged source verification.
