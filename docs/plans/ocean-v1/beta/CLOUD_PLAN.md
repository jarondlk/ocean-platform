# Independent beta cloud plan

Status: offline design and worksheet only. No GCP account/resource inventory or
live change has been performed. Proposed names and region are separate from the
actual pending C24 input; no project ID/number, resource, image or secret exists
merely because it appears in a proposal. No apply commands are provided here.

## Planned resource boundaries

| Resource | Intended role | Required identity/configuration evidence |
|---|---|---|
| Independent whole-site project | Own all v1 resources, access and delivery targets | Inspect organization/folder/billing permissions; select an unused project ID and actual number; exclude legacy and C23 temporary project |
| Artifact Registry | Immutable frontend/API/controller and worker-material references | Exact independent regional repository, source archive/build receipts and image digests; no image has been built |
| Serving Cloud Run service | Production v1 host plus private API sidecar | Host/auth/proxy implementation, explicit serving identity, application auth, load-balancer ingress and direct default URL denial |
| Private controller Cloud Run service | Handle authenticated research task deliveries | Separate controller identity, ingress/IAM invocation checks, default `run.app` target and explicit OIDC audience |
| Research Cloud Tasks queue | Deliver durable research work | Dedicated task-invoker identity, bounded retries/rate, explicit pause/readback and accepted outbox producer lifecycle |
| Cloud SQL and private network | Independent application/corpus schema and narrow roles | Selected instance/version/tier/private ranges/TLS; explicit migration, serving, controller, admission and verifier privileges; no legacy connection |
| Snapshot/results/quarantine/backups buckets | Separate immutable data, experimental output, import and recovery domains | Project-namespaced distinct buckets, scoped permissions, retention/holds and no public or automatic destructive result policy |
| Secret Manager and OAuth registration | Independent beta sessions and narrow runtime credentials | Distinct pinned secret-version references and independently generated contents; no secrets in repository or guest |
| Dedicated Linux/gVisor host | Trusted retained experiment supervisor and bounded sandboxes | Immutable boot-image unique ID plus material hashes, private address, protected state, measured two-job capacity and actual cleanup/proof lifecycle |
| Beta DNS/TLS/load balancer | Serve only the proposed beta hostname | Verify domain ownership and exact beta records, TLS and forwarded Host behavior; preserve main/apex/www and keep controller/worker private |
| Logs, alerts, backup and spend controls | Bounded, recoverable operations | Chosen retention/RPO/RTO/spend policies, actual quota/scale/readback evidence and designated operators; no prices or guarantees invented |

Tokyo (`asia-northeast1`) is a working proposal, not a selected region. Runtime
shape and capacity are deliberately unresolved until actual requirements and
availability are reviewed. Keep the existing billing arrangement as previously
requested; whole-site controls/amounts are still configuration inputs, and the
legacy project's historical budget is not automatically a beta budget.

## Provider details checked during preparation

Serving and controller URL policies differ. Same-project Cloud Tasks requests
using the default `run.app` URL can be accepted by Cloud Run internal ingress;
disabling that default URL breaks this invocation path. Keep a reviewed default
controller endpoint with private ingress and IAM, while the browser-serving
service has its own load-balancer/direct-URL policy. Verify the exact topology
on the live project. [Cloud Run ingress](https://docs.cloud.google.com/run/docs/securing/ingress).

Construct HTTP tasks with explicit task-service-account email and intended
audience, then accept only that authenticated service boundary at the controller.
This is separate from application owner authorization and the browser's internal
JWT. [HTTP task configuration](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks),
[service invocation authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service).

Use explicit runtime identities rather than relying on the signed-in deployer
or a default account's inherited privileges. Grant only the concrete resource
permissions needed by each service; project separation alone does not prove
legacy denial. [Cloud Run service identity](https://docs.cloud.google.com/run/docs/securing/service-identity).

These references were inspected on 2026-11-01. Exact APIs/schemas, grants and
availability must be rechecked when preparing actual provider definitions.

## The later GCP session, in order

1. **Sign in and inspect, without writes.** Verify the selected CLI account and
   ability to view organization/folder/projects/billing. Browser Console login
   and CLI/ADC are separate contexts; verify the credentials used by the intended
   tool. Do not assume sign-in is still valid or change global project defaults.
2. **Resolve the worksheet.** Choose the isolated whole-site project, region,
   proposed names, private ranges, OAuth enrollment, operators, capacity/retention/
   recovery controls and budget settings. Record actual IDs only after inspection.
   Keep passwords, tokens, seed material and DSNs out of the worksheet. Its null
   cookie domain remains null because it intentionally requires host-only cookies.
3. **Prepare a concrete foundation change set.** Name exact APIs, network,
   registry, identities, empty secret containers, stores and target ownership.
   Inventory inherited access, IAM and routes. Translate C24 policy contracts to
   provider-validated definitions. Review cost-bearing choices and dependencies;
   no synthetic image/identity/secret or C23 default may fill a live value.
4. **Apply only the reviewed foundation scope when authorized/configured.**
   Retain command/output/identity/ownership receipts and negative legacy-access
   observations. Keep queues paused and dispatch off. Foundation creation alone
   does not expose a beta site or authorize a scientific data copy.
5. **Build and privately stage the implemented candidate.** Freeze exact source
   and image/configuration/material identities. Use explicit v1-only migration
   targets, independent OAuth, a synthetic snapshot and current bootstrap checks.
   DNS traffic, execution and external access wait for their own accepted stages.
6. **Validate each integration, then decide release.** Follow the implementation
   plan and C27 runbook. Retain source-bound live isolation/session/queue/worker/
   capacity/backup/rollback observations and the unchanged gate inventory. Any
   failed/unknown gate stops its capability. Only an explicit release decision
   permits promotion; never route beta to the legacy site as fallback.

## Information needed later

The worksheet enumerates missing fields from the actual C24 input. Most live
identifiers can be discovered or created after sign-in. Operator decisions still
include acceptable capacity/spend/retention/recovery policy, actual DNS/OAuth
control and scientific/data-transfer/withdrawal responsibility. No decision is
required to finish this preparation, and no login is needed for local integration
coding. Sign-in is needed when beginning the account/project inspection above.
