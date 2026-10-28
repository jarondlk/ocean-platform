# Independent OCEAN v1 configuration

C24 prepares configuration and local validation for the proposed
`https://beta.oceaninfobio.com` site. Nothing here provisions a resource, changes
DNS/IAM, builds an image, creates a secret or enables dispatch. The legacy
`deploy/gcp/` entry points and their environment files are not consumed.

## Validate and render offline

From the repository environment:

```sh
python scripts/render_gcp_v1.py --check-schema
python scripts/render_gcp_v1.py --config deploy/gcp-v1/examples/site.synthetic.json --check
python scripts/render_gcp_v1.py --config deploy/gcp-v1/examples/site.synthetic.json --output-dir /private/tmp/ocean-v1-config-review
python -m pytest tests/test_render_gcp_v1.py tests/test_render_gcp_templates.py tests/test_security_config.py -q
```

The output directory must not exist. Rendering writes seven JSON artifacts and
a byte-hash manifest into a private directory. It never executes subprocesses,
reads environment credentials or contacts GCP/DNS. JSON input is bounded, rejects
duplicate keys, symlinks, nonfinite numbers, unknown fields and implicit defaults.
The committed JSON Schema describes field validation; the renderer additionally
enforces cross-field isolation, capacity, material and authority rules.

`examples/site.synthetic.json` contains fictional identifiers, repeated fixture
digests and illustrative budget/retention numbers. Its example hostname ends in
`.invalid`; it represents no image, service, secret, spending approval or runtime.
`examples/site.operator.pending.json` retains the proposed beta origin but has
null live inputs and **must fail validation**. Populate a separate private copy
with reviewed non-secret identifiers when the whole-site target is selected.
Never put passwords, tokens, DSNs or private signing seeds in either file.

All resource names are explicitly in the `ocean-v1-` namespace. Global bucket
names additionally carry the selected project ID. Legacy project/number pairs
and the temporary C23 project are rejected; no project is inherited from gcloud.
Application images require digests in that project's regional registry. Secret
references require distinct secret resources and numeric versions in its project
number. Distinct references do not prove distinct secret contents or absence of
inherited IAM; those require later actual checks.

## Artifact types and acceptance limits

| Artifact | Configuration supplied |
| --- | --- |
| `serving.json` | Cloud Run v2 frontend/API service body. Only frontend ingress is public through the owned load balancer; API is a private sidecar. The service requires application session auth. Its Cloud Run invocation IAM check is disabled for browser login through the load balancer, its direct default URL is disabled, and network ingress is restricted to internal/load-balancer traffic. |
| `controller.json` | Separate private Cloud Run v2 research controller body, explicit identity, exact pinned image, IAM invocation enabled and bounded scale. |
| `queue.json` | Cloud Tasks v2 queue body with bounded rate/retries. Queue state is output-only: creation does not mean paused. The operator must pause/read back before any producer starts. |
| `worker.json` | Compute instance body with no external IP, project-owned named boot image, protected disk, explicit supervisor identity, no startup script and no automatic restart. It is an unexecuted design, not an available worker. |
| `storage-database.json` | Private database, distinct snapshots/results/quarantine/backups targets, TLS, backup/retention and hold-preserving policy contract. |
| `identity.json` | Resource-scoped permission intents for separate runtime identities, exact secret resources, private queue/controller and v1 stores. No project-wide role or legacy grant. |
| `site-policy.json` | Exact origin/OAuth/session/CSRF contract, network ranges, worker material/capacity, supervisor lifecycle, default-off activation and all pending live gates. |

The artifact wrapper is **not an API request or an apply plan**. Its `body`
for Cloud Run/queue/worker follows the identified REST shape; storage, IAM,
network/ingress and supervisor sections are explicit policy contracts. They need
operator-reviewed provider configuration and actual validation before use.
`provider_schema_validated:false` and `apply_allowed:false` remain on every
artifact and manifest. Local tests do not attest provider acceptance, IAM
enforcement, image provenance, runtime implementation or cloud state.

Current frontend-v1 is a static export and C20 has a fake queue. C24 does not
turn those into an authenticated hosting gateway, real Cloud Tasks adapter or
production experiment supervisor. Their named gates remain unavailable and
dispatch is disabled in every rendered activation policy. Do not deploy a
preview server, fake queue or operator test harness as production infrastructure.

See [isolation matrix](ISOLATION.md) and [operations/live gates](OPERATIONS.md).
Source contracts remain C20, C22 and C23; scientific classification is unchanged.

## Primary resource references

Reviewed 2026-10-28: [Cloud Run services](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.services),
[queue state/rate/retries](https://docs.cloud.google.com/tasks/docs/reference/rest/v2/projects.locations.queues),
[default service URL](https://docs.cloud.google.com/run/docs/triggering/https-request),
[Cloud Run ingress](https://docs.cloud.google.com/run/docs/securing/ingress),
[Compute image unique IDs](https://docs.cloud.google.com/compute/docs/reference/rest/v1/images),
[machine family shapes](https://docs.cloud.google.com/compute/docs/general-purpose-machines),
[custom-domain options](https://docs.cloud.google.com/run/docs/mapping-custom-domains).
Names and configuration are not live readbacks or immutable image authority.
