# Authenticated beta hosting proposal — 2026-11-02 JST

**Plan only; the candidate is not ready to submit.** No cloud resources,
credentials, images, existing receipts or commits were changed by this task.
The selected target is project `ocean-v1-beta-20261101` / `534831104543`, Tokyo,
with public origin `https://beta.oceaninfobio.com`. The first deployable scope is
an authenticated beta shell; scientific services remain unavailable.

The actual Google web client and OAuth secret version1 are now present in the
root's metadata receipts. The client ID is
`534831104543-4l3hm9dqd60u320mf73ql0d3s9rsuprn.apps.googleusercontent.com`,
with exact callback `https://beta.oceaninfobio.com/api/auth/callback/google`
and scopes `openid email profile`. No secret payload was read for this plan.
Real callback/session acceptance and independent account enrollment remain
pending; creating the OAuth client does not enroll an application user.

## Reviewed candidate files

- `serving-service.pending.json`: proposed Cloud Run v2 service with the final
  application-authenticated public-LB policy. It is a review artifact, not an
  apply command. The initial private revision must keep the Cloud Run IAM
  invocation check enabled until the named gates close.
- `api-host-config.json`: exact non-secret API settings for the selected image's
  embedded source revision. Its delivery mechanism is still missing.
- `url-map.proposed.json`: modern global external LB routing and canonical
  forwarded-header handling, with exact beta Host enforcement still in the app.
- `plan.json`: identities, secret grants, dependencies, cost use, ordered changes
  and explicit readiness gaps. `inspected-inputs.json` pins the local inputs.

The selected frontend/API images are immutable digests already built from source
`7924a28e919b1fb751890c694f7b1f9b26b104ff`. Their prior container smoke proves
the unprivileged images/imports, login/CSS and rejection behavior with synthetic
inputs; it does not prove live SQL, Google callback, sessions or science. Original
source/CI/build/smoke receipts remain separate and unchanged.

## One service, three containers

| Container | Listener | Resources | Startup dependency |
|---|---|---|---|
| `frontend` | `0.0.0.0:8080`, sole ingress | 1 vCPU / 512 MiB | `sql-proxy` |
| `api` | `127.0.0.1:8000` | 1 vCPU / 4 GiB | `sql-proxy` |
| `sql-proxy` | SQL on `127.0.0.1:5432` | 1 vCPU / 256 MiB | none |

Use gen2, request-based billing, min0/max1, concurrency4, timeout60s and no startup
CPU boost. Direct VPC egress uses only private ranges through the existing beta
network/subnet; Google OAuth internet traffic uses the normal managed egress.
The proxy selects only the actual private beta SQL connection, with no key file,
public SQL IP, NAT gateway or legacy fallback. Cloud Run documents its
[container/listener contract](https://docs.cloud.google.com/run/docs/container-contract)
and [Direct VPC access](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc).

The proxy has an HTTP readiness listener on `0.0.0.0:9090` for its startup probe.
That port is not public ingress. Both app containers depend on this qualified
proxy start. The frontend's `/login` startup probe supplies exact beta Host and
HTTPS forwarding metadata; it checks frontend configuration only. The frontend
does **not** depend on the API, and no platform probe into the loopback-only API
or wider API listener is invented. The actual provider must accept this
dependency/probe shape; successful frontend startup is not whole-instance API
acceptance. See [startup ordering](https://docs.cloud.google.com/run/docs/configuring/services/containers)
and [health-check behavior](https://docs.cloud.google.com/run/docs/configuring/healthchecks).
The API's real factory still requires the correct database and migration head
before it serves. Whole-instance/API checks remain mandatory later.

## Source-bound config and minimal credentials

The current API image requires a bounded, **regular, non-symlink, absolute JSON
file** at `OCEAN_V1_HOST_CONFIG`. It does not create that file. The pending spec
names `/tmp/ocean-v1-api-host.json`, but no launcher or config volume has been
installed; submitting it as-is would correctly fail startup.

The preferred owning change is a tiny reviewed startup wrapper that materializes
only the pinned non-secret JSON as a new regular file, checks its revision
against the selected image manifest and execs the unchanged API entry. This plan
implements no wrapper or image change. A separate non-secret Secret Manager
config volume is an alternative only if its actual mounted-file behavior passes
the regular/non-symlink check; it also needs its own reviewed numeric reference
and narrow accessor grant. No ConfigMap or environment loader is assumed.

The serving account is
`ocean-v1-beta-serving@ocean-v1-beta-20261101.iam.gserviceaccount.com`.
Grant only instance-conditioned `roles/cloudsql.client` for the selected beta
SQL instance, and `roles/secretmanager.secretAccessor` on these four exact
containers. Mount only the recorded numeric version1 references, after fresh
metadata verification; never use `latest` or inline credentials.

| Secret | Container environment |
|---|---|
| `ocean-v1-beta-auth` | Frontend `V1_AUTH_SECRET` |
| `ocean-v1-beta-internal` | Frontend signer and API verifier, same exact version |
| `ocean-v1-beta-serving-database` | API's prefixed serving DSN only |
| `ocean-v1-beta-oauth` | Frontend raw Google client secret |

The OAuth client ID is a non-secret literal. No JSON-key unpacking of the OAuth
secret is assumed: the host expects a raw secret string. All three containers
share the service identity; separate mounts do not provide per-container IAM
isolation. Treat the instance as one trusted serving unit. It receives no
bootstrap/migrator, worker, queue, bucket-write, model, termination, project-wide
secret or broad administrative permission. Check existing service-agent image
and Direct VPC permissions before adding any grant. The
[Cloud Run secret contract](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
and [v2 service/container schema](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.services)
govern the proposed resource fields.

## Application identity and capability gates

Before serving traffic, actual limited-creator bootstrap, migrations to
`20261027_0021` and final serving-role grants must pass. Enrollment then needs an
explicitly approved independent Google subject/email and application role,
checked against the real `AppUser` contract. The current four-stage database
operator has no enrollment command. Do not copy legacy users, infer a subject
from email/GCP login, assign an unapproved role, or enable automatic enrollment.

Keep all twelve `ENABLE_V1_*` flags false. The bare environment factory has no
scientific provider. It must report unavailable capabilities, not fabricated
empty data or preview fixtures. A later reviewed source/policy-bound provider
and any real-data authorization are separate. Queue remains PAUSED; no
controller, worker, model, research or experiment execution is started.

## Public edge and beta-only DNS

Final serving ingress is `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`, default
`run.app` URL disabled, with the Cloud Run Invoker IAM check disabled only for
this application-authenticated beta edge. This lets a normal browser reach the
Google login flow; Auth.js and current-account checks remain authoritative.
Initially retain IAM invocation enforcement while preparing the private
candidate. Read effective organization policy before changing the final edge;
do not relax org policy or silently grant `allUsers` if it is blocked. These
are distinct controls documented under [ingress](https://docs.cloud.google.com/run/docs/securing/ingress)
and [IAM invocation](https://docs.cloud.google.com/run/docs/securing/managing-access).

Propose one **global EXTERNAL_MANAGED** HTTPS Application Load Balancer with a
Tokyo serverless NEG pointing only to this service, one backend, one URL map,
one target HTTPS proxy and one Premium IPv4 forwarding rule on443. Serverless
NEG uses Cloud Run readiness; no separate backend health-check resource or
unsupported backend timeout is added. Bind the existing beta certificate map
only after fresh actual certificate/map ACTIVE checks. No HTTP redirect rule,
Cloud Armor, CDN or extra paid proxy is selected.
[Global serverless LB guide](https://docs.cloud.google.com/load-balancing/docs/https/setup-global-ext-https-serverless).

The proposed URL map preserves Host, removes untrusted `Forwarded` and replaces
the three forwarded host/protocol/port headers with exact beta/HTTPS/443 values.
The app still rejects a wrong Host and sibling Origin. Use modern
`EXTERNAL_MANAGED`: the [URL-map API](https://docs.cloud.google.com/compute/docs/reference/rest/v1/urlMaps)
does not support this headerAction on classic `EXTERNAL`. Actual provider header
behavior is a live gate, not an inference from the JSON template.

Only after the actual new IPv4/backend are verified, create
`beta.oceaninfobio.com. A` at TTL300 in the **beta child zone**. The address is
still unresolved in this plan. Fresh-check for conflicting A/AAAA/CNAME records;
preserve child NS/SOA/authorization CNAME and every parent/apex/www/legacy record.
No AAAA, parent-zone change or Cloud Run domain mapping is proposed here. Bind a
reserved address promptly; do not leave a failed partial setup incurring unused
address fees without review.

## Cost and acceptance

The unchanged ¥35,604.05 31-day scenario already allocates ¥3,000 across all
Cloud Run services/jobs. This three-container shape is3vCPU/4.75GiB, rather than
the earlier illustrative2vCPU/5GiB arithmetic. At captured public JPY rates it
costs ¥47.7699804 per aggregate billed hour;50hours plus100,000requests is
¥2,394.83, leaving about¥605.17 within the Run allocation for other starts/jobs.
That is a usage condition, not a measured traffic forecast. Min0/max1 and a
service cap do not guarantee an instantaneous hard ceiling.

Canonical custom headers have an additional quoted feature charge of about
¥11.87 for100,000requests. This proposal consumes that amount from the existing
¥3,236.73 contingency, leaving about¥3,224.87; it does not rewrite the original
quote or claim the original gross arithmetic included the feature. The total
envelope remains¥35,604.05, below the initial¥50,000 target. Larger shapes,
traffic, paid options or always-on workers require a fresh forecast. Root must
monitor actual cost, overlap, retained bytes and service-cap behavior.

Acceptance requires source-bound service/IAM/config readbacks, correct live
SQL/API startup, valid TLS, real Google callback, sign-in/sign-out, secure
host-only cookies, account revocation, sibling Origin denial and refusal of
direct/alternate-host access. Use safe receipts without auth codes, tokens,
cookie values, DSNs or secret-derived hashes. Then verify actual UI/API behavior,
cold starts, latency, memory and cost. This plan clears no scientific review,
P2 D26-07, queue/worker integration or full release gate by itself.

```sh
.venv/bin/python docs/plans/ocean-v1/beta/hosting-plan-20261102/verify.py
```

Verification is local and read-only. It checks pinned inputs and proposal
boundaries; it does not call GCP, supply the missing config delivery/enrollment,
or treat an unsubmitted specification as a working deployment.
