# C04 readiness audit

Audited: 2026-10-14 JST. Branch: `overhaul`.
Local HEAD and freshly queried remote overhaul HEAD:
`516b08675460b7de7b02ecafeec0e2f359d38747`.

**Verdict: ready to begin C04 locally. No new blocking defect was found in the
completed foundation work.** C04's only formal dependency is the accepted P00
prototype, which still matches its receipt. C01/C02 are delivered; C03 is complete
and passes fresh actual PostgreSQL acceptance in this working tree. C03 remains
uncommitted and has no hosted CI result for its changed sources. Save C03 as its
own reviewed delivery checkpoint before combining it with subsequent C04 work.
That delivery checkpoint is separate from C04's implementation dependency.

This request authorized an audit. C04 implementation remains Not started.

## Source and evidence reconciliation

- All 36 accepted P00 source hashes and its accepted screenshot hash match.
- All 23 C01/C02 delivery source paths match. The only change among the delivery
  receipt's 24 paths is the shared CI workflow, whose C03 extension exactly matches
  the newer C03 receipt. Historical C01/C02 receipt differences are explicitly
  accounted for by the delivery audit; they are not unexplained drift.
- All six C03 application/test/workflow hashes and all nine retained evidence-file
  hashes match. C01/C02 delivery evidence hashes also match.
- GitHub reports success for the prior C01/C02 backend, legacy frontend, v1
  prototype and PostgreSQL jobs in [the pre-merge CI run](https://github.com/jarondlk/ocean-platform/actions/runs/38545350664).
  This is historical delivery evidence. The merge-head combined-status endpoint
  returns no legacy statuses; it does not establish a new merge-head Actions run.
- All 857 preexisting repository files in the preservation snapshot are unchanged
  by this audit. All seven inventoried real scientific artifacts retain their
  exact C02 hashes. Planning-document links resolve.

## Fresh checks

| Check | Observed result |
|---|---|
| Full backend suite, Python 3.12.7 | 1,684 passed; 51 expected PostgreSQL-gated skips; 81.37% coverage (minimum 70%) |
| Retention/CLI plus auth/security/rate-limit suites | 101 passed: 35 retention/CLI and 66 C04 baseline cases |
| Actual disposable PostgreSQL 18.3 C03 suite | 12 passed, zero skips; observed row-lock ordering and rollback cases |
| Accepted v1 prototype | 27 tests passed; typecheck and static build passed |
| Active Python Ruff; audit replay scripts | Passed |
| Generated chat scope; dependency consistency; diff whitespace | Passed |

The first sandboxed backend attempt had 29 failures and 14 setup errors because
local fixture sockets were denied. It is retained separately, not counted as
success. After permission for local fixture access, the complete suite passed.
The PostgreSQL run likewise required permission for loopback binding.

The newly created database was `ocean_c03_readiness_fc441b152fb0`, role `ocean_c03`,
address `127.0.0.1:61843`, Read Committed. Its identity and owned data directory
were verified before testing. Zero C03 fixture schemas remained afterward; the
server was stopped. The prior C03 test server remains stopped. No existing
application database URL was used.

## C04 target and acceptance gap

Inspection confirms that `authorization_middleware` directly calls synchronous
`authenticate_request` and the production rate limiter. Authentication owns its
session inside `get_session`; PostgreSQL limiting owns a transaction inside
`engine.begin`. `CurrentUser` and rate-limit policy objects are already frozen.
These are suitable complete-operation boundaries for C04's planned offload.

Fresh synthetic smoke probes confirm both blocking operations execute on the
event-loop thread. A 150 ms authentication delay postponed a requested 10 ms
heartbeat to 154.02 ms; the equivalent limiter delay postponed it to 152.89 ms.
These are illustrative observations, not production latency measurements or
acceptance tests with narrow timing thresholds. Existing baseline suites pass
but do not establish concurrent responsiveness or cancellation/session cleanup.

C04 should first add event-driven concurrency acceptance, then offload complete
session/connection lifetimes and verify authorization, attribution, 401/403/429/503,
security headers, Retry-After, fail-closed behavior and cancellation. Preserve
shared limiter atomicity; if its storage code changes, use separately verified
disposable PostgreSQL integration. Its specification remains the acceptance
authority.

Real affected scientific artifact regeneration/review, assembled v1 acceptance,
cloud isolation and release readiness remain later gates; none is a prerequisite
for starting C04. No application implementation, commit, push, merge, deployment,
production cleanup or provider call occurred in this audit.

Exact receipts, replay scripts, logs and preservation evidence:
[audit evidence](evidence/c04-readiness-2026-10-14/verification.json).
