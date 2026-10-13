# C23 — Isolated Python execution

**Status:** Not started. **Prerequisites:** C22.

## Objective and boundaries

Execute an approved, immutable Python analysis envelope with reproducible inputs and bounded outputs, while keeping generated code outside the serving application and production data boundary.

Include sandbox/supervisor interfaces, pinned scientific environment, local synthetic fixtures, output validation, cancellation and containment checks. Exclude provisioning Linux workers, installing host runtimes without authorization, running actual user experiments, production credentials and cloud execution. Infrastructure configuration belongs to C24.

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

## Copy-and-paste prompts

**Planning only:** “Review only C23 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C23-python-sandbox.md, prerequisite handoff C22 and the checkout. Refine docs only; preserve unrelated work.”

**Implementation:** “Implement only C23. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C23-python-sandbox.md and prerequisite handoff C22; reconcile the checkout. Follow checkpoints and local synthetic verification; update STATUS.md and handoffs/C23.md throughout. Preserve unrelated work. Do not advance components, install host services, provision, deploy, run real experiments or paid/live evaluations.”

**Resume:** “Resume only C23 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C23-python-sandbox.md, handoffs/C23.md and prerequisite handoff C22. Reconcile checkout/evidence, continue the next checkpoint and update status/handoff. Preserve unrelated work; no automatic advance, host service installation, provisioning, deployment, real experiments or paid/live evaluations.”
