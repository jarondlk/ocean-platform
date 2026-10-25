# C23 local sandbox preparation contract

Version: `c23-sandbox-contract-v1`. This is the local implementation checkpoint
on `overhaul`, following delivered C22 source `66b4106`, CI `39539257759` and
metadata checkpoint `f4f702c`. C23 is In progress. It is not accepted execution.

Current scope amendment,2026-10-23: GCP setup/runtime installation/image builds
and synthetic tests for an isolated C23 worker are now explicitly authorized.
The no-provisioning statements below describe the earlier local checkpoint.
See [worker plan](C23_GCP_TEST_WORKER_PLAN.md) for actual isolated worker
configuration and unchanged real acceptance gates. Target/existing billing and
required C23 spending were resolved by the user's later authorization. Oct25
manual resume required browser reauthentication, restored at18:04JST. The same
worker was verified stopped then restarted with20:04JST STOP deadline. Actual
runtime gates remain.

The user confirmed there is no existing Linux/gVisor host and instructed that
real execution remain gated. No scheduler was resumed. No host installation,
VM start, scientific image build, generated Python execution, cloud resource
change or real-data operation is part of this checkpoint.

## Retained input and authority

`verify_execution_envelope` accepts C22's exact `metadata` and byte-valued
`files`, an envelope hash from the retained reservation, and a trusted
environment registry. It validates the strict metadata model, all five approved
hashes, context binding, cohort, complete manifest and exact file set. The
256 MiB ceiling includes code, manifest and files; narrower proposal bounds
apply. It preserves private integer and Unicode bytes without browser-number
normalization. The returned `VerifiedEnvelope` detaches mutable callers.

Verification is not admission. A new current C22 service check is required
before an effect or result publication. The caller cannot substitute a Boolean
approval or a newly calculated hash for the retained reservation. A changed
environment requires a revised proposal and new approval. Fake envelopes cannot
be promoted into real execution by changing an executor object.

The C22 application APIs, fake-only executor, approval history, reservation
limits and immutable capacity-release guards remain unchanged. C23's local
supervisor is not registered in the serving application. It releases no C22
reservation and creates no scientific publication.

## Local implementation boundary

The synthetic supervisor models deterministic job identity, journal fencing,
create/verify/start/observe/terminate/collect ordering, current admission,
cancellation and uncertain effects. Its runtime never interprets stored Python.
Every result must retain simulation and non-execution labels. An in-memory
journal is local test support, not durable execution or exactly-once evidence.
Cleanup does not depend on a revoked owner's permission to launch or publish.
Missing acknowledgements and stale epochs cannot imply termination or release.

Staging copies only approved code, manifest and file bytes into a private
create-only job tree. Reuse requires exact immutable bytes and safe file types.
Output validation reads a trusted extracted directory only after a future
adapter proves all untrusted writers stopped. It must reject unsafe paths and
file types, unexpected/missing outputs, malformed formats and exceeded bounds.
Table and raster support is deliberately bounded; unsupported formats require
a revised proposal. Aggregate output accounting includes logs and manifests.
Raw machine artifacts stay distinct from any human CSV presentation.

The OCI/profile renderer is configuration preparation. It must not invoke an
engine, download an image or establish eligibility. Rendered limits, namespaces
and deny-network flags are not proof of enforcement. A recipe, fabricated digest
or structural test receipt cannot become an accepted scientific environment.

## Mandatory outstanding acceptance

| Gate | Required evidence before C23 completion |
|---|---|
| Environment | Authorized compatible Linux host, complete pinned gVisor installation, verified materialized image identity, exact Python and hash-locked scientific dependencies |
| Containment | Actual denial of external/metadata networking, host files/sockets, credentials, package installation and unauthorized mounts |
| Resources | Measured CPU/memory/process/time/input/output/log/scratch enforcement covering the complete job |
| Termination | Actual descendant termination and trusted runtime cleanup; uncertain effects retain capacity |
| Output retention | Tested extraction/retention ordering that preserves bounded outputs while preventing untrusted writer races, including tmpfs lifecycle |
| Durability | Real journal/worker reconciliation and narrow verified-termination reservation-release integration; memory fakes do not establish either |
| Science | Repeated numerical fixtures under the exact image, explicit seeds and declared tolerances; execution success is separate from scientific correctness |

Actual runtime adapters and separately marked Linux/gVisor acceptance remain
future work. Ordinary host Python, the default Podman runtime and unit mocks
cannot clear those gates. C24 target configuration and provisioning/deployment
authorization remain separate. C23 cannot be marked Complete, nor can its
completion be inferred by later components, while these gates are outstanding.

## Hosted preparation and later authorization

Source `b8e929e` passes CI39578854643 (5556 backend,275 actual PostgreSQL,
930 v1/132 legacy tests; all four required jobs). The separate
[hosted receipt](evidence/C23/hosted-preparation.json) retains raw decoded logs
and verifies all17 preparation source hashes. This is software preparation
evidence; no runsc installation or real containment test occurred in those jobs.
The user's later GCP approval removes the missing authorization for a temporary
test worker. It does not satisfy any mandatory acceptance row above. No worker
existed at that historical checkpoint. The worker/image were prepared onOct24;
Oct25 browser reauthentication is pending. Scheduled continuation remains PAUSED.

## Additive operator preparation — 2026-10-25 JST

The durable journal is record-only and holds an exclusive per-job OS lock
through physical effects. Crash/reboot/lease loss never proves termination.
The separately pinned trusted init mounts only fixed guest output/scratch
tmpfs filesystems, verifies byte/inode quotas, drops its transient mount
capability before forking, drops all analysis capabilities and reaps descendants
before bounded extraction. Explicit readonly temporary mounts suppress runsc's
otherwise automatic writable `/tmp`. These are reviewed implementations;
actual Linux enforcement remains a mandatory gate.

The real adapter is reachable only through an explicit operator harness. The
harness's generated synthetic fixture is not retained real C22 approval, has no
C22 reservation consumption/release authority and cannot enable serving dispatch.
Its host-positive controls and fresh target/boot-bound network-isolation records
must establish no external IP/NAT before an actual test runs. Journal, profile,
runtime, materialized rootfs, wrapper, input and output identities remain pinned.
The initial image/receipts stay immutable when the quota amendment is rebuilt.

The retained C22 bridge and narrow proof-backed release path remain design-only.
They must be verified separately after containment; the operator synthetic
fixture cannot clear the Durability reservation-release gate in the table.
