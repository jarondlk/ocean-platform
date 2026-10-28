# C24 readiness and development plan

Prepared 2026-10-28 JST on `overhaul`, baseline
`838b424aca83c1a8816c358c7f53a3461b51ab7d`.
**Ready for C24 offline configuration development. Implementation is Not started.**
The user's current request is preparation, with `beta.oceaninfobio.com` proposed
for the separate overhaul site. This document records that working target;
it does not claim a registered DNS record, available hosting or a deployed beta.

## Prerequisites and source reconciliation

| Prerequisite | Accepted evidence | Current reconciliation |
| --- | --- | --- |
| C20 durable research execution | Source `a149239`, hosted run `39209113719`, [delivery](evidence/C20/delivery.json) | All 169 transitive source entries reconciled. 150 remain exact; 19 intentionally changed in accepted C21/C22/C23 work. All 169 current bytes match accepted source `f6f823b`. All 135 original delivery evidence files remain exact. |
| C23 isolated Python execution | Source `f6f823b`, hosted run `40652395233`, [completion](evidence/C23/completion-20261028.json) | All 236 actual-worker source pins match current and accepted source. Both retained Linux cases and raw audit pass; four required hosted jobs pass. Original capacity-held recovery limitations remain. |
| Checkout preservation | Baseline `838b424` | 370 distinct predecessor source paths reconciled, 5,006 prior tracked evidence files preserved and 42 unrelated paths unchanged. No predecessor receipt was rewritten. |

[Machine-readable verification](evidence/C24/readiness-20261028/verification.json)
records every source pin and all 19 intentional C20 supersessions, including
the accepted implementation commits. The old C20 hashes are historical evidence,
not a reason to reset the newer evidence, experiment or security implementation.
These are read-only receipt/source checks. Application suites were not rerun
for planning-only edits; their accepted results remain source-bound.

## Working hostname and browser boundary

Use `https://beta.oceaninfobio.com` as the proposed canonical v1 origin. Preserve
the existing main site at `https://oceaninfobio.com`; no redirect or main-domain
cutover is included. Hostname is an explicit configuration input, so changing
the proposal requires a new reviewed origin/callback binding before deployment.

Serve the v1 frontend and authenticated API through the beta origin. Keep
controller dispatch, queues, database and experimental workers private. Prefer
a v1-owned global external Application Load Balancer with serverless backends
and managed TLS as the configuration design; its final resources and cost are
operator inputs, not provisioned facts. Google currently recommends this custom
domain option; direct Cloud Run domain mapping remains limited/Preview.
[Cloud Run custom domain guidance](https://docs.cloud.google.com/run/docs/mapping-custom-domains).

Configure an independent OAuth client, signing/internal-token secrets and
v1-specific issuer/audience. The planned Google callback is
`https://beta.oceaninfobio.com/api/auth/callback/google` if the v1 hosting layer
uses the existing provider ID/path convention. Pin the actual implemented path
before enrollment; the provider requires an exact redirect URI match.
[Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect).

Use v1-specific host-only session cookie names, preferably `__Host-` prefixed,
with HTTPS, `Secure`, `HttpOnly`, `Path=/` and no `Domain` attribute. Do not
accept legacy cookies or reuse their names/secrets. Read back existing cookie
scope before launch; this preparation has not inspected live legacy cookies.
An inherited parent-domain cookie must not become v1 identity or be forwarded
to private services. [Cookie scope rules](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

Beta and the main origin share a registrable domain, so `SameSite` alone does
not establish separation. Require exact-origin/CSRF validation for browser
mutations, explicit CORS origins and tests rejecting requests from the main site
and sibling hosts. Never use `*.oceaninfobio.com` or parent-domain session scope.
The trusted ingress must validate the beta Host and overwrite untrusted forwarded
headers. [OWASP CSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## Planned implementation checkpoints

1. **Define the independent site configuration.** Add a versioned non-secret
   input schema and isolation matrix in `deploy/gcp-v1/`. Require explicit v1
   project/region, canonical origin, services, registry/image digests, database,
   buckets, identities, pinned secret references, OAuth callback and queues.
   Keep the full-site target distinct from legacy `data-infra-infobio` and do
   not silently promote the temporary C23 project into the beta site. Synthetic
   examples use reserved example hosts and resource IDs, never live credentials.
2. **Render and validate locally.** Add a separate offline renderer and templates
   for frontend/API ingress, private research controller/dispatch, dedicated
   Linux/gVisor worker, storage/database/identity/queue boundaries and monitoring.
   No renderer or test may invoke cloud/DNS APIs, apply resources or read a
   legacy environment file. Reject missing targets, legacy/shared mutable stores,
   wildcard origins, broad cookies, unpinned images, excessive permissions,
   public worker dispatch, guest credentials and writable host exposure.
3. **Prepare operator execution and rollback.** Document preflight, staged
   enablement, current-state readbacks, health, bounded logs, backup/retention,
   budget/capacity inputs, drain and rollback. Keep experiment dispatch off.
   Reuse exact C22 reservations and C23 physical-proof release; a lease timeout,
   elapsed shutdown deadline or rendered flag cannot release uncertain capacity.

Keep the existing `deploy/gcp/` renderer/templates unchanged. Its CLI contains
legacy project/resource defaults, so it is a reference pattern rather than the
v1 entry point. Preserve the user's unrelated evaluation-template changes.

One active experiment per user and two globally remain the C22 limits. Each
sandbox retains two CPUs, 4 GiB, ten minutes, 256 MiB inputs and 50 MiB outputs.
The future host must accommodate both sandboxes plus explicit supervisor/runtime
overhead. The single C23 test VM did not validate simultaneous two-job capacity.
Document measured capacity requirements without inventing prices or recovery
guarantees. Guest networking, metadata and credentials remain unavailable.

## Hosting and transport gates exposed by inspection

`frontend-v1/next.config.mjs` exports static files. Its loopback preview is not
an OAuth/API host; service mode correctly reports unavailable without a trusted
bootstrap. C24 must describe and validate the separate authenticated hosting
contract, not deploy that preview or repoint the legacy frontend. A concrete
v1 host/auth/proxy implementation and assembled browser checks remain gates
before beta serving can be accepted.

`orchestration/research_dispatch.py` supplies `FakeResearchQueue`; the C20
contract explicitly defers a real Cloud Tasks adapter and private authenticated
target. C24 configures those targets and identities, but a template does not
implement delivery, authentication or lease recovery. Keep real adapter,
outbox-consumer and supervisor lifecycle integration visible in the live
validation checklist. Route needed application changes to their owning component
with separately recorded source and acceptance; do not widen C24 silently.

## Acceptance and next action

C24 completion requires reviewable configuration, passing offline validation
and an operator runbook with pending live gates. Planned baseline regressions:
`python -m pytest tests/test_render_gcp_templates.py tests/test_security_config.py -q`;
add focused v1 renderer/schema tests during implementation. They have not run
as new C24 acceptance in this preparation. Existing C23 CI is not C24 CI.

Before an eventual beta launch, retain separate actual DNS/TLS/Host checks,
OAuth/session/CSRF checks across both origins, inherited IAM and network access
denials, independent storage/database/queues, two-job capacity, recovery/drain,
backup/restore and C26/C27 promotion evidence. DNS operator access, whole-site
target/region, independent OAuth/secret references, capacity, budget and retention
inputs are required for concrete live configuration, not for synthetic offline
development. No sign-in is needed to start that development.

**Next action:** implement checkpoint 1's explicit input schema and isolation
matrix, then checkpoint 2's renderer/negative cases. C24 remains Not started
until implementation is selected. Scheduler remains PAUSED. No GCP, DNS, TLS,
OAuth, real-data or application-runtime change occurred during this preparation.
