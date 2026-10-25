# C23 operator Linux adapter checkpoint

The new `orchestration/experiment_sandbox/linux_runtime.py` is an operator-only
acceptance adapter. It is not registered in a serving API, worker dispatcher or
C22 release path. Its result always retains `dispatch_eligible:false`,
`reservation_released:false`, scientific-unverified and runtime-acceptance-false
labels. A completed operator job is not a completed C23 component.

The frozen local run passes **78 cases and Ruff**, including three actual
SQLite/flock interoperation cases with all runtime effects mocked. Its117 local
import-source paths are unchanged before/after checks, as are all17 original
C23 preparation source files and four prior receipts. This is host-safe control
acceptance, not a Linux/gVisor containment result.

Receipt: `local-20261025-01/verification.json`.

## Public operator interface and layout

```python
adapter = LinuxExecutionAdapter(
    worker_root, runtime_directory, runtime_manifest, durable_journal,
)
result = adapter.run(
    verified_envelope,
    prepared_execution_profile,
    admission=current_retained_envelope_hash,
    cancelled=operator_cancellation,
)
```

`admission(envelope)` must freshly return that retained envelope's exact hash,
not a Boolean or a recomputed caller assertion. It is checked before launch and
publication, and again on replay. The pure `VerifiedEnvelope` check itself grants
no current authority. Synthetic operator fixtures must retain their explicit
qualifications; this module cannot manufacture a real C22 or scientific approval.

`worker_root` and `worker_root/<job_id>` are canonical supervisor-owned0700
directories. The job contains approved `inputs/` owned by the mapped analysis
owner with0500 directory/0400 files, and an independently materialized **host
read-only mount** at `rootfs/`. New profile-v3 validates application/control UID
separation and the sealed init byte pin. The adapter writes its own0400
`config.json`, a private sibling `runsc-state-<job_id>`, and private retained
outputs/diagnostics. No writable host mount is passed to the analysis.

The actual runtime directory is
`/opt/ocean-c23-runtime/release-20261019.0`. Root-owned runsc, shim and every
adjacent sidecar must match the complete trusted manifest; directories cannot
be group/other-writable. The adapter source used by its helpers is itself hashed
and checked. There is no ordinary container or native-Python analysis fallback.

The private journal is `DurableExecutionJournal`, on this host's local private
filesystem and current boot identity. Its real SQLite driver must satisfy that
module's WAL-reset-fix checks. The scientific guest image does not receive the
journal, database packages or SDK credentials.

## Launch, watchdog and cleanup boundary

All effects remain inside the durable journal's claim/flock context. First
preflight checks Linux/root, real cgroup-v2 mount, boot identity, installed
runtime hashes, profile/input/rootfs integrity and a host-read-only rootfs.
The base `/sys/fs/cgroup/ocean-c23` must already expose and enable CPU, memory
and pids controllers. Per-job limits are applied to its outer group, with
`host/` for trusted runtime control and `sandbox/` for the gVisor child.
Both outer and inner exact CPU/memory/swap/pids readbacks precede start.

The runtime and independent watchdog use fresh Python **`-I -S -B`** processes.
The module's direct-script branch exits before project/scientific imports.
No Python `os.fork` or `Popen(preexec_fn=...)` runs after importing native thread
pools. Only scoped cgroup/control pipe FDs are inherited; SDK/journal descriptors
and environment values are not passed.

Each launch helper sets `PR_SET_PDEATHSIG(SIGKILL)` and rechecks PPID. It checks
parent liveness, its cancellation pipe and the approved deadline before and
after cgroup placement, then FD-executes the same hash-verified runsc ELF. This
blocks a queued command from entering late after cleanup has killed an empty
group. The cancellation writer is parent-only/CLOEXEC; closing it on abort
prevents later launch. The helper never introduces an `exec` guest command.

The independent watchdog is intentionally outside the job group. It retains
only that exact group's kill FD and a parent-liveness read pipe, acknowledges
READY before any create, and kills on parent EOF or the approved deadline.
Controller polling checks it remains alive. Missing READY refuses execution.
These local tests inspect the mechanism; actual Linux death/FD behavior remains
an acceptance gate.

After the sealed init reaps all guest writers and extracts its private tmpfs
bytes, the adapter retains the bounded frame from the original create stdout.
It kills the outer host group immediately, performs bounded trusted delete,
kills again, and requires the same device/inode group's `populated0` readback.
Only then can it decode/validate/retain outputs and freshly admit publication.
Missing state or a lone PID's exit is never a whole-job proof. Unknown delete
acknowledgement, stale fences, lost effects or journal failures yield uncertainty
and no outputs/release. Reacquired nonterminal jobs reconcile; they never rerun.

## Private forensic diagnostics

Every real control command retains create-only0400 stdout/stderr prefixes and
metadata in private0700 `job/diagnostics/<stage>-<nonce>/`. Captured and retained
byte hashes, sizes, observed exit status, stage and honest EOF state remain
distinguishable. Runtime stderr is capped at1MiB and non-create stdout at64KiB.
The large create transport body is hashed/count-recorded rather than duplicated.
These are per-command bounds; no aggregate unlimited-retry host-disk bound is
claimed. Parent directory entries and retained output/diagnostic files are
fsynced. Diagnostic-write failure cannot prevent the outer kill/empty finally
path, and prevents result publication.

## Exact runtime behavior still to verify

The controller assumes the pinned release implements its fixed flags, preserves
guest stdio through `create`/`start`, reports created state with the exact job ID,
bundle and a PID inside the outer group, and returns wait JSON `{id,exitStatus}`.
The implementation was informed by official runtime/kernel interfaces; source
inspection is distinct from observing this release on the authorized Linux host.
[gVisor create](https://github.com/google/gvisor/blob/master/runsc/cmd/create.go),
[wait](https://github.com/google/gvisor/blob/master/runsc/cmd/wait.go),
[state](https://github.com/google/gvisor/blob/master/runsc/cmd/state.go),
[kernel cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)

Real flags/FDexec/readbacks, parent death/deadline/queued-launch races, whole
Sentry/gofer termination, trusted-init quota/capability/drop/ownership semantics,
safe frame retention, containment probes and repeated scientific fixtures remain
mandatory. Root owns the separate GCP harness and real receipts. No cloud action,
generated analysis execution, original receipt rewrite or C22 bridge modification
was performed by this local checkpoint.
