# C26 local browser verification on the final repair source

All four functional browser checks pass in `browser-observations.json`. The
capture uses the actual C17/C20/C21/C22/C25 services and frontend with explicit
synthetic TEST identities, deterministic catalogue research, a local queue
adapter and template answers. It does not establish release acceptance.

The source identity is
`sha256:79059c699828bb4e15767eef13e735370ed3ebe32e6f488bbe3e846186ce976f`.
This is the original 16-file fixture source identity; 204 expanded
serving/frontend/harness pins are also recorded and matched after shutdown.
`actual-http.json.gz` retains all 707 actual request records and the exact
startup/final source maps. No HTTP 500/503 response occurred in this capture.

The main journey explicitly attached native C21 evidence first, attached a
validated C25 result second, submitted a new run, and prepared a new answer for
that run. The actual UI rendered a completed answer with datasets **4**, a
retained current binding, one tool action and zero model calls. It distinguished
the earlier receipt as supplementary and retained the experimental result's
absence of independent scientific verification. The same answer reopened after
a fresh page reload. The exact int64 value `9223372036854775807` remained visible
in the experimental output preview; real execution remained unavailable.

The concurrent-read performance finding remains **open**. During active answer
preparation, one automatic history hydration exceeded the unchanged 15-second
whole-history deadline and showed an unverified notice. The underlying requests
returned HTTP 200; two concurrent evidence-list reads took 14.14/14.68 seconds
before including answer-list/event work. Explicit **Reload answers and evidence**
recovered, and stable prepared-answer/page-reload reads succeeded. The functional
check includes that bounded recovery; it does not claim zero notices or accept
production latency. The parent acceptance review must retain this finding.

Other checks covered read-only catalogue search/inspection/selection, explicit
pin/unpin, shared context with independent conversations, snapshot/node/section
Back/Forward/reload, English/Japanese presentation, 390px dark layout with no
document overflow, keyboard inspector-tab selection, modal Escape/focus return,
other-account denial and suspended-account clearing. Actual assistive-technology
user validation remains unrun; this evidence covers keyboard and DOM semantics.

The earlier Oct29 failure capture and Oct30 intermediate activity-race capture
remain unchanged. This new source includes the exact current provider closing
guards and the bounded C21 event-prefix query. No client deadline or contract
validation was relaxed. Hosted CI/source delivery for these source changes is a
separate parent checkpoint; this local receipt does not claim it has occurred.

The accepted C26 harness was unchanged. Commands:

```sh
DEPLOYMENT_ENV=test AUTH_MODE=disabled .venv/bin/python docs/plans/ocean-v1/evidence/C26/serve_acceptance_qa.py --state-file /private/tmp/ocean-c26-browser-control-final-20261030.json --observations /private/tmp/ocean-c26-browser-http-final-20261030.json
NEXT_TELEMETRY_DISABLED=1 node frontend-v1/node_modules/next/dist/bin/next dev frontend-v1/development/c26 --hostname 127.0.0.1 --port 3100
```

The owned API and frontend exited successfully, the test tab closed, the viewport
override reset, and ports 3100/3101 had no listener. No GCP, live model, real
Python execution, real data transfer or deployment ran.
