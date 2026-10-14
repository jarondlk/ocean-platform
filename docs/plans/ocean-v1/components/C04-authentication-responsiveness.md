# C04 — Authentication responsiveness

**Status:** Not started. **Prerequisites:** P00. **Contract:** nonblocking authorization boundary.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

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

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c04). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.
