# Dedicated database identities and private jobs — 2026-11-02 JST

**Plan only. No GCP write, credential generation, job creation or execution is
performed by this document.** Applies only to `ocean-v1-beta-20261101` /
`534831104543`, Tokyo `ocean-v1-beta-sql`, `ocean_v1_beta` and the four named
database jobs. The user-authorized root operator owns actual application.
Do not change legacy projects, organization policy or default Compute identity.

The current renderer confirms API source
`7924a28e919b1fb751890c694f7b1f9b26b104ff` and password-safe operator source
`8b06a1b993cbca53ded0a9e79e1acb5ba58f3089`. The original50-check setup receipt
and its old756renderer bytes remain historical; use the separate operator
revision amendment. Actual accepted operator image digest and completed
credential-installation receipt remain required inputs, not values invented by
this plan. `plan.json` pins the inspected local inputs and leaves those actual
deployment inputs unresolved.

## Exact identities and permissions

Create only these two service accounts after a fresh GET returns NOT_FOUND,
not PERMISSION_DENIED. If a name already exists, stop creation and inspect its
identity, enabled state, keys and effective bindings. A preserved prior
root-created account may be reused only after its actual receipt and exact
baseline match; unexpected existing state is not silently adopted or reset.

```sh
gcloud iam service-accounts create ocean-v1-beta-db-bootstrap \
  --display-name='OCEAN beta database bootstrap' \
  --project=ocean-v1-beta-20261101 --quiet
gcloud iam service-accounts create ocean-v1-beta-db-migrator \
  --display-name='OCEAN beta database migrator' \
  --project=ocean-v1-beta-20261101 --quiet
```

Each receives `roles/cloudsql.client` at the **beta project** with this exact
instance condition, rather than an unconditional project-wide grant:

```text
resource.name == 'projects/ocean-v1-beta-20261101/instances/ocean-v1-beta-sql' && resource.service == 'sqladmin.googleapis.com'
```

Cloud SQL's [PostgreSQL IAM Conditions guide](https://docs.cloud.google.com/sql/docs/postgres/iam-conditions)
documents this resource-name/service restriction for the Client role. The role
provides connection and instance metadata permissions; its lowest grant level
is the project. A conditional project binding restricts it to this instance.
[Role definition](https://docs.cloud.google.com/iam/docs/roles-permissions/cloudsql).
No custom role, Admin, Editor, Owner, instanceUser, Token Creator, service-account
key or default-identity grant is proposed. SQL username/password authentication
remains distinct from this connector authorization.

The root may apply the two reviewed bindings sequentially:

```sh
gcloud projects add-iam-policy-binding ocean-v1-beta-20261101 \
  --member=serviceAccount:ocean-v1-beta-db-bootstrap@ocean-v1-beta-20261101.iam.gserviceaccount.com \
  --role=roles/cloudsql.client \
  --condition="expression=resource.name == 'projects/ocean-v1-beta-20261101/instances/ocean-v1-beta-sql' && resource.service == 'sqladmin.googleapis.com',title=ocean-v1-beta-sql-only" \
  --quiet --format=json
gcloud projects add-iam-policy-binding ocean-v1-beta-20261101 \
  --member=serviceAccount:ocean-v1-beta-db-migrator@ocean-v1-beta-20261101.iam.gserviceaccount.com \
  --role=roles/cloudsql.client \
  --condition="expression=resource.name == 'projects/ocean-v1-beta-20261101/instances/ocean-v1-beta-sql' && resource.service == 'sqladmin.googleapis.com',title=ocean-v1-beta-sql-only" \
  --quiet --format=json
```

Grant `roles/secretmanager.secretAccessor` only on the following four individual
secrets. No project-wide secret role or new secret version is part of this plan.
Secret-level binding is supported by the official
[Secret Manager access-control guide](https://docs.cloud.google.com/secret-manager/docs/access-control).

| Account | Exact secret resources |
|---|---|
| `ocean-v1-beta-db-bootstrap` | `ocean-v1-beta-bootstrap-database`, `ocean-v1-beta-migrator-password`, `ocean-v1-beta-serving-password` |
| `ocean-v1-beta-db-migrator` | `ocean-v1-beta-migrator-database` |

Each of the four reviewed grant commands has this form, with the account and
secret chosen only from that table:

```sh
gcloud secrets add-iam-policy-binding ocean-v1-beta-bootstrap-database \
  --member=serviceAccount:ocean-v1-beta-db-bootstrap@ocean-v1-beta-20261101.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor --condition=None \
  --project=ocean-v1-beta-20261101 --quiet --format=json
```

`plan.json` contains all four exact argument arrays. The two accounts get no
auth/internal/serving-DSN/OAuth secret access. Public serving and worker runtime
grants are deferred. Both sidecars in a job share its task identity, so the
bootstrap identity can access its three authorized secrets even in the readback
job that mounts only its DSN. Revoke only the two newly added role-password
Accessor memberships after accepted bootstrap; retain bootstrap-DSN access for
the required readbacks. Do not rerun bootstrap after that reduction. Preserve
versions and logs, and do not edit unrelated IAM members.

## Baselines and readbacks before job creation

Work under one beta configuration writer. Before any change, verify current
project ID/number, active SQL target, no competing SQL/job operation and the
completed seven-version metadata receipt. Read the beta project IAM policy
including conditions/version3 and the four secret policies. Confirm both new
principals have no unexpected project or inherited grants; permission errors
are gates, not absence. Read existing Cloud Run service-agent access instead of
granting broad image/network permissions to the runtime accounts.

Use these metadata-only readbacks before and after each relevant mutation:

```sh
gcloud projects describe ocean-v1-beta-20261101 --format=json
gcloud projects get-iam-policy ocean-v1-beta-20261101 --format=json
gcloud iam service-accounts describe ocean-v1-beta-db-bootstrap@ocean-v1-beta-20261101.iam.gserviceaccount.com --project=ocean-v1-beta-20261101 --format=json
gcloud iam service-accounts describe ocean-v1-beta-db-migrator@ocean-v1-beta-20261101.iam.gserviceaccount.com --project=ocean-v1-beta-20261101 --format=json
gcloud iam service-accounts keys list --iam-account=ocean-v1-beta-db-bootstrap@ocean-v1-beta-20261101.iam.gserviceaccount.com --managed-by=user --project=ocean-v1-beta-20261101 --format=json
gcloud iam service-accounts keys list --iam-account=ocean-v1-beta-db-migrator@ocean-v1-beta-20261101.iam.gserviceaccount.com --managed-by=user --project=ocean-v1-beta-20261101 --format=json
gcloud secrets get-iam-policy ocean-v1-beta-bootstrap-database --project=ocean-v1-beta-20261101 --format=json
```

Repeat the secret policy GET for the other three fixed names. Require zero
user-managed keys, correct project/unique account IDs, enabled accounts, exact
conditional connector membership and exact secret-scoped Accessor membership.
Compare each result with the immediately preceding approved baseline and
preserve every unrelated binding. Reject concurrent/unexpected drift; do not
overwrite an entire policy from a stale file. The deployer uses its existing
authorized permissions to attach these identities and create/run jobs. A
permission denial does not authorize adding broad roles to it or to a sidecar.

## Four create-only Cloud Run v2 jobs

After actual image/build and credential receipts are verified, render a **new**
directory with the current source-pinned renderer. Do not use the synthetic
fixtures, a mutable image tag or `latest` secret versions. Every job must name
the accepted operator digest, the fixed official proxy digest, the above
source revisions and actual numeric version refs.

Use the official [v2 create method](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs/create),
not gcloud v1 `jobs replace`. For each exact job ID below, GET first and require
NOT_FOUND; a403 or an unexpected existing job closes the gate. An exact prior
root-created job may only be reused after comparing its preserved receipt,
generation and complete effective specification. Never silently patch/reset it.

```text
GET  https://run.googleapis.com/v2/projects/ocean-v1-beta-20261101/locations/asia-northeast1/jobs/JOB_ID
POST https://run.googleapis.com/v2/projects/ocean-v1-beta-20261101/locations/asia-northeast1/jobs?jobId=JOB_ID&validateOnly=true
POST https://run.googleapis.com/v2/projects/ocean-v1-beta-20261101/locations/asia-northeast1/jobs?jobId=JOB_ID
```

The POST body is exactly its newly rendered `JOB_ID.json`; no credential value
or execution override is supplied. Validation and creation return operations
that must be read to completion and checked for errors. Creation does not run
the job. Send any access token only through a root-controlled in-memory HTTPS
Authorization header; never put it in argv, shell interpolation, a file or a
receipt. The credential installer's fixed API allowlist is not a Cloud Run
transport and must not be bypassed or broadened casually.

| Exact job ID | Task identity | Mounted credentials |
|---|---|---|
| `ocean-v1-beta-db-bootstrap` | bootstrap | bootstrap DSN and two role passwords |
| `ocean-v1-beta-db-readback` | bootstrap | bootstrap DSN only |
| `ocean-v1-beta-db-migrate` | migrator | migrator DSN only |
| `ocean-v1-beta-db-finalize` | migrator | migrator DSN only |

After all four creations, GET every job and compare the provider's effective
specification with its source-bound render before any execution: one task,
parallelism1, retries0, timeout600s, Gen2, exact service account, both immutable
images, fixed stage/confirmation args, four execution flagsfalse, correct
numeric secret refs, explicit Direct VPC beta network/subnet and
PRIVATE_RANGES_ONLY egress. The proxy must retain private-IP loopback5432,
admin9091/quitquitquit, health9090 and the bounded readiness startup probe;
operator depends on `sql-proxy`. No public SQL endpoint, service URL, invoker
grant, trigger or execute-on-create option is added.

## Explicit stage sequence and stop conditions

Creating four jobs authorizes no automatic parallel bootstrap. Root selects
each execution only after the preceding gate passes. Use
`gcloud run jobs execute EXACT_JOB --region=asia-northeast1 --project=ocean-v1-beta-20261101 --wait`
without overrides, with immediate job-generation/spec comparison before each
invocation. Retain the exact execution name and read it and its task/container
statuses; a CLI exit alone is not the acceptance receipt.

1. **Readback first:** run `ocean-v1-beta-db-readback` to establish actual private
   connectivity, exact postgres/database/source identity, expected fresh schema,
   no independent roles and no migration head. Readback must be metadata-only.
2. **Bootstrap:** run only after the fresh-state/readiness and logging/provider
   policy gates pass. Require actual session logging/collector attestation,
   SCRAM-only role creation, vector extension and strict role/membership
   readbacks. A limited Cloud SQL principal refusal remains a real gate; do not
   weaken checks to force it through. After successful shutdown/exit acceptance,
   reduce the two newly added role-password secret memberships as above.
3. **Migrate:** require actual restricted `ocean_v1_migrator`, exact source/head,
   no administrative role fallback and no reset/downgrade/retry. Preserve any
   partial schema and diagnose an interrupted stage before proceeding.
4. **Finalize:** require exact head and effective least-privilege/PUBLIC/column/
   delegation checks. Require only the three accepted serving-table grants;
   scientific/history/C23 grants and real user enrollment remain absent.
5. **Final readback:** run readback again and bind the resulting roles, owners,
   extension/head and all stage receipts to this target, without exposing data.

For **every** stage, require the operator's safe JSON `state=stage_completed`,
expected stage/source/target and acknowledged proxy shutdown, plus the actual
successful exit of both operator and proxy containers and successful task/job
execution. The operator's2xx shutdown acknowledgement is not physical exit
proof. Timeout, cancel, stopped task, absent/ambiguous exit evidence, retry,
failed shutdown or uncertain mutation keeps the stage unaccepted. Do not
blindly rerun bootstrap or manufacture an empty-state receipt. Preserve
resources/evidence; manual inspection precedes any explicit recovery.

After final acceptance, review removal of only these temporary job identities'
new connector/secret grants; preserve accounts/job definitions/logs for audit
unless separately selected for cleanup. Do not remove unrelated members or
secret versions. No operational/scientific/OAuth/C23/release gate is closed by
the creation of identities or job definitions.
