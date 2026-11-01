# Controlled beta database operator

This additive package prepares the independent `ocean_v1_beta` database on the
selected private SQL instance. It has no general SQL, arbitrary target, reset,
downgrade, import, account-enrollment, scientific-provider or C23-activation
operation. It changes no application/migration source or previous receipt.

Local acceptance: **26 guard/finalizer checks and 23 actual owned native checks
pass**. Native PostgreSQL18.3/pgvector0.8.7 verifies fresh extension/role setup,
actual SCRAM connections, migration as a restricted object owner, exact serving
grants, limiter writes, forbidden account/history/C23/DDL access, refusal to
overwrite unexpected state and an actual loopback HTTP shutdown transport.
The server is stopped; status3, closed port, absent PID and owned temporary
directory removal are recorded. This is not Cloud SQL16 or actual proxy-image
acceptance. No cloud call, image build or real-data/account operation occurs.

## Immutable package and source contract

The operator image derives only from an exact beta API image digest; it adds two
root-owned files and retains nonroot UID/GID10001. Source-only context generation
checks each owned source against its exact Git object and refuses existing output
or mutable/foreign API references. Its manifest binds the API revision/digest
and the later operator commit separately. After committing:

```sh
.venv/bin/python deploy/gcp/beta/operator/prepare_context.py \
  --revision FULL_OPERATOR_COMMIT \
  --api-revision FULL_ACCEPTED_API_SOURCE_COMMIT \
  --api-image asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/api@sha256:EXACT_API_DIGEST \
  --output /private/tmp/ocean-v1-beta-operator-NEW_CONTEXT
```

Use that emitted immutable API reference as the Docker `API_IMAGE` build argument.
Only the generated context may be submitted; it contains no credentials or entire
repository. The Dockerfile itself is not an image-reference validator when used
outside this guarded procedure. Image build/audit/startup remain parent-owned
gates. No local build or immutable operator image is claimed here.

Every invocation requires one explicit stage and exact nonsecret confirmations:

```sh
python /opt/ocean/beta_operator.py bootstrap \
  --confirm-project ocean-v1-beta-20261101 \
  --confirm-database ocean_v1_beta \
  --confirm-source FULL_ACCEPTED_API_SOURCE_COMMIT \
  --confirm-operator FULL_OPERATOR_COMMIT
```

`migrate`, `finalize` and `readback` are separately selected stages with the same
confirmation contract. There is no default operation. Missing/invalid stage or
confirmation rejects work and still attempts the fixed local proxy finalizer.

## Explicit private environment

All stages require `DEPLOYMENT_ENV=production`,
`OCEAN_V1_PROJECT_ID=ocean-v1-beta-20261101`,
`OCEAN_V1_SQL_CONNECTION_NAME=ocean-v1-beta-20261101:asia-northeast1:ocean-v1-beta-sql`,
and exact `OCEAN_V1_SOURCE_REVISION`/`OCEAN_V1_OPERATOR_REVISION` matching both
packaged manifests and confirmations. All four execution flags stay false.
`DATABASE_URL` must be absent; no prior imported application config is accepted.

`OCEAN_V1_OPERATOR_DATABASE_URL` is a private mounted/runtime-secret DSN with
driver `postgresql+psycopg2`, host `127.0.0.1`, port5432 and database
`ocean_v1_beta`. No arbitrary query options/socket/host/port are accepted;
`sslmode=disable` is allowed only for this same-instance proxy leg. SQL Auth
Proxy must encrypt the private upstream connection; this is not permission to
expose plaintext PostgreSQL to a network. DSN/password values never belong in
argv, logs, source, context, Docker arguments or chat.

The service identities, secret access and stage credentials must be separate:

| Stage | SQL principal and private inputs |
|---|---|
| bootstrap | New-instance `postgres` DSN; distinct generated `OCEAN_V1_MIGRATOR_PASSWORD` and `OCEAN_V1_SERVING_PASSWORD` (48–128 URL-safe characters) |
| migrate | `ocean_v1_migrator` DSN only; no bootstrap/serving passwords |
| finalize | `ocean_v1_migrator` DSN only, because it owns the migrated objects |
| readback | Explicit bootstrap `postgres` DSN, metadata-only report |

The operator emits only fixed errors and bounded role/table/head/extension
metadata. A migration child receives only its own database DSN through its
environment, a fixed existing entry/target command and a 480-second deadline;
its raw output is captured rather than copied into public operator output.
An error retains the target for explicit safe inspection, never resets it.

## Stage behavior and privilege boundaries

Bootstrap first checks actual database, current/session user and fresh state
under a transaction-scoped advisory lock. It refuses existing `ocean_v1_*`
roles, public relations/functions, nondefault extensions or unexpected user
schemas; the new database must belong to `postgres`. It creates the actual
available `vector` extension, records its observed version and creates exactly
two distinct password roles with all administrative attributes false. Only any
automatic creator membership of these newly created roles is revoked; no
pre-existing role is edited. It verifies zero memberships/members afterwards.

Database/public-schema ownership stays with the trusted bootstrap principal;
the migrator receives CONNECT and public USAGE/CREATE. The serving role receives
only CONNECT/USAGE initially. PUBLIC database privileges and schema privileges
are revoked in this new database. Both roles use `public, pg_catalog` so existing
unqualified application migrations resolve their explicitly controlled writable
schema; serving cannot create there. No runtime role owns DB/schema/tables.

Migration first verifies that actual restricted migrator identity and public
schema, then changes its database-wide default function ACL so future functions
have no PUBLIC EXECUTE. A schema-specific REVOKE cannot subtract PostgreSQL's
global function default. It then invokes the already accepted guarded API
`beta_entry.py migrate` in a fresh subprocess to the exact head
`20261027_0021`. Migrations own their own objects. They do not create scientific
corpus tables or enroll users. An interrupted migration remains inspectable;
there is no automatic downgrade or filled-schema reset.

Finalize runs as that restricted object owner. It requires the exact live head,
restricted role attributes, zero memberships and no runtime ownership. It refuses
unexpected existing table/function/creation rights rather than silently removing
them. It grants serving only SELECT on `public.app_user` and
`public.alembic_version`, and SELECT/INSERT/UPDATE on `public.rate_limit_bucket`.
This serves the closed current-account/readiness host stage, not full catalogue,
retained history, cancellation or dispatch. Broad grants and real user enrollment
require their own explicit subsequent implementation and evidence.

## Private proxy/job lifecycle

Run one task, parallelism1, max-retries0, timeout600s. Configure Direct VPC egress
on the existing beta network/subnet with private-ranges-only, and an official
digest-pinned Cloud SQL Auth Proxy sidecar using the exact connection name,
`--private-ip --address=127.0.0.1 --port=5432 --quitquitquit`. Attach only the
specific connector/secret permissions for that stage. No service-account key,
public database endpoint, VPC connector or NAT is supplied. The proxy needs a
tested real private SQL startup probe before operator work; Direct VPC startup
and SQL connectivity can lag. Configuring a dependency without an effective
probe is not a readiness guarantee.

On completion, failure or malformed invocation, the operator's finalizer POSTs
only to `http://127.0.0.1:9091/quitquitquit`, with bounded retries/timeouts. Failure
to receive2xx returns exit3 even when the SQL stage committed. Acknowledgement
means shutdown was requested; actual proxy process exit still must be observed
from Cloud Run per-container execution readbacks. The overall job may be accepted
only when both containers exit successfully. A timeout or stopped job is not
accepted as a completed stage. The admin endpoint is loopback-only and must
never enter a frontend/public proxy allowlist. No job/image/proxy is deployed by
this checkpoint.

## Evidence and outstanding qualification

`native-attempt01` preserves the first candidate's migration failure after six
passing checks and complete cleanup; its operator source is retained. The role
search path was corrected before the second run. The unfortunately named
`native-accepted` directory is **a historical failed second attempt**, not the
accepted evidence: it passed migration then exposed inherited function EXECUTE
rights at the finalization gate. Its original receipt/source remain unchanged.
`native-final/receipt.json` preserves the intermediate passing 21-check result
after correcting the default function ACL. The final delegation-rights hardening
also refuses an otherwise allowed table privilege if it carries GRANT OPTION.
`native-final-grants/receipt.json` is the current accepted 23-check result; its two
additional actual tests verify delegation refusal and preservation for inspection.
No failure is relabelled as passing or overwritten.

Cloud SQL's limited `cloudsqlsuperuser` must still pass actual fresh extension,
role-creation and grant qualification. Native superuser bootstrap is not proof
of those managed-service capabilities. The finalization/migration stages do use
actual nonadministrative owner connections locally. C23's NOLOGIN function-owner
bootstrap and restricted execution roles are deliberately absent. Its separate
Cloud SQL privilege qualification gate remains closed; no membership/ownership
check is weakened. Actual OAuth/identity enrollment, scientific services, queue,
worker, recovery/release gates and all original twenty gates remain independent.

```sh
.venv/bin/python docs/plans/ocean-v1/beta/packaging-20261102/operator/verify.py
```

Do not repeat the successful stateful rehearsal for unchanged source. Its harness
requires a new output directory and owned loopback permission, copies the already
installed pgvector control/SQL files into its own temporary cluster configuration,
and never installs or edits Homebrew/system files. It tests no GCP or real data.
