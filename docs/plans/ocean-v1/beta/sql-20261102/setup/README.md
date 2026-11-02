# Private credential installation and job rendering

Prepared locally only. **50 pure mocked checks pass**, with no cloud call, SDK
token acquisition, real random-secret generation, native cluster, image build or
job execution. Source and output are ready for independent review before root
uses the apply operation. Existing SQL/application/receipt files are unchanged.
This does not create OAuth configuration, enroll accounts or enable C23.

## Installation contract

`deploy/gcp/beta/setup/prepare_credentials.py` defaults to a static JSON plan.
It does not acquire a token, generate values or query GCP in that mode:

```sh
.venv/bin/python deploy/gcp/beta/setup/prepare_credentials.py
```

After independent review, root can select the concrete new-beta installation:

```sh
.venv/bin/python deploy/gcp/beta/setup/prepare_credentials.py --apply \
  --confirm-project ocean-v1-beta-20261101 \
  --confirm-instance ocean-v1-beta-sql \
  --receipt NEW_METADATA_RECEIPT.json
```

The receipt must not exist; an exclusive initial create occurs before any token
or cloud operation. No resume/overwrite/rotation/delete mode exists. The fixed
target is project `ocean-v1-beta-20261101`, number `534831104543`, private Tokyo
instance `ocean-v1-beta-sql` and existing `ocean_v1_beta` database. An active GCP
CLI login must already be available. The helper captures its access token in
memory; it never prints/stores that token or sends it as a shell argument.

Before values are generated, fresh live preflight verifies project identity,
RUNNABLE PG16 Enterprise/ZONAL/tier, private-only address within the reserved
range, exact VPC, encrypted/connector-only policy, disk bounds, deletion
protection, backup/PITR settings and the exact existing database. Existing
`ocean-v1-beta-auth`, `ocean-v1-beta-internal` and
`ocean-v1-beta-serving-database` must be empty and exactly user-managed replicated
in Tokyo. Four new containers may be created only if absent:

- `ocean-v1-beta-bootstrap-database`
- `ocean-v1-beta-migrator-database`
- `ocean-v1-beta-migrator-password`
- `ocean-v1-beta-serving-password`

If one of those four already exists, its exact name/replicas and absence of all
versions must be verified. All seven are re-read after empty container creation.
An existing ENABLED, DISABLED or DESTROYED version rejects installation. No
payload is accessed. Only after this verification does the applied helper create
five distinct cryptographic URL-safe64-character values: auth, internal signing,
postgres, migrator and serving passwords. The last three produce exact coupled
`postgresql+psycopg2` DSNs on `127.0.0.1:5432/ocean_v1_beta` for `postgres`,
`ocean_v1_migrator` and `ocean_v1_serving`. Seven versions retain auth/internal,
the three DSNs and the two restricted-role passwords. No provider/OAuth secret,
fake identity or application runtime configuration is supplied.

Values go directly over verified HTTPS to Google's documented
[Secret Manager create](https://docs.cloud.google.com/secret-manager/docs/reference/rest/v1/projects.secrets/create)
and [addVersion](https://docs.cloud.google.com/secret-manager/docs/reference/rest/v1/projects.secrets/addVersion)
endpoints. AddVersion includes base64 payload plus its
[CRC32C field](https://docs.cloud.google.com/secret-manager/docs/reference/rest/v1/SecretPayload);
the response must acknowledge the supplied checksum and enabled numeric version,
then a metadata-only GET verifies the version name/state. No credential values,
payload hashes/checksums, HTTP bodies or auth token enter receipts or files.

**The last mutation** is Google's
[SQL Admin users.update](https://docs.cloud.google.com/sql/docs/postgres/admin-api/rest/v1beta4/users/update)
for only this instance's `postgres` password. No database role membership,
runtime user or privilege is changed through that endpoint. A bounded read-only
operation poll verifies target/project, UPDATE_USER type and DONE without an
error. There are no automatic mutation retries. Receipts contain only phase,
created names, exact enabled numeric refs, operation identity and fixed status.

Use one installer only. The API does not provide an atomic conditional
"add only if there are no versions" operation; repeated inventory checks do not
constitute a distributed lock against an external concurrent writer. Do not run
another installer or edit these secret containers concurrently. A transport
failure may have applied despite a lost acknowledgement. Any partial/uncertain
failure preserves its pending phase and known refs, requires manual inspection,
and must not be retried by generating a new receipt or new credentials. The
helper cannot resume partial state. Retain the coupled versions for controlled
recovery; never expose them in chat or delete/recreate them to hide a failure.

The local metadata receipt is reserved before work and updated as steps finish.
If the filesystem write itself fails after an API mutation, retain the last
receipt and inspect the expected fixed resources; local logging is not a
transaction with Google. Python immutable credential strings are memory-only
here, not claimed to be cryptographically zeroed. Normal SDK login storage is
not replaced or exported by this script. HTTPS redirects and foreign API targets
are rejected; there is no service-account key generation.

## Reviewable private jobs

`render_jobs.py` requires an immutable operator image in the exact beta registry
and a completed metadata receipt containing all seven exact enabled numeric
refs. Syntax validation alone does not attest image source or live secret
contents: root must bind the actual accepted image/build evidence. The API
revision is `7924a28e919b1fb751890c694f7b1f9b26b104ff` and operator revision
`756c7a7dc46d4ba75e3a0308b7ab23d9b3553bfe`.

```sh
.venv/bin/python deploy/gcp/beta/setup/render_jobs.py \
  --operator-image asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/operator@sha256:EXACT_ACCEPTED_DIGEST \
  --credentials-receipt COMPLETED_METADATA_RECEIPT.json \
  --output NEW_RENDER_DIRECTORY
```

The four emitted files are **Cloud Run v2 REST Job bodies**, not gcloud v1
`jobs replace` manifests. They contain no create/run token, API call or execute
operation. Submit/create and execute are separate parent-owned actions after
review, stage-specific IAM/secret grants and actual readbacks. Synthetic render
fixtures are under `rendered-synthetic/` solely for review; their zero digest
and numeric version1 refs are invented test inputs, never live configuration.

All jobs have one task, parallelism1, retries0 and timeout600s. Gen2 Direct VPC
uses the existing beta network/subnet and private-ranges-only egress. No VPC
connector/NAT, public SQL endpoint, broad IAM or persistent key is introduced.
The official proxy2.26.3 index digest is
`sha256:f333a9c59890c3c67b8505166c5dbdcc0b29fca9173a2e09ca0446ab6997a736`,
from the parent's actual registry readback. It uses private IP, loopback5432,
loopback admin9091/quitquitquit and health HTTP0.0.0.0:9090. Operator startup
depends on its `/readiness` probe, bounded at120seconds. A listening proxy is
not proof of actual SQL authentication/network reachability; live startup and
the operator's database/source/privilege checks remain mandatory.

The proposal uses two separate identities, which this package does not create:

| Stages | Dedicated service account | Mounted private refs |
|---|---|---|
| bootstrap | `ocean-v1-beta-db-bootstrap@ocean-v1-beta-20261101.iam.gserviceaccount.com` | bootstrap DSN and migrator/serving passwords |
| readback | same bootstrap identity | bootstrap DSN only |
| migrate, finalize | `ocean-v1-beta-db-migrator@ocean-v1-beta-20261101.iam.gserviceaccount.com` | migrator DSN only |

Grant only the selected instance's connector permission and exact needed secret
access after review. No SA/IAM binding is applied here. All sidecars share their
job's identity; minimal mounts do not prevent that identity from separately
accessing other IAM-authorized secrets. Remove unnecessary password access from
the bootstrap identity after its stage where operationally appropriate. Never
mount bootstrap or migrator credentials into the public frontend/worker.

Cloud Run's official [Job/ExecutionTemplate](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs),
[TaskTemplate](https://docs.cloud.google.com/run/docs/reference/rest/v2/TaskTemplate),
[Container](https://docs.cloud.google.com/run/docs/reference/rest/v2/Container) and
[Direct VPC fields](https://docs.cloud.google.com/run/docs/reference/rest/v2/VpcAccess)
were inspected for these bodies. Provider acceptance, actual image health,
numeric secret resolution, narrow IAM, managed-SQL bootstrap, complete per-stage
results and successful proxy/container exits remain live gates. Original C23
limitations, scientific/UI/OAuth enrollment and release gates remain unchanged.

## Verification

The pure checks use only deterministic synthetic inputs and mocked REST. They
cover exact preflight drift, existing versions, seven coupled values/CRC request
shape, postgres-last ordering, partial failures, receipt non-overwrite, private
data absence in metadata, fixed HTTPS targets, job bounds, stage-specific mounts
and mutable/foreign image/ref rejection. No native or prior application suite
is repeated.

```sh
.venv/bin/python docs/plans/ocean-v1/beta/sql-20261102/setup/verify.py
```
