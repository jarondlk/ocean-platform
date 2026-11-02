# First public beta milestone: actual login page

Prepared for the user's new priority to make `https://beta.oceaninfobio.com`
reachable now. **Candidate only; root remains the sole cloud writer.** This
supersedes the earlier three-container hosting sequence only for this smaller
milestone. Original plans/receipts stay historical. No application change,
image build, cloud call, credential read or lengthy suite is performed here.

`service.create.json` uses the accepted `adb5bc75…6023e9dc` frontend image and
actual OAuth client ID with auth/internal/oauth version1 references. It omits
the create-body resource name; pass `serviceId=ocean-v1-beta-serving` in the
[Cloud Run v2 create request](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.services/create).
The final service name is retained for later API attachment. Only the frontend
starts: min0/max1, request-based1CPU/512Mi, concurrency4, timeout60s, Gen2,
no startup boost, VPC, SQL proxy or API dependency. Startup is an exact beta
Host/HTTPS443 HTTP GET to `/login`.

App authentication remains required, mocks/local chat stay false, secure
host-only session rules remain, and every scientific/execution flag is false.
The loopback API origin stays `127.0.0.1:8000` and is deliberately unavailable
until the backend is attached. **Acceptance is the real login page and assets
over the final beta TLS edge. It is not successful Google callback, session,
current-account, catalogue or research integration.** A callback cannot be
accepted while the backend account check is unavailable. Do not introduce a
temporary login bypass or report sign-in as working.

## Minimal root preflight and create

Confirm project `ocean-v1-beta-20261101`/`534831104543`, accepted image receipt,
current serving identity and the three ENABLED version1 metadata refs. Compare
actual existing service/LB/IAM state with the intended names; NOT_FOUND permits
create,403 or unexpected existing resources do not. Reuse an exact prior
root-created resource only with matching receipt and effective specification.
Keep one writer and preserve unrelated IAM/resource state.

Serving identity:
`ocean-v1-beta-serving@ocean-v1-beta-20261101.iam.gserviceaccount.com`.
It needs only secret-scoped `roles/secretmanager.secretAccessor` on:

- `ocean-v1-beta-auth`
- `ocean-v1-beta-internal`
- `ocean-v1-beta-oauth`

Apply only missing reviewed memberships and read each policy back. No serving
DSN, SQL role/client binding, bootstrap/migrator credential, project-wide role
or key is needed for this frontend-only revision. Inspect existing Cloud Run
service-agent image access; do not add runtime administrative roles.

```sh
gcloud secrets add-iam-policy-binding ocean-v1-beta-auth --project=ocean-v1-beta-20261101 --member=serviceAccount:ocean-v1-beta-serving@ocean-v1-beta-20261101.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --condition=None --quiet --format=json
```

Use the same exact command for internal and oauth only. Check effective
organization policy first: this edge requires internal/LB ingress, disabled
default URI and `invokerIamDisabled=true` so a browser can reach the app login.
No `allUsers` binding, public direct URL or organization-policy change is
proposed. If policy rejects this supported application-authenticated edge,
retain the failure; do not weaken application authentication or silently use a
different ingress. [Ingress](https://docs.cloud.google.com/run/docs/securing/ingress),
[invocation controls](https://docs.cloud.google.com/run/docs/securing/managing-access).

Root submits the exact file using an in-memory token/header:

```text
GET  https://run.googleapis.com/v2/projects/ocean-v1-beta-20261101/locations/asia-northeast1/services/ocean-v1-beta-serving
POST https://run.googleapis.com/v2/projects/ocean-v1-beta-20261101/locations/asia-northeast1/services?serviceId=ocean-v1-beta-serving&validateOnly=true
POST https://run.googleapis.com/v2/projects/ocean-v1-beta-20261101/locations/asia-northeast1/services?serviceId=ocean-v1-beta-serving
```

Require completed operation/no error and actual Ready revision, image digest,
single container, identity/three secret refs, bounds, probe and ingress/default
URI/IAM flags. Keep access tokens, secret payloads and cookies out of receipts.

## One final HTTPS edge, beta child A only

Fresh-check the existing beta certificate/map entry ACTIVE. The unchanged
`url-map.create.json` preserves Host, removes `Forwarded` and replaces forwarded
host/proto/port with beta/HTTPS443. Modern global `EXTERNAL_MANAGED` is required;
do not substitute classic `EXTERNAL`. No backend health-check resource, backend
timeout override, second HTTP rule, CDN, Armor or NAT is needed.
[Serverless global LB procedure](https://docs.cloud.google.com/load-balancing/docs/https/setup-global-ext-https-serverless).

After absent-name/baseline checks, root can apply sequentially, reading each
result back before the dependent command:

```sh
gcloud compute network-endpoint-groups create ocean-v1-beta-serving-neg --network-endpoint-type=serverless --cloud-run-service=ocean-v1-beta-serving --region=asia-northeast1 --project=ocean-v1-beta-20261101 --quiet
gcloud compute backend-services create ocean-v1-beta-serving-backend --global --load-balancing-scheme=EXTERNAL_MANAGED --protocol=HTTP --project=ocean-v1-beta-20261101 --quiet
gcloud compute backend-services add-backend ocean-v1-beta-serving-backend --global --network-endpoint-group=ocean-v1-beta-serving-neg --network-endpoint-group-region=asia-northeast1 --project=ocean-v1-beta-20261101 --quiet
gcloud compute url-maps import ocean-v1-beta-serving-url-map --global --source=docs/plans/ocean-v1/beta/fast-access-20261102/url-map.create.json --project=ocean-v1-beta-20261101 --quiet
gcloud compute target-https-proxies create ocean-v1-beta-serving-https-proxy --global --url-map=ocean-v1-beta-serving-url-map --certificate-map=projects/ocean-v1-beta-20261101/locations/global/certificateMaps/ocean-v1-beta-cert-map --project=ocean-v1-beta-20261101 --quiet
gcloud compute addresses create ocean-v1-beta-serving-ip --global --ip-version=IPV4 --network-tier=PREMIUM --project=ocean-v1-beta-20261101 --quiet
gcloud compute forwarding-rules create ocean-v1-beta-serving-https --global --load-balancing-scheme=EXTERNAL_MANAGED --network-tier=PREMIUM --address=ocean-v1-beta-serving-ip --target-https-proxy=ocean-v1-beta-serving-https-proxy --ports=443 --project=ocean-v1-beta-20261101 --quiet
```

Reserve the address only when ready to bind it promptly. Verify its actual
IPv4 and the rule/proxy/map/backend/NEG chain. Require no conflicting beta
A/AAAA/CNAME in child zone `ocean-v1-beta-domain`; then create only this record
using that **actual verified** address:

```sh
gcloud dns record-sets create beta.oceaninfobio.com. --zone=ocean-v1-beta-domain --type=A --ttl=300 --rrdatas=VERIFIED_NEW_LB_IPV4 --project=ocean-v1-beta-20261101 --quiet
```

No parent/apex/www/legacy DNS changes occur. Preserve child NS/SOA/authorization
CNAME. Partial failures retain readbacks and never justify replacing an
unexpected existing resource.

## Short live milestone check and cost

Check final public DNS/IP, trusted TLS/SAN, HTTPS `/login`200 and one real CSS
asset200, root routing to login, wrong Host denial and protected runtime401.
Verify default direct `run.app` access is unavailable and header normalization
works at the actual edge. Do not retain auth codes, token/cookie values or
Google profile data. Record the actual revision, source/image and safe HTTP
statuses. Provider startup/512Mi memory remains an actual gate; local shape
checks do not claim live readiness. Defer lengthy release checks while keeping
their acceptance status open.

The existing public JPY31-day envelope is¥35,604.05 including a shared¥3,000
Run allocation and one HTTPS rule. This frontend's captured request-based
rate is¥14.38083 per billed active hour;50hours plus100,000requests is¥725.37.
The quoted canonical-header feature adds about¥11.87/100,000requests from the
existing contingency. This is a usage example, not a forecast or new invoice;
all jobs/services share the Run allocation. Keep existing¥50,000 beta alerts
and¥3,000 Run cap, monitor overlap/actual spend, and notify before forecast
passes¥50,000. Min0/max1 is not a whole-project hard budget limit.

Later attach the reviewed API/config/proxy to the same service only after its
SQL/account and integration prerequisites pass. Real callback/session/UI/data,
queue/worker/C23 and full release gates remain separate. This milestone
publishes an honest authenticated login entry, not an accepted full platform.
