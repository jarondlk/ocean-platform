# C26 local actual-service browser acceptance

These are synthetic loopback observations through the actual frontend and
C17/C20/C21/C22/C25 APIs, with a separate local queue delivery loop. No live
model, real Python execution, GCP, real transfer or beta deployment ran.

`browser-observations.json` has the four required local browser check IDs. The
catalogue, experiments, and keyboard/DOM accessibility checks pass. The research
check currently fails: new mixed native/experimental context runs complete, but
answer/evidence hydration shows an unverified notice. This is an acceptance gate,
not a release success.

The final `accepted-http.json.gz` contains 397 actual HTTP request records and
204 serving/frontend/harness source pins. All expanded source pins matched after
the API stopped. The `source_revision` identity is the 16-file fixture identity
defined by `tests.system_acceptance_support.source_revision`; the expanded pins
are independently available and must not be substituted into that identity.

The failure was initially suspected to be an answer-list contract rejection.
`browser-observations-initial-hypothesis.json` retains that initial hypothesis.
The complete request trace shows answer-list responses complete under 0.9s,
then mixed-context evidence-list responses take 13.66–15.79s. The actual history
scheduler allows 15s for the whole hydration. Separate exact-response diagnostics
pass the actual frontend schema/client and complete history hydration; no schema,
validation or deadline was relaxed. The owning performance diagnosis is retained
separately. Raw failures and original captures are unchanged.

The `accepted-*` DOM files and screenshots belong to the final C14 source
`9b29032a9dd604bf7694cf7373f79bf71a967bed4634bb0f4f1f12f64aacec2a`.
Earlier screenshots/DOM files and `pre-optimization-http.json.gz` document the
pre-optimization exploration. `preliminary-synchronous-worker-http.json.gz`
belongs to an initial harness that incorrectly waited for worker delivery before
returning the submit response; it does not establish a product defect or pass.

Manual browser verification covered read-only search/inspection/selection,
explicit pin/unpin and native/experimental attachments, separate conversations,
actual research submit/reopen, retained evidence/experimental labels and exact
int64 output display, deep-link Back/Forward/reload, English/Japanese themes,
390px responsive layout, keyboard tab selection, modal Escape/focus return,
other-account denial and suspended-account clearing. Actual assistive-technology
user validation remains separate; DOM semantics and keyboard behavior are the
scope of this local check.

Harness commands:

```sh
DEPLOYMENT_ENV=test AUTH_MODE=disabled .venv/bin/python docs/plans/ocean-v1/evidence/C26/serve_acceptance_qa.py --state-file /private/tmp/ocean-c26-browser-control-20261029.json --observations /private/tmp/ocean-c26-browser-http-accepted-20261029.json
NEXT_TELEMETRY_DISABLED=1 node frontend-v1/node_modules/next/dist/bin/next dev frontend-v1/development/c26 --hostname 127.0.0.1 --port 3100
node frontend-v1/node_modules/typescript/bin/tsc --noEmit -p frontend-v1/development/c26/tsconfig.json
```

The owned API/frontend processes exited successfully, the test tab was closed,
the temporary viewport override was reset, and ports 3100/3101 had no listener.
See `cleanup.json`. Unrelated user tabs were not used.
