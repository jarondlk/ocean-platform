# Cloud Run create-request amendment — 2026-11-02 JST

The actual beta `validateOnly` request returned HTTP400 with
`job.name must be empty on CreateJobRequest`. The preceding job GET was404.
Those original responses remain immutable under
`../../jobs-live-20261102/validation-8b06a1b/`. This validation did not create
or execute a job. The failure exposed a renderer request-shape defect; a generic
Job resource containing its name was not an accepted CreateJobRequest body.

The owning renderer now omits the top-level `name`. Its dictionary key and JSON
filename still carry the exact job ID; root must supply that ID in the create
request's `jobId` query parameter. The provider assigns the full resource name.
The [official create method](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs/create)
documents parent plus jobId as the request identity. Actual failure evidence,
rather than the generic Job schema alone, qualifies the omitted field here.

Only that one renderer line is removed. OPERATOR_REVISION remains
`8b06a1b993cbca53ded0a9e79e1acb5ba58f3089`; any later operator-image/source
amendment is separate owning work. The before-source copy and supersession
record preserve the8b renderer. The original50-case setup receipt, synthetic
outputs, original756renderer copy and four-case revision-amendment receipt remain
unchanged. Do not retarget their pins to this later source.

The new regression renders all four stages with clearly synthetic metadata and
checks the external job IDs, absent body name, correct stage and exact equality
of every other policy/configuration field against the preserved renderer. It
also invokes the actual renderer CLI in an owned temporary directory and checks
the four serialized filenames/bodies before deleting only that temporary tree.
No original suite, native cluster, credential generation or cloud request runs.
The accepted local result is4stage checks plus actual CLI serialization; Ruff
checks the new source. `receipt.json` preserves the failure and historical pins.

```sh
.venv/bin/python docs/plans/ocean-v1/beta/sql-20261102/setup/create-request-amendment/verify.py
```

The verifier is read-only. Local regression does not establish provider
acceptance. Root still needs the actual accepted operator digest/source,
completed numeric secret refs and a new reviewed render, followed by actual
validateOnly/create/readbacks. Creating job definitions still must not execute
them. Physical proxy/container exits and all private stage, scientific, C23
and release gates remain unchanged.
