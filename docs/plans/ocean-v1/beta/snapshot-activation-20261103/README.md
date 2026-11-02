# CTD snapshot activation — 2026-11-03 JST

The first real dataset is live in the authenticated beta Context Catalog. API
source `a4923c4e41fba694f77ebb60c1d3f768390e8b1b` is pushed to `overhaul`;
Cloud Build `4b8fa356-9261-4a0a-9df9-df61c88669ef` and its separate network-none
Linux image proof both succeeded. Ready generation8 revision
`ocean-v1-beta-serving-00008-ngj` uses immutable snapshot-api digest
`sha256:877b1b3f7db703f5a8e9fedc3cca30f4a5aa67d238201cb5e9159482561e7eb9`.

## Actual data and authorization

The user explicitly approved CTD activation and one persistent reader grant in
`activation-user-authorization.json`. Automatic review rejected an earlier attempt
before execution pending that exact authorization; the subsequent authorized
operation succeeded once. `executed-publish-operator.py` records its actual source;
**do not rerun** it. The eight create-only objects were each downloaded at their
exact created generation and SHA256-verified. The lifecycle control was published
last. Earlier preparation/upload receipts correctly retain `cloud_published=false`
or `serving_activated=false` for their historical stages; this delivery supersedes
those prospective states without rewriting the receipts.

Private beta snapshot storage contains C09 child/index manifests, content objects,
activation and lifecycle control. The serving identity has Object Viewer only
under `v1/catalogue/` in that beta bucket. All other bucket bindings are preserved;
there is no public, write, legacy-project or project-wide storage grant. Runtime
uses generation-bound fresh control and activation checks. Scientific data and
full private activation/transfer manifests remain outside Git and image layers;
the image carries only the opaque exact-target activation reference.

CTD contains 162 casts and 10,955 original depth rows, preserving source dates,
labels and signed depths. Depth/temperature/salinity follow the existing OCEAN
contract units, without claiming independent calibration/unit validation.
Descriptive, unpublished, scientific approval false; no cross-source pairing or
scientific endorsement is inferred. Other raw measurement columns remain in
quarantine. Original source manifest/raw files remain unchanged.

## Verification and limits

Actual Google sign-in returned administrator/internal access. The real Context
Catalog discovery, directory drill-down, dataset inspector and both cast/depth
tables rendered, with their retained counts and 100-row first pages. Source/query
completion and qualifications render. This is not a claim of manual browser
traversal of all 10,955 rows or a measured production performance acceptance.
The screenshot is private in `/private/tmp`; only its hash/observation is retained.
Public HTTPS login returns200 with valid TLS, unauthenticated `/v1/runtime`401.
An initial sandbox DNS failure was followed by the successful network-enabled
read-only check. Native UI selector clicks did not change the table; the supported
semantic select action did, and actual depth rows were then observed.

232 distinct focused cases are covered across the retained231-case and final13-case
runs; 32 packaging checks and Ruff pass. Do not describe that as one232-case run.
Actual network-none/nonroot Linux proof verifies root-owned0444 configuration,
exact source and denied production test-transport injection. Existing broad CI
remains bound to50566b7; a fresh broad run is deferred per user instructions.
`verify_delivery.py` reconciles885 composed source paths,5368 original evidence
files,90 C27 artifacts and42 protected unrelated/scientific paths. It verifies
that only the API image and two catalogue source-selection settings changed in
the runtime template. Frontend/proxy, auth, secrets, network and scale settings
are preserved. No SQL/account/job mutation occurred in this activation.

## Next work

- Qualify metagenome library/run/abundance denominators, SST embedded timestamps
  and duplicate aliases, and eDNA current publication/classification dependencies;
  seal/register only qualified inputs. The user selected all eligible data.
- Implement durable catalogue retention and investigation/context writes with
  their exact DB/store authorization. The read-only GCS adapter deliberately
  cannot mutate retention; enabling Research over it is not yet accepted.
- Wire research/outbox/queue, model/provider and worker execution with actual
  integration checks before enabling those flags. Queue remains paused.
- Complete broader system/release, recovery and budget/operational acceptance;
  P2 D26-07 remains open. No production/research/scientific release acceptance.

Use the operator Mac's isolated beta wrapper for its granted read/build/existing-
service-update scopes, explicit Tokyo/project/build identity and approved bucket.
Other writes require their specific authorization; do not expand its roles.
Scheduler remains paused. Beta-only target stays¥50,000/month with notice before
exceeding; this activation does not add an always-on worker/model.
