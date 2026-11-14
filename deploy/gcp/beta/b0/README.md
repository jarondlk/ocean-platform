# B0 read-only observer recovery and guard

The reviewed observer source was recovered from the existing job
`ocean-v1-beta-provider-preflight-20261111`, generation 1, through a read-only
Cloud Run metadata call. `observer.source` is exactly 12,094 bytes with SHA256
`a094ff42319fb4428fd0955ab8abfaf6ea94dd5b9d976198ef50f85af20a9e33`, matching
the original preflight and retained-helper receipts. `observer-entry.source`
retains the exact 402-byte hash-checking entry wrapper. They are verbatim source
recovery artifacts, not newly formatted or automatically executable entrypoints.
Their historical formatting is preserved without altering their byte identities.

`observer-contract.json` pins the reviewed job identity, generation, configuration,
network, numeric secret references, resource bounds, source/wrapper hashes and
images. This reconstructs the B0 boundary; it does not recover or silently replace
all 15 missing private deployment helpers. Later B1 staging/promotion tooling must
be reconstructed/reviewed separately or transferred against its original hashes.

The versioned verifier is
[scripts/beta_b0_preflight.py](../../../../scripts/beta_b0_preflight.py).
It reads supplied metadata and cannot call a cloud API, execute a job, change
service settings, resume a queue or admit a model question. Its exact proxy
exception verifies both immutable raw OCI hashes and the reviewed Linux/amd64
descriptor; all other execution settings must remain equal to the job contract.
Reports must contain only the exact aggregate keys and consistent integer counts.
It rejects failed/retried executions and reports older than 180 seconds. The result
always retains `rollout_cleared=false`: budget, service/IAM/control and admission
checks are separate prerequisites, and a snapshot is not an admission fence.

From the repository root, inspect a fresh job readback without executing it:

```sh
.venv/bin/python scripts/beta_b0_preflight.py --job "$PRIVATE_JOB_READBACK"
.venv/bin/python -m pytest -q tests/test_beta_b0_preflight.py
.venv/bin/ruff check scripts/beta_b0_preflight.py tests/test_beta_b0_preflight.py
```

For a newly authorized, budgeted observer run, first verify current serving
admission drain and the full old-request envelope, paused/empty queue, absent
runtime sweep, current IAM/secret metadata and catalogue authority. Inspect
uncertain outcomes before retrying. Record that run's real lower time bound,
then read the exact successful execution and its single aggregate log report:

```sh
.venv/bin/python scripts/beta_b0_preflight.py \
  --job "$PRIVATE_JOB_READBACK" \
  --execution "$PRIVATE_EXECUTION_READBACK" \
  --execution-name "$CURRENT_OBSERVER_EXECUTION" \
  --report "$PRIVATE_AGGREGATE_REPORT" \
  --not-before "$CURRENT_POST_DRAIN_BOUND_UTC"
```

These variables refer to newly inspected private files and the current run;
they are not saved arguments to replay. Do not change the verifier's clock to
accept an expired capture. The November14 successful observation remains dated
evidence, not persistent permission to roll out a later controller/runtime.

Use the dedicated beta CLI wrapper for its granted read/build/serving-update
scopes. Executing the existing observer requires the separately authorized
operator job-execution capability; no automation-identity role expansion is
included. The unchanged observer uses read-only SQL and mandatory proxy shutdown.
No original bootstrap, migration, enrollment, grant or import job is involved.
