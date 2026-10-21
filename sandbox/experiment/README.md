# C23 scientific sandbox preparation

This directory is **not an available runtime**. The user confirmed that no
Linux/gVisor host is available and real execution must remain gated. Nothing in
this directory downloads software, installs a runtime, starts a VM/container,
builds an image, provisions cloud resources or runs a proposal automatically.
`image-readiness.json` records `ready:false`; no image digest, statsmodels version
or wheel hash has been invented. C23 cannot be marked Complete from these files.

## Offline image materials

The dedicated recipe copies a scientific installation prefix only; it does not
copy repository/application sources, a serving image, environment files,
credentials or database clients. A pinned base is still an external trust input:
review its provenance/content before a separately authorized build. A string
digest alone does not prove that a base or resulting filesystem is appropriate.

Before any authorized build, provide all of the following in a private build
context made from this directory:

1. `build-materials.json`, replacing the intentionally invalid template. Bind
   one exact locally available base reference ending in `@sha256:…`, its exact
   Python patch, the complete installed package/version inventory, and the SHA256
   of the exact dedicated lock. Include NumPy, Pandas, PyArrow, SciPy, statsmodels,
   Matplotlib, packaging and every required transitive distribution.
2. `requirements.lock`, generated/reviewed for the selected Linux architecture
   and Python. It contains only exact `name==version` requirements with verified
   SHA256 wheel hashes. No editable sources, URLs, indexes, includes, extras,
   conditional requirements or source distributions are accepted. The serving
   and analysis locks are references, not accepted C23 scientific environments.
3. A verified local `wheels/` directory containing those pinned wheels. The
   recipe uses no index, requires hashes, selects binary wheels only and does not
   resolve/download dependencies. Its installed inventory and dependency graph
   must match the complete manifest. Missing/incompatible wheels fail the build.

Obtain concrete authorization and a build tool/target before building. Use a
preloaded verified base and an offline build with no network or automatic pull.
No build command has been executed for C23. The missing non-template materials
make the supplied recipe intentionally unbuildable until operator preparation.

The runtime stage removes pip, setuptools/wheel installer components, ensurepip,
venv and their command wrappers. Cleanup is guarded by a Linux-only private
image-build marker and explicit build environment. The helper verifies exact
Python, complete package versions and installed dependency constraints, then is
removed from the final image. The recipe sets non-root UID/GID65532. These are
recipe properties, not observations of a built image or containment evidence.

After an authorized build, retain the platform-specific OCI manifest digest,
config and layer hashes, lock/package evidence and authenticated materializer
receipt. OCI root-filesystem extraction and runtime-configuration conversion are
separate operations; `runsc` does not establish that an arbitrary directory
matches a requested image. [OCI image conversion](https://github.com/opencontainers/image-spec/blob/main/conversion.md)

## Fixed render-only profile

`orchestration.experiment_sandbox.profile.render_oci_profile()` consumes a
verified C22 envelope and trusted configuration-only image/runtime preparation
records. It rechecks the exact staged bytes and no-follow rootfs inventory,
matches image/lock/Python/package/architecture identities and returns detached,
hash-bound configuration. It never returns execution eligibility or invokes a
binary. A structurally valid preparation receipt is not runtime authority.

The plan uses a read-only rootfs and input bind, non-root application UID, dropped
capabilities, explicit private namespaces, no hooks/annotations/host devices and
a minimal fixed environment. Required OCI namespaces must be explicit because
omitted namespace types inherit the runtime's namespace.
[OCI Linux configuration](https://github.com/opencontainers/runtime-spec/blob/main/config-linux.md)

Only guest `/outputs` and `/scratch` tmpfs mounts are writable; they have fixed
byte/inode limits. No writable host mount is substituted. The output allocation
reserves space for bounded stdout, stderr and the retained manifest; file/scratch
allocations round down to page boundaries. This initial profile refuses output
budgets below8192bytes or non-page-aligned memory instead of broadening approval.
It retains declared seeds exactly and does not inject an unrequested random seed.

Networking is explicitly disabled with `--network=none`; a private network
namespace and denied host sockets/FIFOs are required. The profile disables
Directfs, overlays and OCI flag overrides. gVisor's documented overlay default
can use host-backed storage, so the configuration requests no overlay. These
flags must be verified against the selected pinned release.
[Networking](https://gvisor.dev/docs/user_guide/networking/),
[filesystem](https://gvisor.dev/docs/user_guide/filesystem/),
[official flags](https://github.com/google/gvisor/blob/master/runsc/config/flags.go)

Do not use built-in rootless mode as a fallback: its documented limitations
include unavailable `create` support and ignored cgroup configuration errors.
The plan requires a capable trusted Linux supervisor and non-root application
inside the sandbox. Full runtime installation pins include runsc, the shim and
every adjacent `gvisor-bin` sidecar, rather than one executable alone.
[Rootless limitations](https://gvisor.dev/docs/user_guide/rootless/),
[installation](https://gvisor.dev/docs/user_guide/install/)

Stage files remain0400. The preparation record explicitly maps the non-root host
input owner to application UID/GID65532 and refuses host UID/GID0. Real Linux
namespace/gofer ownership and readability must be demonstrated; this pure render
does not prove those semantics. It neither invents a host subuid allocation nor
broadens staged file permissions. An incompatible mapping remains unavailable.

## Mandatory unverified gates

No Linux image/runtime has been built or launched here. Before real eligibility:

- Verify the complete installed release/sidecars, private state root, supported
  flags, authenticated image materialization, immutable rootfs and exact inputs.
- Create the sandbox before untrusted code starts, then read back actual cgroup
  CPU quota, memory/swap and host PID settings. Verify namespace/mount limits,
  aggregate tmpfs/inode limits and bounded log pipes. Host PID accounting alone
  cannot establish a guest-process cap; gVisor virtualizes guest processes.
- Resolve and test race-free extraction of guest tmpfs outputs after all guest
  writers terminate and before storage is destroyed. No extraction mechanism is
  invented here. The host output validator accepts only an independently trusted
  extracted directory; it does not supply the missing runtime operation.
- Verify watchdog/cancellation and whole host-subtree teardown of Sentry/gofer.
  A stopped initial process, absent state, lost acknowledgement or lease expiry
  cannot release capacity. C22 reservation/release guards remain unchanged.
- Run actual no-network/metadata/host-file/socket/package-install probes, input
  tamper checks, process-tree/time/memory/disk limits and repeated scientific
  fixtures with explicit seeds/tolerances. Simulated/configuration tests cannot
  prove containment or scientific correctness.

The cgroup memory observations must account for all job memory rather than
assuming anonymous memory is the complete workload.
[gVisor resource model](https://gvisor.dev/docs/architecture_guide/resources/),
[kernel cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)

Primary documentation was inspected on2026-10-21; documentation and source
inspection are distinct from actual runtime acceptance. Unsupported flags,
missing controllers/quotas, rootfs provenance uncertainty or unresolved output
extraction keep the gate closed. No production dispatch path is built by C23's
current local preparation.
