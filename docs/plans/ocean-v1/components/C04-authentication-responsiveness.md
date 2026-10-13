# C04 — Authentication responsiveness

**Status:** Not started. **Prerequisites:** None. **Contract:** nonblocking authorization boundary.

## Objective and boundaries

Fix audit F03 so synchronous authentication and shared rate limiting do not block the asynchronous server event loop. Preserve permission decisions, request attribution and fail-closed behavior while other requests remain responsive during identity-store delays.

Included: moving complete session-owning work off the event loop, existing rate-limit decisions and deterministic concurrency checks. Excluded: changing identity providers, roles, invitation rules, rate quotas, introducing a new database driver or redesigning authentication. This is a serving repair, not permission expansion.

## Existing entry points

Verified sources: [authentication middleware](../../../../api/auth.py), [rate limiting](../../../../api/rate_limit.py) and [database sessions](../../../../db/connection.py). Existing suites include `tests/test_auth.py`, `tests/test_api_security.py` and `tests/test_rate_limit.py`. `authorization_middleware` currently calls `authenticate_request` and the production limiter synchronously before awaiting the downstream application.

## Interface decisions

Use the application's supported thread-offload mechanism for each complete synchronous session/connection-owning operation. Open, consume and close database sessions in the worker; do not move a live session or lazy ORM object across threads. Return immutable identity/decision data, then assign request state on the event loop. Maintain existing 401/403/429/503 outcomes, security headers, `Retry-After`, route default-denial and liveness exemptions. Cancellation must not leak connections or leave mutable cross-request user state. Keep shared limiter atomicity and storage failures fail-closed.

## Resumable checkpoints and acceptance

1. **Controlled reproduction:** add a blocking identity stub and an independent event-loop heartbeat, plus the equivalent limiter case. Acceptance: reproduce the current blockage without a live identity provider, paid calls or unreliable narrow timing assertions.
2. **Offload boundary:** relocate blocking work with complete session lifetimes. Acceptance: delayed authentication/limiting allows unrelated requests and heartbeat progress, with no cross-thread session reuse.
3. **Security parity:** verify parallel users, rejected tokens, revoked users, limiter failures, cancellation and errors. Acceptance: prior status codes and attribution survive; every opened session closes and unauthorized requests never reach protected handlers.

Implementation command: `python -m pytest tests/test_auth.py tests/test_api_security.py tests/test_rate_limit.py`. Extend these suites with event-driven concurrency tests. Run PostgreSQL limiter integration only against an already configured disposable test database when the shared limiter code changes; record gated skips. No throughput claim or production responsiveness measurement is implied by these local tests.

## Compatibility, rollback and handoff

Keep public APIs, identity objects and provider configuration compatible. No migration is expected. Rollback can restore the prior deployment for service availability but must clearly retain F03 as unresolved; do not claim the old path responsive. Record offload/session boundaries, security parity checks and measured synthetic behavior in `handoffs/C04.md`; update `STATUS.md` per checkpoint. Completion requires both concurrency and authorization acceptance.

## Exact prompts

**Planning-only**
> Review C04 without implementing. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C04-authentication-responsiveness.md and relevant handoffs; no prerequisites apply. Inspect current middleware and checkout, then report planning refinements only. Do not edit application code or begin implementation without an explicit implementation request.

**Implementation**
> Implement only C04 after reading the planning README, MASTER_PLAN, DECISIONS, STATUS, this C04 specification and relevant handoffs under docs/plans/ocean-v1. There are no prerequisites. Verify the checkout and preserve unrelated work. Complete the checkpoints, updating STATUS.md and handoffs/C04.md after each. Run required tests before completion. Do not change role policy, start another component, publish, make cloud writes, provision, deploy or run paid model evaluation.

**Resume**
> Resume C04 only. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C04-authentication-responsiveness.md and handoffs/C04.md; C04 has no prerequisites. Reconcile checkpoint evidence with the checkout, then continue the next unfinished step. Preserve unrelated work, record tests and update status/handoff at checkpoints. Do not start another component, change role policy, publish, make cloud writes, provision, deploy or run paid model evaluation.
