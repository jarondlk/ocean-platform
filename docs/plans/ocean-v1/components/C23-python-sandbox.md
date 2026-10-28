# C23 — Isolated Python execution

**Status:** In progress. Retained C22 reserve/start/publication, held runtime
context, native cleanup/physical issuer and lifecycle runner are implemented
locally. Physical software gates pass639 cases; retained reserve/lifecycle/edge
checks pass26 actual PostgreSQL cases with shutdown verified. These are inert
runtime/software-signature tests. Actual retained Linux execution, physical
proof and independent capacity release remain mandatory; the guarded synthetic
GCP harness is being prepared. Pushed91ebe81 backend6392/85.61percent and both frontends pass; PostgreSQL
timed out at15minutes. Exact new-source hosted delivery remains
required. C24 has not started. **Prerequisites:** C22.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Execute an approved, immutable Python analysis envelope with reproducible inputs and bounded outputs, while keeping generated code outside the serving application and production data boundary.

Include sandbox/supervisor interfaces, pinned scientific environment, local synthetic fixtures, output validation, cancellation and containment checks. Exclude provisioning Linux workers, installing host runtimes without authorization, running actual user experiments, production credentials and cloud execution. Infrastructure configuration belongs to C24.

**2026-10-23 scope amendment:** the user explicitly approved GCP use. Authorized
C23 work now includes an isolated temporary Linux/gVisor test worker, runtime
installation, scientific image preparation and synthetic cloud acceptance. This
supersedes the earlier cloud-execution exclusion for that test environment.
The user subsequently authorized required C23 spending on existing billing;
target/billing selection was resolved on2026-10-24. No new cap is required.
[Worker plan](../C23_GCP_TEST_WORKER_PLAN.md). No legacy deployment or real-data
operation is included, and C24's whole-site acceptance remains separate.

## Verified entry points and contracts

Inspect [artifact storage](../../../../ingestion/artifact_store.py), [analysis bundle conventions](../../../../ingestion/research_analysis_bundle.py), [security configuration tests](../../../../tests/test_security_config.py) and [runtime requirements](../../../../requirements/runtime.txt). Existing ingestion jobs are not an isolation boundary for untrusted generated analysis code.

Use a dedicated Linux gVisor sandbox invoked by a trusted supervisor. The supervisor verifies C22's approval envelope, stages frozen inputs read-only and collects validated outputs. It retains production/storage credentials outside the sandbox. Deny external networking, host sockets, metadata service access, package installation and writable host mounts. Fail closed if isolation or resource enforcement cannot be established.

Pin Python and scientific dependencies including NumPy, Pandas, PyArrow, SciPy, statsmodels and Matplotlib by image digest and lockfile. Set two CPUs, 4 GiB memory, ten minutes, 256 MiB inputs and 50 MiB outputs. Enforce limits at the runtime boundary; subprocesses are part of the same job. Retain image identity, input/code hashes, seed declarations, logs, exit status and output manifest. Seeds must be explicit when randomness is used, not silently invented to imply determinism.

Allow validated table files and raster plots for previews. Reject escaping paths, symlinks, excessive outputs and unsafe artifacts; do not execute notebooks or HTML in the app. Execution success remains separate from scientific correctness.

## Resumable checkpoints

1. Define supervisor/executor envelope and result contracts with a fake runtime; validate image, inputs and approval hashes before launch.
2. Implement pinned image and gVisor launch configuration with staging, limits, timeout/cancellation and clean termination; build no production dispatch path.
3. Add containment and output-validation tests using synthetic inputs. If a compatible isolated Linux environment is unavailable, record unverified runtime gates rather than substituting ordinary host Python.

## Future verification and acceptance

Existing regressions: `python -m pytest tests/test_artifact_store.py tests/test_security_config.py -q`. Add executor unit tests and separately marked Linux/gVisor integration tests during implementation; record exact commands and environment requirements in `handoffs/C23.md`.

Acceptance includes no network/metadata/host-file access, whole-process-tree termination, input tampering, output traversal, memory/time/disk limits, image mismatch and repeatable numerical fixtures within declared tolerances. Unit mocks cannot prove containment. Real containment gates must pass before experimental dispatch becomes eligible; an unavailable runtime must remain an explicit blocker.

## Compatibility, rollback and handoff

Keep execution independently disabled by default. Rollback stops dispatch and retains approved inputs/results. Update [status](../STATUS.md) and `handoffs/C23.md` after each checkpoint, distinguishing simulated tests from actual containment evidence and naming any missing host prerequisite.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c23). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.


## Implemented local checkpoint — 2026-10-21 JST

Strict byte/hash contracts, synthetic supervisor ports, bounded staging/output
validation, fixed OCI preparation and offline image recipe checks pass393 scoped
cases with unchanged source/preserved prior artifacts. See [contract](../C23_SANDBOX_CONTRACT.md),
[handoff](../handoffs/C23.md) and [checkpoint](../evidence/C23/checkpoint.json).
No production dispatch path or real runtime was built/activated. This checkpoint
does not satisfy actual containment, durable runtime integration, safe extraction
or numerical acceptance; C23 is not Complete. The user confirmed no host exists
and real execution must remain gated. Scheduled continuation remains paused.

## Hosted preparation and GCP authorization — 2026-10-23 JST

Exact source `b8e929e` passes [hosted CI39578854643](https://github.com/jarondlk/ocean-platform/actions/runs/39578854643):
5556 backend/275 gated skips/86.94% coverage,275 actual PostgreSQL cases,
930 v1/132 legacy tests and all four required jobs. All17 preparation source
paths match the accepted commit. [New hosted receipt](../evidence/C23/hosted-preparation.json)
preserves the original pending receipt. This verifies local preparation software,
not actual gVisor behavior. New GCP authorization is recorded separately in
[the decision](../evidence/C23/gcp-authorization-2026-10-23/decision.json).
C23 remained In progress at that historical checkpoint.

## Worker preparation and manual resume — 2026-10-25 JST

The isolated project `ocean-v1-c23-20261024` and one `e2-standard-4` worker in
`asia-northeast1-a` were created on2026-10-24. No service account is attached;
SSH uses IAP/OS Login. gVisor `release-20261019.0` and all eight binaries are
pinned; Python3.12.15 and22 hash-locked scientific packages were built offline
and verified. The initial image is retained separately from the quota amendment
being prepared. [Worker plan and actual record](../C23_GCP_TEST_WORKER_PLAN.md).

The durable journal passes97 focused cases plus an independent four-case review.
These results do not verify Linux containment. The real adapter/harness and
trusted-init quota amendment are still being completed. Original receipts are
immutable. C22 production dispatch/reservation-release guards remain closed;
synthetic operator fixtures cannot count as real C22 approval consumption.
The two-hour worker deadline elapsed during interruption; current cloud state
must be read back after the browser login opened on2026-10-25 completes.

## Actual operator checkpoint — 2026-10-27 JST

The source07 synthetic scientific diagnostic, two unchanged NumPy-first
numerical programs and Matplotlib raster program pass on the isolated worker.
Repeated mean/t-test/OLS values agree at1e-12 absolute/relative tolerance;
Parquet preserves int64 maximum. The only resource-policy amendment is the
native Sentry/gofer descriptor cap256→4096; the guest remains256. Stable pinned
Sentry/gofer identities and limits are read before start, with bounded explicitly
classified auxiliary processes. Unknown identities still fail closed. Original
failed attempts/receipts and image/init bytes remain immutable.

Namespace, containment, whole-tree cleanup, CPU/memory/time/output/scratch/log
and unsafe-output observations are retained under their exact source profiles.
The original process-exhaustion case failed with Sentry clone panic; a separate
qualified host PID-bound observation does not relabel it a successful guest.
Three process-crash/replay episodes pass; VM reboot, queued cancellation and
retained owner revocation are not thereby established. Read-only C22 inspection
and strict termination packet validation are preparation, not reservation or
physical issuer authority. New PostgreSQL persistence/roles are still a draft.
The actual retained synthetic C22 approval→reserve→Linux run→signed termination
proof→verified release path remains required before Complete. Scientific
correctness, production dispatch and whole-site C24 deployment are not claimed.
See [latest handoff](../handoffs/C23.md) and
[local receipt](../evidence/C23/operator-local-20261027-native02/verification.json).
