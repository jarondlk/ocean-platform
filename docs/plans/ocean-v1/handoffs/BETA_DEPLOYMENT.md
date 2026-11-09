# Beta deployment continuation — 2026-11-09 JST

## Current compatibility amendment

The Gemini adapter now omits deprecated sampling configuration. All 67 focused
Research checks pass, including real SDK request serialization against mock HTTP
transport. The replacement API image must pass its source-bound image proof
before selection for Research activation. Preserve the previous API build and
its original receipts. See the
[compatibility amendment](../beta/research-20261109/README.md#compatibility-amendment).

Fresh personal CLI sign-in and cloud readback confirm an empty paused Research
queue, private encrypted SQL and the exact control-only serving storage write
grant. The controller secret has zero versions. Live SQL role/provider/task
acceptance remains pending. The corrected SDK flow is not a real model call.

Research questions are prioritized, with the user selecting Gemini through
Vertex AI. The [Research activation review](../beta/research-20261109/README.md)
contains four successfully built immutable images, scoped cloud changes,
private-controller/one-shot-job configurations and rollback. The final disposable
PostgreSQL16 qualification passes credential initialization/SCRAM denial, exact
runtime grants and the saved cited-answer journey with synthetic data/provider
transport. It is not live Cloud SQL/Gemini acceptance. Live revision remains
`ocean-v1-beta-serving-00017-kvz`, 100% traffic; Research execution is disabled
and its Cloud Tasks queue is PAUSED at fresh readback. New-service, IAM, database,
job execution, API enablement and runtime outbox scheduling require the specific
activation scope documented in that review. No such writes have been applied.
The three-hour Codex schedule stays PAUSED; legacy and eDNA gates are unchanged.

## Live catalogue checkpoint — 2026-11-05 JST

The authenticated beta serves saved investigations alongside the CTD,
metagenome, and MUR regional SST catalogues on revision
`ocean-v1-beta-serving-00017-kvz` at 100% traffic. The
[request latency update](../beta/context-20261103/request-latency-20261105.md)
removes duplicate listings, ancestor requests and repeated Research discovery
polling. Backend reads verify activation/lifecycle at request boundaries while
preserving per-operation payload verification. Live collection discovery sampled
5.142–5.727 seconds; initial loading still takes several seconds, and scale-to-zero
can add startup delay. The [copy cleanup](../beta/context-20261103/copy-cleanup-20261104.md)
removes promotional and repeated explanatory text while retaining controls,
errors and source-specific scientific qualifications. The [collection-browsing rollout](../beta/context-20261103/catalogue-browsing-20261104.md)
adds visible links to all three authorized collections and clears stale filters
when switching. Search stays within the selected collection; no new data was
activated. The preceding rollout occasionally reached its 15-second discovery
timeout; the latency receipt records the subsequent optimization and its limits.
The [reference-verification follow-up](../beta/context-20261103/reference-verification-20261104.md)
records the deployed API optimization: context changes returned 200 in 8.286
and 8.887 seconds; sampled context reads took 1.504–3.472 seconds. ANEMONE's
separate raw-data latency/integrity acceptance remains open.
The [confirmation follow-up](../beta/context-20261103/save-confirmation-20261104.md)
records the deployed frontend fix and the preceding revision's timing limit.
The [saved investigations receipt](../beta/context-20261103/live-20261104.md)
records the approved grants and initial browser workflow.
The [metagenome/SST rollout receipt](../beta/cohorts-20261103/meta-sst-live-20261104.md)
records the active image, browser checks, and remaining latency limits.
The branch is `overhaul`, and the three-hour schedule remains paused.
The [second Mac handoff](SECONDARY_MAC_HANDOFF.md) describes pinned input
recovery and the earlier CTD-only checkpoint.

## Paused checkpoint — 2026-11-03 JST

The live service remains generation 9, with the updated frontend and the
original CTD-only API. The C13 carrier fix passed 197 local regressions;
explicit staged cohort selection passed 16 tests, and packaging passed 34
probes. The fix is checkpointed in source and has not been built or deployed.
The full cohort passed local catalogue correctness after the fix, but raw eDNA
paging took 15.076610 seconds before network cost, failing the existing
15-second gate. The cache experiment is a local diagnostic only. Resume with
a fresh `meta-sst` append; no new bundle was prepared during the pause.
Context grants and actual Cloud SQL/GCS/browser acceptance remain pending.
[Source receipt](../beta/cohorts-20261103/secondary-mac-source-checkpoint.json).

## Earlier iterative continuation — 2026-11-03 JST

The user explicitly requested iterative deployment of all remaining beta work,
authorized all project scientific data/GCP use, and reactivated a three-hour
same-chat continuation. Existing automation `continue-ocean-overhaul-checkpoints`
was updated, not duplicated. It notifies only on meaningful progress/failure or
required action, checks existing work before continuing, and retains the beta-only
¥50,000 target/notice boundary. No legacy mutation or independent scientific
approval is inferred. [Authorization](../beta/cohorts-20261103/automation-and-authorization.json).

Actual frontend source0fc4775 build6b48b628 succeeded with network-none/nonroot
image proof; immutable image `context-frontend@sha256:005eda32b803676c17a4cdc72ffda3dedc447f4cf73b7533161b43f55d695ea3`
is now Ready generation9 revision `ocean-v1-beta-serving-00009-rn7`. Exact
readback verifies ONLY the frontend image changed. API/proxy/identity/secrets/
network/scale/flags preserved. HTTPS login200/TLSverified and unauthenticated
runtime401; refreshed authenticated browser still renders the CTD catalogue.
The frontend forwards exactly eight C17 context paths through existing auth/
origin/body guards, but the API remains catalogue-only, so context writes remain
unavailable until their actual grants and host composition pass. Do not confuse
this live frontend increment with complete Research deployment.

Pushed source checkpoints:0fc4775 (279 focused backend/57 hosting/typecheck,
32packaging probes/Ruff; qualified meta/SST and context-only source),1d20cf2
(eDNA/append publisher/exact context-grant operator and private aggregate driver),
b3db9e9 (renderer accepts the user’s new Nov3 authorization reference;34probes).
New publisher26tests, eDNA28tests, operator35tests and actual disposable native
PostgreSQL28checks pass. Native C17 transactions reproduced that audit INSERT
RETURNING needs SELECT(created_at); only that column is added, full audit reads
remain denied. Native cluster is stopped/removed. No real SQL grants or jobs run.

All328normalized eDNA artifacts/127885817bytes were read at exact existing source
generations and registry SHA/CRC verified into private staging.39current bundles
normalize to39datasets/3498occurrences/3498assays/349638detections;2older bundles
are excluded.3155classifications are unknown and343negative controls; all3498
physical identities remain unresolved. This allows raw inventory, not an eligible
environmental detection-frequency/association cohort. MUR1455observations and
sixgaps remain an unreviewed regional preview. Metagenome82source-column keys,
106runQC records and125952method-separated cells retain unknown abundance units/
denominators and all zero cells. No calibration/reclassification or science review.
Raw JCOPE remains separate:1837valid source-time grids plus one malformed all-fill
placeholder repeated11paths; missing SST cells remain missing and no dates invented.

Actual private aggregate `/private/tmp/ocean-beta-multi-catalogue-prepared-20261103`
source1d20cf2 seals41additional datasets into three new indices while preserving
the original CTD entry. Activation SHA3fee1baeb47d9d4b9df323ba8041aa661574b8f1e5233fc67498c1f6fcae07c6;
250immutable files/68844098bytes, controlrev4→92. This uses the LAST accepted
basecontrol generation1793637712460705/hash276e0190, not a fresh cloud-read claim.
Publisher must recheck the exact current generation/bytes before any upload and
CAS control last, preserving all refs/audits. Local preparation/publication manifests
and data remain private; nothing from this new cohort is uploaded or activated.

**Actual integration gate discovered:** offline all-family discovery on the new
package fails for eDNA with “Scientific/source canonical identities collide”.
CTD/metagenome/SST per-index overview succeeds. C13 incorrectly reserves the
shared canonical c12:edna directory under each distinct source owner;39legitimate
sources collide. The owning runtime fix and adversarial/multisource regression
checks were in progress at that point. The paused checkpoint above records
the fix and the subsequent latency failure; do not activate this candidate.
Old private preparation and failed diagnostic receipts remain immutable.

API candidateb3db9e9 build896039e7 and network-none source proof succeed, image
`snapshot-api@sha256:799c034a10366ea6ed1e736cc03986c6c979607ff4a77447ac508517e06f87c2`.
It is UNDEPLOYED and gated by the C13 defect; its source/binding must be superseded
explicitly after the fix, not retargeted. Context-operator1d20cf2 corrected build
6b0cba18 and offline source proof succeed, image
`context-operator@sha256:a9be3b94b156c9d1260c609fb5958c4e503772d3564b95c097fa9f3d47bb1340`.
First operator build2b08f03a failed only because its image-proof script had an
invalid broad text substitution; the correction/source-unchanged receipt and
first failure are retained. Initial API binding renderer also refused the new
Nov3 authorization reference locally; the explicit allowlist amendment and empty
preflight submission receipt are retained. Neither failure touched data or DB.

**Earlier authentication gate:** personal GCP authentication expired before a
fresh control read. No upload, grant or job attempt occurred. The automation
identity still worked within its read/build/existing-service update scopes.
The main Mac sign-in has since been cancelled; start a fresh sign-in on the
second Mac. Preserve the empty local preflight directory at
`/private/tmp/ocean-beta-multi-catalogue-20261103`.

Broad CI is deferred per user; the older receipt remains bound to 50566b7.
[New receipts](../beta/cohorts-20261103/),
[context operator/native checks](../beta/context-20261103/).

## Current CTD activation — 2026-11-03 JST

Pushed source `a4923c4e41fba694f77ebb60c1d3f768390e8b1b`; actual build
`4b8fa356-9261-4a0a-9df9-df61c88669ef` and both build/network-none image-proof
steps succeed. Ready generation8 revision `ocean-v1-beta-serving-00008-ngj` uses
`snapshot-api@sha256:877b1b3f7db703f5a8e9fedc3cca30f4a5aa67d238201cb5e9159482561e7eb9`.
Only API image and two source-selection settings changed; frontend/proxy/auth/
network/secrets/scale preserved. Only SHELL/CATALOGUE/CATALOGUE_BROWSER flags
are on in the API. Research/worker/model/scientific dispatch stays off.

After exact user approval, eight create-only CTD objects were copied into private
`gs://ocean-v1-beta-20261101-snapshots/v1/catalogue/`, each exact generation
SHA256-readback verified, lifecycle control last. Serving SA received only the
approved conditional Object Viewer prefix grant. No public, write, project-wide
or legacy grant. Original scientific files/manifest remain unchanged. Actual
operator source and all selection/readback/grant/build/deployment receipts are
retained; do not rerun upload, grant, DB bootstrap/migrations or enrollment.

Actual Google sign-in, catalogue discovery/drill-down, inspector and both tables
render:162cast rows and10955depth rows, with100-row first pages and explicit
source/query completion. Data remains descriptive/unpublished/not_reviewed.
Depth/temperature/salinity retain source rows and signed values; existing contract
units do not imply independent calibration. Other raw columns remain quarantined.
Child snapshot04f779af and index50bfdf55 are explicit registrations; activation
74674398 is immutable. No scientific findings/approvals or cross-source pairing.

232 distinct focused cases across231+final13 retained runs,32packaging checks,
Ruff, independent final review and actual nonroot Linux image proof pass. New
reconciler verifies885composed sources,5368original receipts,90C27 artifacts and
42protected paths. Broad CI is deferred; old run stays bound to50566b7. HTTPS
login200/TLSverified and unauthenticatedruntime401; actual browser observation
and private screenshot hash retained. [Activation delivery](../beta/snapshot-activation-20261103/).

Next: qualify/register metagenome, SST and eDNA under their actual provenance
constraints; integrate durable retention/context writes before Research; then
outbox/queue/model/worker integration and broader release/operational acceptance.
The GCS runtime store is deliberately read-only; it does not provide durable
retention writes needed for research bundles. No missing personal GCP sign-in
currently blocks granted read/build/existing-service-update operations. Use the
local beta wrapper for those authorized scopes, explicit beta project/Tokyo,
exact build SA and approved source bucket. Do not broaden roles for other work.
The user's CLI/AGENTS/wrapper edits remain unrelated and are not staged.

## Historical catalogue and data continuation — 2026-11-02 JST

Catalogue API source `abcdff79d8695be2e493efa29dc92c454d5b6dfe` is pushed.
Actual build `bddb55b2-bd82-4d84-aa07-385bc78d6dcf` and both build/image-proof
steps SUCCEEDED. Current Ready generation7 revision
`ocean-v1-beta-serving-00007-lxt` uses catalogue API image
`asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/catalogue-api@sha256:0de4842308efeef1b64c3e51b9c225d2ce0dbdd5b4b321ea4c65c1b6e37de13d`.
Catalogue/browser flags and SHELL are enabled only in the API. No database, IAM,
network, OAuth or dispatch change. Frontend and private proxy images unchanged.
Actual authenticated browser now renders Context Catalog controls and the honest
**No eligible snapshots** state. It is a real configured empty inventory, not a
fallback for missing scientific data. Research remains unavailable.

69 focused host/authority checks,14 packaging checks, Ruff and independent review
pass. Actual nonrootLinux/no-network image proof confirms root-owned0444 files,
source/config identity, import closure and real empty discovery. New delivery
reconciles882 committed source paths (two intentional source/test supersessions
and two additions),5368 original receipts,90 C27 artifacts and42 protected paths.
The previous hosted run remains bound to50566b7; broad CI/release acceptance is
deferred per user. [Catalogue delivery](../beta/catalogue-20261102/).

User answered **“Lets do all”** for the initial beta dataset selection. This
covers preparation/copy of all eligible existing scientific data to independent
beta, not accounts/history/backups/credentials or invented scientific reviews.
The first available raw CTD/metagenome/SST cohort has1860 unique files and
89159370 payload bytes. Its immutable legacy manifest9ac5170f has1860 entries but
1849 unique paths; a separately pinned11-path raw-alias amendment reconciles the
complete actual local inventory while retaining the original manifest unchanged.
Different-date SST filenames with identical bytes do not establish independent
observations or valid observation dates. Embedded time/provenance and scientific
deduplication remain publication gates. The reviewed quarantine preparer has23
focused tests plus Ruff and is committed at `b34a62a9168b58f8aba96632fe213bf08fc8a9f3`.
Actual preparation succeeded:1863 archive members/91934720 archive bytes, SHA256
`e62eb0e62ad1a1b0b9354944cb46b3b1d818fd12b5076b1e2749fb317cf471cb`.
Four create-only objects are now stored under private
`gs://ocean-v1-beta-20261101-quarantine/v1/raw-imports/local-20261102-e62eb0e62ad1/`.
Each exact generation was downloaded and SHA256 verified. Bucket Tokyo/PAPenforced/
uniform access and no public bindings were checked; no IAM or source mutation.
The first upload preflight stopped locally on an atime comparison before any
cloud call; stable metadata comparison fixed it before the single selected upload.
Do not rerun preparation/upload: accepted local package and source/target receipts exist.
The private archive and full source/transfer manifests remain outside Git.
Raw archive/staging is not a C09 seal, catalogue registration or scientific approval.
Metadata-only origin inventory separately observed all1860 raw source objects
(89159370bytes) and530eDNA objects (329136303bytes). SST inventory stopped at its
8MiB metadata cap after16000objects, so the overall remote inventory is explicitly
partial/unaccepted. Completed prefix inventories must not be repeated blindly.
No source object body was read by that inventory, and no remote cohort copied.
Five existing regional-publication objects (2619780bytes) were subsequently read
at exact generations into private Mac staging, CRC-verified, and publication/period/
registry SHA256 bindings reconciled to current operational publicationd34da58.
Actual source decision is user-accepted operational publication; independent
researcher approval/provider endorsement remain false. Retained period is explicitly
unpublished regional-context preview with scientific_approval=false. Preserve
those exact qualifications; historical embedded instructions do not grant new
authorization. Two referenced analysis dependencies remain pending. No regional
publication/data was copied to beta or registered. Source objects/private data
remain outside Git; sanitized readback/qualification receipts are in raw staging.

Precise remaining SST/current-publication selection is next; exclude operational,
backup, account/history/secret and serving-cache material. [Raw staging](../beta/raw-quarantine-20261102/).

Historical read-only scope at that checkpoint: use `./scripts/gcloud_beta.sh`
when local config is present, per user AGENTS instructions. It has viewer roles
only; do not broaden them. It successfully inspected current service/jobs/build
and regular logs. Authorized deployment/data writes use the separate operator
identity and explicit target; read-only legacy scientific inventory uses explicit
legacy project only for the user's approved data preparation. No legacy writes.
The user's new CLI/AGENTS documentation and wrapper remain unrelated local work,
not staged by this continuation. Scheduler remains PAUSED.

The following milestones are historical; the current CTD section above controls
current image, source and next work. Next: normalize/export the retained raw cohort, verify the current cloud publication
dependency graph, and register eligible scientific snapshots with real policy and
a durable cloud-backed store,
then durable catalogue retention/context CRUD and queue/model integrations.

## Latest actual continuation — public beta milestone

Source `6f03f9d37d29b4ebeefc7c7fc35d61bc6ef495cb` and its predecessors
`8e2a163`, `094841c`, `dcde1ef` are pushed to `overhaul`. Accepted application
bytes remain unchanged; deployment wrappers have separate source/evidence.

The independent beta edge is deployed: global Premium IP `136.81.62.56`, one
443 forwarding rule, HTTPS proxy/certificate map, URL map, backend service and
Tokyo serverless NEG. The exact beta certificate is ACTIVE. Child-zone A record
`beta.oceaninfobio.com. -> 136.81.62.56`, TTL300, is publicly resolving. No further
legacy/parent-zone changes occurred. Actual public normal-DNS login is200/TLS
verified, CSS200, wrong hostname403, correct unauthenticated `/v1/runtime`401.
The earlier optional build smoke failed and is preserved; its protected route
was incorrectly `/api/runtime/v1/runtime` (live404), not the actual `/v1/runtime`.
No claim is made that this failed optional smoke passed.

Cloud Run `ocean-v1-beta-serving` has default URL disabled, LB-only ingress,
application authentication, min0/max1 and closed dispatch flags. Frontend-only
revision00003-frs made the login publicly accessible. Generation4 revision00004-prr attached the real API and private SQL proxy.
Generation5 added a deployment-only startup wait for loopback API health before
starting Next, keeping startup CPU allocated until the API is ready while retaining
request billing/min0. Current generation6 revision
`ocean-v1-beta-serving-00006-sd9` is Ready and enables only `ENABLE_V1_SHELL`;
all other ENABLE_V1 flags remain false, authentication remains required. Runtime identity has only the existing three auth/OAuth secret reads,
one exact serving-DSN secret read and instance-conditioned Cloud SQL Client.
[Public edge evidence](../beta/edge-live-20261102/),
[backend attachment](../beta/backend-live-20261102/).

Actual images (all under the beta Tokyo registry except the official proxy):

- `serving-frontend@sha256:db0b822805cd3599abf33a5a05b931a0d05c2c337b87381927b4dc6233eb77e2`, source6f03f9d, successful build6872f1eb. Its14 actual Node HTTP checks pass. The deployment-only adapter removes Cloud Run's redundant RFC Forwarded field only after exact canonical beta transport checks; accepted Next/auth sources stay unchanged. Temporary secret-free diagnostic revision00002 is inactive.
- `serving-api@sha256:28f769ee6b44cb46b10c936f045e609bb83ad9d9bc8ccefa98603801a52157ab`, sourcedcde1ef, builde539fd8a. Config-only layer over accepted APIf2e; root-owned0444 `/opt/ocean/beta-host-config.json`, unchanged source validation, nonrootUID10001.
- Official proxy2.26.3 `gcr.io/cloud-sql-connectors/cloud-sql-proxy@sha256:f333a9c59890c3c67b8505166c5dbdcc0b29fca9173a2e09ca0446ab6997a736`, private IP/loopback5432.

Actual private Cloud SQL qualification succeeded: readback-r2gk5 observed initial
managed ownership; rollback-only qualify-xk4cm found no automatic memberships,
and left the fixed NOLOGIN probe absent. Native failure receipts remain immutable.
A reviewed one-flag `pg_stat_statements.track_utility=off` overlay was applied,
then fresh-session owner/bootstrap receipts verified it. Explicit empty-database
normalization to ownerpostgres succeeded under operator source8e2a163/image
`operator@sha256:0a89057b7459342e191e4b194628bee00cc7544749489df9f85f31508399e7b3`
(buildc6339079). The owner operation's23 guards and independent review passed.

Selected once, actual jobs all succeeded with structured operator completion and
successful provider execution:

- Owner `ocean-v1-beta-db-normalize-owner-rljsn`.
- Bootstrap `ocean-v1-beta-db-bootstrap-mktnv`: vector0.8.5, two restricted LOGIN roles, no memberships.
- Migrate `ocean-v1-beta-db-migrate-wvzh4`: all migrations through0021.
- Finalize `ocean-v1-beta-db-finalize-kbwr5`: exact serving table/column grants verified; no PUBLIC ACL or broad all-tables grant.

[Actual database stages](../beta/sql-20261102/backend-8e2a163/). Do not rerun
these executions, reinstall existing credentials or reset the database. Proxy
shutdown was acknowledged; the previously qualified distinction between provider
successful completion and a separately exposed operator exit line remains.

User selected exactly one verified Google **admin/internal** account for
`dilokkalayakul.jaronchai.p8@dc.tohoku.ac.jp`. Enrollment source8e2a163 and actual
image `enrollment@sha256:65592dada494d70dd5cb13cf923fc4c67172a7aa20648cb6ee5ce1c05f7fa564`
(build634ba0bf) are ready. Genuine Google SDK signature/issuer/audience/email verification succeeded.
One-shot execution `ocean-v1-beta-enrollment-first-account-g58sh` SUCCEEDED; its
structured result and new-connection readback verify exactly one active verified
admin/internal account. Temporary enrollment token accessor was removed and its
version1 destroyed after terminal success. The original unbounded log reader
refused a continuation token; an exact execution-time window found one outcome
and no continuation, recorded as a separate reader amendment. No account retry.
Real browser Google sign-in with that approved account returned to the beta root
and loaded authenticated navigation with the Administrator/Internal account badge.
[Enrollment evidence](../beta/enrollment-20261102/).

The immediate access milestone is complete. Screenshot and browser-observation
receipt are in backend-live-20261102. Research/catalogue are honestly unavailable
without configured services/data; Settings/About and the authenticated shell
are visible. Two temporary bootstrap password accessors were also removed after
all database stages completed. Preserve the working beta and continue remaining
service/data integration and broader checks separately. Scientific/queue/worker
dispatch, broad system/release acceptance and P2 D26-07 remain explicit later
gates. No release tag or complete-platform claim. Historical prospective sections
below must be read against this actual current continuation.

## Accepted software and images

App source `50566b7cfa4a0d8ee19686f0109e74f3a2a45d45` passes all five required
jobs in [CI41322838746](https://github.com/jarondlk/ocean-platform/actions/runs/41322838746):
6747 backend passes/626 explicit skips/83.67% coverage;318 actual PostgreSQL/
16 capability skips plus migration/upsert/backup/restore;132 legacy/1051 prototype/
50 host-unit+1 actual standalone HTTP cases. Coverage threshold remains70%.
The conditional push-only dependency review is skipped as configured.
[Hosted delivery](../beta/checkpoint-20261102/hosted-delivery/delivery.json).

The current880-path app identity is
`sha256:1d3b93f3abbf914d165982a43d4a24f830d975712029e7e5570cb0b868828128`:
841 unchanged accepted paths,3 intentional supersessions and36 additive paths.
5368 prior receipts,90 original C27 artifacts and42 protected paths are retained.
Later deployment wrappers have separate source/evidence; their changes are not
attributed to that earlier hosted app run. P2 D26-07 remains open.

Source-only containers built from packaging `7924a28`:

- Frontend: `asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/frontend@sha256:adb5bc75dbc56d146bdf6e63f83a3dc8b3867b0318de0c2c02ba6fc56023e9dc`
- API: `asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/api@sha256:f2e73ca98ba915e29a4dd7dc429e34a165475faa7f9000bc8cefaa10e5a6ee4f`
- Password-safe8b operator: `asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/operator@sha256:ccd38dae9065b73e89865434123abe07d984af906bf3da626961e727c9a37f3d`

Operator build `e403b44c-e92e-48fa-b94a-6b43d6a84b84` inasia-northeast1
is SUCCESS. Earlier756operator is superseded and must not be executed.
[Actual Linux smoke](../beta/builds-20261102/container-smoke-receipt.json)
for the frontend/API passes; the first failed harness attempt remains preserved.
Operator32pure/26guard/48actual native password-safety evidence and independent
review remain historical accepted local evidence, not CloudSQL qualification.

## Cloud target and financial boundary

Only new beta project `ocean-v1-beta-20261101`, number534831104543, Tokyo
asia-northeast1. Ambient gcloud project remains legacy: **every command must use
an explicit project**. CLI sign-in completed and actual authenticated reads and
reviewed writes succeeded; do not restart sign-in absent a new auth failure.

Beta-only target is¥50,000/month. Notify before exceeding it; the stated¥100,000
upper amount does not remove that notice gate. Saved beta-only all-service¥50k
alert and Cloud Run¥3k cap remain; neither is a whole-project hard cap.
The [31-day bounded public JPY scenario](../beta/quotes-20261102/README.md)
is¥35,604.05 with10% reserve and no credits. Actual usage/tax/invoice are separate.
No always-on worker/model/data acquisition is budgeted.

Private VPC/subnet, registry,4private buckets, initially separate runtime
identities,8initial empty secret containers and PAUSED Cloud Tasks queue exist.
The default Compute identity's automatic Editor was removed only in beta.
The dedicated build account has narrowly scoped source/registry/log access.
No legacy deployment/data/IAM/billing change is authorized.

## Private SQL and installed credentials

Private-only Enterprise PG16 `ocean-v1-beta-sql`, independent DB`ocean_v1_beta`,
Tokyo-zone-a/db-custom-2-7680/ZONAL/SSD20GiB/growth-limit30/private10.93.0.3,
connectorREQUIRED/ENCRYPTED_ONLY/backup7/PITR7/deletion protection are verified.
[Original settings](../beta/sql-20261102/settings-verification.json).

The reviewed logging overlay log_statement=none/log_min_error_statement=panic
was applied once, operationDONE, settingsVersion3/RUNNABLE, unrelated settings
preserved. QueryInsights remains defaultfalse. First preflight stopped on v1 vs
CLI beta4 response representation differences before mutation; the difference
was explicitly qualified and a fresh same-API comparison preceded application.
[Live flag evidence](../beta/sql-20261102/logging-policy/live-20261102/verification.json).
Actual session collector/logging attestation remains required before password SQL.

The reviewed installer successfully created4exact Tokyo secret containers and
installed7coupled versions: auth/internal/bootstrap DSN/migrator DSN/serving DSN/
migrator password/serving password. Only the independent instance's postgres
password was updated after all7versions were retained; UPDATE_USER reachedDONE.
[Metadata receipt](../beta/sql-20261102/setup/live-credentials-20261102.json).
Never rerun the installer, regenerate values or print/read payloads as diagnostics.

Two dedicated DB identities were created with zero user-managed keys, exactly
2instance-conditioned CloudSQL Client memberships and4secret-scoped Accessor
memberships. Unrelated IAM preserved; no project-wide secret access or runtime
Admin/Editor/key grant. [IAM proof](../beta/sql-20261102/iam-jobs-plan/live-20261102/verification.json).

No actual CloudSQL application role/schema migration has run. A limited-creator
native rehearsal exposed a deeper automatic creator-membership/grantor issue;
the proposed ordering-only fix is **not accepted**. Failed run, safe logs and
complete owned-cluster stop/removal are retained under
[bootstrap amendment](../beta/packaging-20261102/operator/bootstrap-order-amendment/).
A source-bound rollback-only qualification stage and finite provider metadata
are being prepared. Preserve strict zero-membership/finalizer checks; do not
weaken them or blindly attempt actual role bootstrap.

Actual Cloud Run validateOnly rejected the first body because job.name must be
empty on create. The owning renderer omits that output-only identity, retaining
external jobId and every other policy. All4corrected bodies received HTTP200 in
new validateOnly responses; no job was created/executed or reconciled by those
requests. Old50/four-case receipts, before-source and failed provider response
remain immutable. New operator source/revision/digest binding is still required.
[Create amendment](../beta/sql-20261102/setup/create-request-amendment/README.md).

## Beta domain and real Google OAuth

The exact child zone `beta.oceaninfobio.com` is delegated to e1/e2/e3/e4
CloudDNS servers. Managed certificate is now **ACTIVE**, exact beta domain
AUTHORIZED, expiry2027-01-30; map entryACTIVE.
[Fresh cert readback](../beta/dns-20261102/certificate-active-20261102.json).
There is no published servingA/AAAA, externalIP/LB/CloudRun service yet.

User specifically approved the single beta NS delegation in legacy project
`data-infra-infobio` / `oceaninfobio-com`, TTL300. It was applied once; four prior
non-SOA sets unchanged, provider SOAserial1→2 with other fields preserved.
[Exact authorization](../beta/dns-20261102/delegation-user-authorization.json),
[preservation proof](../beta/dns-20261102/parent-preservation-proof.json).
This exception does not authorize any other legacy mutation.

User completed Console passkey reauthentication and explicitly approved Google
API Services User Data Policy plus the independent web client and secret storage.
OCEAN Beta app remains EXTERNAL/Testing with0test users. Actual web client
`534831104543-4l3hm9dqd60u320mf73ql0d3s9rsuprn.apps.googleusercontent.com`
has only `https://beta.oceaninfobio.com/api/auth/callback/google` as redirect,
no JavaScript origins. App requests only openid/email/profile. Its secret is
ENABLED numeric version1 in ocean-v1-beta-oauth. It was privately transferred to
SecretManager; the temporary0600file/0700directory were removed, and no secret,
its hash or credential-page screenshot was exported into source/chat.
[OAuth metadata](../beta/oauth-20261102/credential-installation.json).
The browser is on the public Audience/Testing page; tab3 should be retained for
continuation. No genuine beta AppUser has been enrolled and no actual callback/
session exchange is accepted yet. Do not import legacy users or enroll by email.

## Immediate continuation

Root owns cloud mutation. Complete/read-only review the provider metadata and
rollback-only qualification amendment, run its owned native checks with honest
limited-principal results, commit/push the exact source and build an immutable
new operator image. Bind the renderer to that actual revision/digest and existing
numeric secret refs. Do not create or execute stale8b bootstrap definitions.

Use fresh target/IAM/job-operation checks. Create reviewed private job definitions
without running them; verify effective specs/source/SA/network/refs, then actual
readback/rollback-only qualification before bootstrap→migrate→finalize→readback.
Every real stage requires safe source-bound output, successful task/job state
and physical operator/proxy exit evidence. No timeout/retry/reset counts as pass.
Actual provider privacy, limited-superuser/C23 function-owner and managed
migration behavior remain gates until demonstrated.

Complete the concrete hosting plan for one bounded beta frontend/API/privateSQL
proxy service, real OAuth config and enrolled current account, then LB/certmap/
childDNS/HTTPS/defaultURL and cookie/UI checks. API loopback listener stays private;
its source-bound regular config-file and actual startup/probe behavior must be
qualified, not invented. Queue/outbox/private invocation/retained worker
integrations must precede any research/experiment dispatch. Absent scientific
providers report unavailable; no source/data import or scientific approval is
inferred from GCP permission. All20original live release gates and P2 D26-07 remain;
release acceptance is false. Keep unrelated/scientific files unmodified and
excluded from staging. [Cloud checkpoint](../beta/continuation-20261102/cloud-checkpoint.json).
