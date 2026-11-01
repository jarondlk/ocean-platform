# Smoke diagnostic amendment — 2026-11-02 JST

The root operator reported that Cloud Build
`07cd8231-b72e-4e2b-8cde-b56118563233` passed both default image-user checks,
the API import and unconfigured API startup refusal, then failed the frontend
HTTP probe. Its log retained only the summary and its failed step did not upload
the full result artifact. That partial evidence does not identify the observed
frontend failure. The original preparation record and source commit `74f2262`
remain historical; no pass or root cause is added to them.

Reading the harness identified an independently reproducible defect:
`assert.match` was called with a string as its second argument. Node requires
a regular expression. That call would throw after a successful login response.
The harness now uses `/Sign in to OCEAN/`. This is a confirmed harness defect,
not a claim that the missing first-run diagnostic showed that exception or that
the application passed all remaining checks.

The summary now includes the actual error and cleanup error. If a frontend
container was allocated, failure captures only that UUID-owned container's
last80 server log lines and state before cleanup. Each diagnostic command has
a5-second deadline and bounded captured tails. All configured values remain
synthetic and the container still has no network. No credentials, environment
dump, other container or deployment is inspected. Cleanup records command
availability failures instead of abandoning the result file. The root wrapper
must independently print/copy that file on a failed Cloud Build step because
successful-build artifact upload cannot preserve a failed step's result.

Changed Python and embedded probe syntax, Ruff and the corrected Node assertion
API were checked locally. No image, application source, full test suite, native
database or cloud operation was changed or repeated by this amendment. A new
bounded actual-container run is still required. `diagnostic-amendment.json`
records the intentional harness source supersession and unchanged original
preparation identity.
