# Beta private Cloud SQL provisioning plan

Prepared 2026-11-02 JST. **Plan only: no network, database, role, secret, job or
IAM mutation was performed.** Apply only after root accepts the completed fresh
JPY quote, verifies the current project/range inventory and freezes the concrete
change set. User authorization for the isolated beta and initial ¥50,000 target
already exists; this document does not request it again or clear live gates.

Target is solely `ocean-v1-beta-20261101`, number `534831104543`, Tokyo. Proposed
instance `ocean-v1-beta-sql` is Enterprise PostgreSQL16, zonal
`asia-northeast1-a`, 2vCPU/7680MiB, 20GiB SSD with automatic growth limited to
30GiB, no public IP/authorized networks, encrypted-only connections, deletion
protection, seven daily backups and seven-day PITR. No HA, replica, Enterprise
Plus, public endpoint, VPC connector, NAT, PSC endpoint or legacy resource is
included. The existing custom network/subnet are the only consumer network.

The completed quote must govern actual procurement. The current local
[qualification](../quotes-20261102/cost-qualification.json) prices the 744-hour
scenario at ¥20,674.80 SQL compute + ¥721.57 20GiB SSD + ¥339.56 20GiB retained
backup + ¥360.79 separate log allowance, before contingency. The 730-hour total
for those four lines is ¥21,680.92. These use each SKU's captured conversion
factor; the earlier approximate storage values are superseded by this quotation.
The quoted whole-beta 744-hour usage scenario is ¥35,604.05 including 10% cost
contingency, not a tax assertion or invoice. The log allowance does not establish
the actual PITR storage implementation. Disk growth, retained/log bytes and use
still require metering. Before a forecast exceeds ¥50,000, notify the user and
revise the resource plan. No deletion of held records is a cost-control action.

## Network and instance sequence

1. Read the beta project identity, existing SQL inventory, all beta subnet,
   allocated-range and relevant route/peering readbacks. Confirm no overlapping
   or already allocated `10.93.0.0/20`, and that existing
   `ocean-v1-beta-subnet` is `10.92.0.0/24` on
   `ocean-v1-beta-network`, region `asia-northeast1`. The /20 is a candidate,
   not an asserted live allocation. Refuse identity/name/config mismatch.
2. Reserve internal global VPC_PEERING range `ocean-v1-beta-sql-range`,
   `10.93.0.0/20`, in that network. Establish the private-services-access
   connection to `servicenetworking.googleapis.com`. Wait for the operation and
   retain range/peering readbacks. Do not force-update or replace an unexpected
   existing peering. Private services access may provision its documented
   service agent; do not add unrelated runtime roles to it.
3. Create the single proposed instance using the supported command in
   [plan.json](plan.json). Installed gcloud help requires `--cpu=2` and
   `--memory=7680MiB` for dedicated Enterprise capacity; do not combine them with
   `--tier`. The corresponding expected readback is `db-custom-2-7680`.
   `--ssl-mode=ENCRYPTED_ONLY` is the current encrypted transport setting.
   Require the official connector as an additional planned network boundary.
4. The installed create command has no `--allocated-ip-range-name` flag. The
   plan selects the existing network after verifying its sole reviewed PSA
   allocation and then checks the private address belongs to that /20. An
   alternative reviewed SQL Admin API request can explicitly specify
   `settings.ipConfiguration.allocatedIpRange`; do not invent a gcloud flag.
5. Retain actual operation/readback: exact project/connection name, engine,
   edition/tier/zone, `RUNNABLE`, private address within the selected range,
   public IP absent, authorized networks empty, correct private network,
   SSL/connector enforcement, size/growth limit, backup/PITR retention and
   deletion protection. The default `postgres` account initially has no
   password; instance creation is not an accepted application database.
6. Provision only the new `ocean_v1_beta` database through SQL Admin API or the
   explicit database-create command. Do not import legacy accounts or data.
   Private role/schema/bootstrap and source-bound migration occur later through
   the controlled jobs below, after their code and grants are concrete.

Private SQL requires a consumer network path; a proxy is not a tunnel from a
machine lacking that path. See [PSA configuration](https://docs.cloud.google.com/sql/docs/postgres/configure-private-services-access).
The existing /24 is large enough for the documented Direct VPC minimum, but
actual IP availability and startup connectivity still need acceptance.
[Direct VPC guidance](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc).

## Private serving and operator connectivity

Use an explicitly pinned official Cloud SQL Auth Proxy2 image as a same-instance
sidecar, with `--private-ip --address=127.0.0.1 --port=5432` and the exact
`ocean-v1-beta-20261101:asia-northeast1:ocean-v1-beta-sql` connection name. Resolve
and retain the official image digest before deployment; the plan deliberately
does not invent one. Use ADC from the attached dedicated service identity,
never a downloaded service-account key. The proxy's connector IAM and actual
database SQL credentials are separate controls.

For serving, the frontend, API and proxy share one Cloud Run instance network;
only frontend port8080 is ingress, API listens loopback8000 and proxy listens
loopback5432. Use Direct VPC network/subnet selection and
`--vpc-egress=private-ranges-only`. Private SQL traffic uses the VPC/PSA path;
Google control-plane and other permitted public destinations use normal Cloud
Run egress, without a NAT resource. Preserve the separate canonical-origin,
load-balancer and direct-URL policy. Do not add the platform's built-in public-IP
Cloud SQL socket annotation as a substitute for this private proxy path.

The app DSN uses `127.0.0.1:5432`, its independent SQL username/password and
`ocean_v1_beta`. The loopback client/proxy leg stays local; the proxy performs
TLS to SQL. Setting DSN SSL mode to require TLS on the local proxy listener is
not a substitute for verifying this encrypted private upstream path. The new
API/migration entries already accept the explicit loopback connector contract.

Use the same Direct VPC/private proxy arrangement for a bounded bootstrap or
migration job, each with its own dedicated service identity and only its own
specific secret access. All containers of one Cloud Run deployment share its
attached IAM identity; sidecars are not separate IAM principals. The proposal
therefore isolates bootstrap/migrator jobs from the serving deployment.

Grant only actual connector permissions (`cloudsql.instances.get` and
`cloudsql.instances.connect`) for the selected beta instance using a tested
conditional Cloud SQL Client binding or a reviewed custom role; validate any
condition against actual instance requests before depending on it. Do not grant
Cloud SQL Admin/Editor or project Editor to application runtime identities.
The bootstrap operator's SQL `postgres` credential is not mounted in serving,
research, worker or verifier containers. This plan applies no IAM bindings.

Actual Direct VPC availability can lag startup. Use bounded connection retries
and a real proxy/SQL readiness test before dependent work. Do not assume a
default probe Host or a TCP open socket proves database authentication/schema.
Jobs must have one task, parallelism1, max-retries0 and a bounded 600-second
deadline initially, with no execute-on-create flag. A proxy sidecar must finish
when its operator finishes: implement a reviewed operator finalizer that calls
the proxy's localhost-only `--quitquitquit` endpoint after success or failure,
wait for clean exit and preserve both exit statuses. A forever-running sidecar
ending only at task timeout is a failure, never a successful migration receipt.
The control endpoint must not be exposed by the frontend/proxy allowlist.
[Official proxy behavior](https://github.com/GoogleCloudPlatform/cloud-sql-proxy).

## Database ownership and bootstrap

Cloud SQL built-in user creation grants `cloudsqlsuperuser`, `CREATEROLE` and
`CREATEDB` by default unless custom roles are explicitly assigned. Do not create
runtime accounts through an unqualified user-create call. Establish only a
temporary new-instance bootstrap credential for `postgres` through a private,
redacted Admin API operation; keep its value out of argv, repository, build
context, logs and chat. Mount it only into the bounded bootstrap job.
[Cloud SQL role defaults](https://docs.cloud.google.com/sql/docs/postgres/users).

The required bootstrap job is an **unimplemented operator artifact**, not the
API's `migrate` operation: the latter correctly refuses the `postgres` user.
Prepare and check a separate exact-target bootstrap entry/script in an immutable
image before any row/role operation. It must validate project/instance, actual
`current_database()/current_user`, expected initial inventory and exact SQL
identifiers, perform only the new beta role/schema/grant setup, and return
credential-safe readbacks. No legacy default/environment fallback or arbitrary
SQL input is permitted. Secret generation/installation must use secure private
inputs, and a retry must compare actual state rather than reset role/data state.

Recommended identities are:

| Principal | Initial scope |
|---|---|
| `postgres` | New-instance bootstrap/recovery only; no serving mount |
| `ocean_v1_migrator` | Independent DB/schema owner and exact Alembic operator; no runtime mount, no global CREATEDB/CREATEROLE |
| `ocean_v1_serving` | LOGIN, no administrative attributes/memberships, no owned DB/schema/table; current-account and limiter rights below |
| `ocean_v1_research_controller` | Separate restricted LOGIN, no initial grants/credential mount until production controller implementation |
| `ocean_v1_sandbox_controller` | Separate restricted LOGIN, no initial grants/credential mount until retained runtime acceptance |
| `ocean_v1_sandbox_verifier` | Separate restricted LOGIN, no initial grants/credential mount until physical-proof acceptance |
| `ocean_v1_sandbox_function_owner` | NOLOGIN, no administrative attributes or members; future C23 function authority only |

Create restricted roles with explicit NOSUPERUSER, NOCREATEDB, NOCREATEROLE,
NOREPLICATION and NOBYPASSRLS; verify actual attributes/memberships. Revoke
PUBLIC database CONNECT/TEMP and schema CREATE where appropriate in the new
database, then grant explicit CONNECT/USAGE. The trusted migrator may own the new
database and public schema; no runtime role may own them. Current migrations
do not create scientific corpus tables/extensions automatically, and ordinary
host startup must not call `init_db` or `create_all` to fill any gap.

After an explicit new-database migration to `20261027_0021`, the current bare
host needs SELECT on `app_user` and `alembic_version`, plus SELECT/INSERT/UPDATE
on `rate_limit_bucket`. Grant those exact rights only initially. There is no
independent enrollment implementation or actual scientific provider supplied
by this plan; do not enable a broad table wildcard or whole read/cancel UI
journeys on the strength of the bare host. Later configured services need a
reviewed exact table/column grant extension and their own role-denial checks.

The accepted C23 restricted bootstrap additionally requires zero memberships
and no runtime table/schema/database ownership, and transfers function ownership
to a dedicated NOLOGIN role. Native receipts exercised it with a real PostgreSQL
superuser. Cloud SQL `postgres` is a limited `cloudsqlsuperuser`, not a true
SUPERUSER. Its ability to execute that exact ownership/bootstrap procedure under
the unchanged checks is **not established**. Keep C23 execution disabled until
actual qualification or a separately reviewed owning implementation resolves
this; do not weaken the membership/ownership checks to make SQL provisioning
look accepted. This does not prevent provisioning/migrating the independent
database for the closed read-only host stage.

Finish with actual live migration head/schema/history readbacks, explicit
runtime allow/deny checks, backup restore into a separate owned target, and
operator credential/grant removal or approved recovery retention. Retain all
original C24/C26/C27 receipts and the twenty unchanged operational gates.

## Supported command checks and pending work

Read-only installed gcloud help confirmed address/peering, SQL instance create,
Cloud Run job network/subnet/egress/container/dependency, secret and timeout flags.
Warnings concerned sandbox-denied SDK log-file creation; no cloud action was
attempted and no permission failure is relabelled a provider-schema check.
The JSON commands are a reviewed proposal, not a dry-run/provider acceptance.
No new job, secret version, bootstrap code, IAM binding or proxy image exists
from this plan. Parent must finish quote verification, inspect live ranges,
apply/read back the selected SQL/network set, then prepare the guarded private
operator and actual serving manifests against immutable images.
