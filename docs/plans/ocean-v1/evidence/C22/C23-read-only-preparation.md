# Conditional C23 preparation — read-only, not selected

Prepared during C22 acceptance on `overhaul`, parent source base
`69123408c5bf9caaefe365ef0fc05905c70984c5`. C22 hosted delivery and final C23
formal readiness were pending at this inspection. This document selects no
component, changes no application contract, and proves no runtime containment.
Reconcile these source pins with accepted C22 delivery before implementation.

## Observed local boundary

The authorized inventory consisted only of `uname -a`, `command -v docker
podman runsc limactl colima`, and the locally present client's `podman --version`.

| Observation | Result |
|---|---|
| Host | Darwin kernel27.0.0, arm64; macOS host, not a Linux worker |
| `docker` | Not found on current PATH |
| `podman` | `/opt/homebrew/bin/podman`; `podman version 5.4.2` |
| `runsc` | Not found on current PATH |
| `limactl`, `colima` | Not found on current PATH |
| Guest/runtime availability | Not inspected; a Podman client does not establish an existing Linux guest or gVisor |
| Containers, builds, installs, generated Python, network/cloud calls | None run |

The actual Linux/gVisor containment gate is unavailable on the observed host.
Do not replace it with ordinary host Python, the Podman default runtime, a mock,
or existing container smoke tests. An explicitly authorized compatible Linux
host, installed/pinned gVisor runtime and real scientific image are required for
that gate. No permission to install a host runtime or provision Linux/cloud is
inferred from this preparation.

## Existing immutable input and dispatch seam

`ResearchExperimentService.load_execution_envelope(reservation_id,user=None)`
returns `{'metadata':..., 'files':Mapping[str,bytes]}`. Its current path verifies
fresh owner/context, active proposal head, exact retained approval and all five
proposal/code/input/environment/resource hashes, then regenerates the scientific
export under current source/publication policy and closes fresh DB authority.
Metadata version is `c22-execution-envelope-v1` and includes site, experiment,
proposal revision, owner, reservation, approval, five-field context binding,
full proposal, environment, hashes and the exact input manifest. The reservation
binds the canonical metadata hash. Files are exact immutable machine inputs;
private int64 values must not enter browser-number normalization.

C23 should consume this exact return, not reinterpret catalogue rows, C21
previews, natural-language scope or a client-provided approval Boolean. Internal
`VerifiedExecutionEnvelope` can be a typed wrapper around validated C22 bytes,
computed envelope hash and trusted fresh-admission receipt; it must not invent
new source/publication authority. Recompute every hash and verify actual file
names, byte counts, code UTF-8 and environment identity immediately before
staging. Recheck current admission immediately before launch and before result
publication; a saved authorization receipt cannot grant current access.

Current dispatch is deliberately fake-only: the C22 service constructor admits
`FakeExperimentExecutor` exclusively, its accepted acknowledgement says
`execution_performed:false`, and stable delivery IDs deduplicate exact metadata.
C23 must add a distinct explicit supervisor adapter with a default-off real
execution gate. It cannot relabel an existing fake acknowledgement or mutate
C22's historical `execution_performed:false` envelope into a true result.

Reservations remain occupied for `reserved`, `accepted` or `uncertain` states.
The current ORM/native design forbids C22 releasing accepted capacity. C23 needs
an additive execution record and narrow verified-termination release contract,
with native constraints: an expired lease, missing acknowledgement or cancelled
HTTP request never proves the process stopped. Retain one active job/owner and
two globally under the existing capacity lock. Redelivery reconciles the same
reservation/runtime job ID; it never launches another job to obtain an answer.

## Proposed minimal internal ports

Names are design suggestions, not added code:

- `verify_execution_envelope(c22_envelope, *, admission, environment_registry)
  -> VerifiedExecutionEnvelope`: pure exact bytes/hash/schema checks plus the
  separately supplied trusted fresh admission boundary. Caller supplies no
  runtime binary, mount path, image, shell command or storage credentials.
- `ExperimentSupervisor.execute(verified, *, journal, runtime, cancelled)
  -> ExecutionResult`: persist preparation/launch intent before external effect,
  use deterministic job identity from site+reservation+envelope hash, reconcile
  uncertain launch/termination, and atomically publish validated terminal result.
- `SandboxRuntime.preflight(profile)->RuntimeAttestation`,
  `start(job_id,staged_bundle,profile)->LaunchReceipt`,
  `inspect(job_id)->RuntimeObservation`,
  `terminate(job_id)->TerminationReceipt`: explicit Linux/gVisor implementation
  and a distinctly labelled deterministic fake. Absence of the real adapter or
  verified enforcement fails closed. No automatic engine/runtime fallback.
- `validate_execution_outputs(output_dir, *, expected_outputs, limits)
  -> ValidatedOutputSet`: trusted post-termination FD-based collection, exact
  hashes and typed previews. It performs no scientific approval/publication.

Suggested execution states are prepared, launching, running, terminating,
succeeded, failed, timed_out, cancelled, unavailable and uncertain. Model launch
intent/observations/termination acknowledgements as append-only records; lease
owner/epoch fences prevent stale workers publishing results or releasing slots.
The journal is not a claim of exactly-once kernel execution. Unknown effects
remain uncertain and retain capacity until inspection proves the same job gone.
A prelaunch refusal may say execution was not performed only when the journal
and runtime reconcile that fact. Clock rollback/nonfinite observations fail
closed; trusted monotonic wall-time enforcement continues across controller
polling and includes descendants of the sandbox process.

## Scientific image and runtime profile

Prepare a dedicated sandbox image recipe and lock surface. Do not reuse
`Containerfile.api`: it copies the application and database clients and includes
model/cloud/database libraries. Current runtime locks pin NumPy2.5.3,
Pandas2.3.3, PyArrow23.0.1 and SciPy1.18.1. The analysis lock adds Matplotlib3.11.2
and Pillow12.3.0. No `statsmodels` pin exists in the inspected requirements.
These are inspected repository values, not a newly accepted C23 environment.

A complete C23 descriptor must bind the exact scientific image digest, Python
patch version, dedicated hash-locked dependency file and versions of NumPy,
Pandas, PyArrow, SciPy, statsmodels and Matplotlib. A Containerfile recipe or
request-supplied SHA is not a verified image. Prepare lock-generation/build
instructions and offline integrity checks; keep the real digest/configuration
unavailable until an authorized Linux build and image inspection produce it.
Never invent package hashes, an installed statsmodels version or an image digest.
Use `--require-hashes` at an authorized build stage and remove installation
entrypoints from the final image. Include no project source, production
credentials, service account files, database libraries or host tool sockets.

The fixed runtime profile should validate an OCI configuration against the
approved image and a pinned runtime/profile version, with no arbitrary overrides:
non-root UID/GID; read-only rootfs; independent PID/mount/IPC/UTS/network/user
namespaces; no external network/routes; dropped Linux capabilities and
no-new-privileges; fixed minimal environment; no host networking/devices/sockets,
Docker/Podman sockets, credential directories or arbitrary host mounts.
Inputs, manifest and exact code are staged under a private immutable read-only
root. Only bounded output and scratch directories are writable. `/proc` and any
minimal devices must be sandbox-local, never a host bind. No GPU or privileged
mode is supported. Package/network capability denial is enforced by the runtime,
not by Python AST filtering.

Enforce proposal limits at the kernel/runtime boundary: at most2CPU,4GiB,
600seconds,256MiB input bytes and50MiB output bytes. CPU/memory/PID enforcement
must cover all processes/threads; measured cgroup controller availability and
runtime configuration become preflight evidence. A per-file `RLIMIT_FSIZE` alone
cannot enforce aggregate output/scratch size. Use bounded mounts/quotas and
bounded stdout/stderr pipes, counting every collected output/log/manifest byte.
A scratch filesystem also needs a fixed quota; it cannot create an unbounded
disk or evade memory accounting. Additional hard PID/FD/thread caps belong to a
versioned fixed safety profile, not arbitrary request values.

Seeds remain the explicit proposal mapping. Preserve exactly what was declared
and any observed reproducibility limitations. A seed or library-thread setting
is not proof that arbitrary generated Python used it or is deterministic.
Do not silently invent seeds. Numerical fixtures declare seeds and tolerances
and compare repeated real sandbox results under the exact same image/profile.

## Trusted output boundary and result retention

Stop and establish whole-job termination before collecting output files so the
untrusted writer cannot race validation. Traverse only the designated output
root with directory FDs, no-follow open/stat semantics, regular-file/nlink
checks, bounded depth/file counts and exact declared names. Reject traversal,
absolute paths, symlinks, hardlinks, device/FIFO/socket files, unsupported formats
and missing required outputs. Hash actual bytes from stable FDs. A table suffix
alone is not validation. Use explicit bounded format profiles (for example strict
UTF-8 JSON/CSV or verified Parquet with decoded-row/size limits) and bounded PNG
raster decoding/dimensions. Reject SVG, HTML, notebooks, pickle, archives and
executable artifacts. Any unsupported requested output format must refuse
before launch or require a new reviewed proposal, not guess a preview format.

Any separate human CSV follows C07 escaping and has a separate hash from exact
machine bytes. Never interpret returned Markdown/HTML as trusted UI. Render logs
as quoted text; preserve bounded raw log hashes/truncation metadata and safe
failure classifications. Exit0 without required validated outputs does not
satisfy success. Distinguish runtime success, output validity and scientific
correctness. Partial validated outputs after failure/cancellation may be retained
with explicit partial authority; no result updates source classifications,
physical relationships, operational publication or C21 accepted facts.

`ExecutionResult` should bind reservation/delivery/execution IDs, envelope and
five proposal hashes, image/lockfile/runtime/profile identities, explicit seeds,
observed start/end/elapsed time, exit code/signal, termination proof, resource
observations, bounded log descriptors and validated output manifest. OOM,
wall timeout and unknown killed states require actual runtime observations;
exit137 alone does not distinguish them. Results and accepted artifacts are
immutable, experimental and owner scoped. Reopen/download requires current
owner and source/publication policy, even when dispatch is disabled.

`ArtifactStore` already offers immutable content hashes and generation-conditional
registration, but uses512MiB/4000-file defaults and has no experiment-specific
namespace. Those bounds are too wide for C23, and publish itself is not an
untrusted-output validator. Prefer additive owner-bound result/blob records and
an explicit validated artifact sink; if using ArtifactStore later, add a separate
v1 experimental namespace after the same prepare-before-write protection
protocol. Never borrow a legacy/operational `analysis` publication namespace.
`research_analysis_bundle.py` reads production-style DB/source heads and performs
manual publication; it is a shape/regression reference, not an execution or
input-discovery dependency. Existing security config/container scripts prove
serving configuration and limited image inventory, not gVisor containment.

## Work possible after C22 delivery and formal selection

Local independent work can implement strict envelope/result contracts, journal
state and capacity-release guards, deterministic fake supervisor tests, safe
staging/output validators, fixed OCI/profile rendering checks, dedicated image
recipe/lock preparation and marked Linux integration harnesses. These are useful
checkpoint evidence on this Mac and may stay disabled without any host install,
container execution or cloud target. They cannot complete C23 by themselves.

Before real acceptance, obtain an explicitly authorized Linux/gVisor environment,
exact runtime/image identities and enforcement capabilities. Run synthetic
containment probes for external network/metadata services/host-file/socket
access, child-process-tree kill, input tamper, traversal/symlinks, image mismatch,
wall time/memory/PID/aggregate disk limits, cancellation/uncertain recovery and
repeatable numerical fixtures. Record actual commands, exit statuses, source
pins and cleanup. Unit mocks cannot satisfy these gates. C24 cloud configuration
and paid/provisioning/deployment work remain separately scoped and unapproved.

Suggested ownership after selection: root owns shared contracts/C22 bridge and
flags; a persistence delegate owns additive execution/result/lease models,
migration/native tests and verified capacity release; a supervisor delegate owns
trusted lifecycle/real gVisor adapter and deterministic fakes; a validation/image
delegate owns staging/output validation, image/profile files and synthetic
fixtures. Keep source ownership disjoint and explicitly freeze interfaces before
parallel edits. Final required regressions include existing artifact/security
checks plus new focused and separately marked real Linux/gVisor acceptance.

## Inspected source pins

These are preparation-time pins, not accepted C22/C23 receipts. Root C22 source
and final delivery may supersede them intentionally; preserve the original map.

| Path | SHA-256 |
|---|---|
| `docs/plans/ocean-v1/components/C23-python-sandbox.md` | `9fc448f311589b890d031b26a7f26824198d89cabb848e47c36d73582c219454` |
| `docs/plans/ocean-v1/components/C24-gcp-worker-configuration.md` | `45be7aa251a5713e187f85fd79c370efefe5e0377b1ed8bf28e732ef1b406940` |
| `orchestration/research_experiments.py` | `bab02f05549655977e2f95ef7885a59d3a311c3ad64941b0846d79b94b0db2ee` |
| `schema/research_experiments.py` | `3623b8ce0349316f5e28597752a798817acc1641d55e05d3614ebd61f0d87494` |
| `orchestration/frozen_experiment_export.py` | `6edb1ab644d0c8af4900b0880de68163114bc76ba1262cc3309f323738071099` |
| `db/app_models.py` | `3c61bec6fb134f26e05efd304f5d6c84cd7ef4b715cc6a356d2519e57536c1e3` |
| `ingestion/artifact_store.py` | `dc085280b1594f58eb503303ec7fcf1ac0778d076c1e0e6e2d0ea006f329626e` |
| `ingestion/research_analysis_bundle.py` | `3ad061b22f56d06f86068782d3efbf6e35395ec2660b353bb6bb6bb78fe312dd` |
| `Containerfile.api` | `b8c81257c8368841dde53d74a949ca872e10f4fe44c2f8d9cdd439c047a2477c` |
| `requirements/runtime.in` | `056d71fcbf99db94c05b911655e605bdd8afefd8f24f1ca51c819df153435c64` |
| `requirements/runtime.txt` | `6b0bb8d53fde43edb0d23370f17f32ceb7243a0545071dc31bceaced55b19f81` |
| `requirements/analysis.in` | `63c7b7aaf5aebf9c54352448d1d01473b476a6819bfee47c280fab07def13238` |
| `requirements/analysis.txt` | `ef4312330b7f457d14705f96841d2e35d9d4baff39a4ccbc73bedbb8fcc24fbe` |
| `tests/test_security_config.py` | `7e0e7b4fc14954c28784578ad8c95d5ba2094df0f4b5625ab8aad3422a935034` |
| `scripts/verify_runtime_security.sh` | `3f2c538e2ae4fa6678c0afe09880fba1660c24dadd3fea14eea216b4efef37fc` |
| `scripts/verify_candidate_containers.sh` | `a79456ebf3651b8270033f5ae03709ad2b9dcad94d6f271589e3d8d6e8e43f50` |
| `scripts/render_gcp_templates.py` | `7c081a49751c785baad7a207fa25775b5066db96eb242158d6ba12a9c4315c7f` |
