# C20 — Durable research execution

**Status:** Complete; original checkpoints, final history repair and source-bound hosted delivery verified. **Prerequisites:** C04, C17, C19.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Make investigations survive browser reloads, process interruption and repeated queue delivery without losing observations or duplicating completed steps. This component implements application-side durability and dispatch contracts, not cloud provisioning or experimental workers.

Include research run APIs, persisted events, transactional outbox, leases, idempotent execution, continuation and cancellation. Exclude changing scientific query behavior, final synthesis (C21), experiments and live Cloud Tasks/Cloud Run resources.

## Verified entry points and contracts

The implementation's [durable execution contract](../C20_DURABLE_EXECUTION_CONTRACT.md)
records the public wire, transaction, lease, replay, budget and rollback invariants.

Inspect [chat records](../../../../api/chat_records.py), [application models](../../../../db/app_models.py), [authentication](../../../../api/auth.py), [API entry point](../../../../api/main.py) and [migrations](../../../../migrations/versions/). Legacy chat lifecycle records are references for persistence conventions, not the new run state model.

Expose creation and cursor-based status/events under `/research/runs/*`, with clarification, continuation and cancellation actions. Use queued, running, awaiting clarification, awaiting approval, completed, partial, cancelled and failed states. Every action/read rechecks ownership and current permissions. Runs retain their C17 context revision and snapshot; refresh is a new branch, not mutation of an active run.

Use a private Cloud Run controller behind Cloud Tasks. Commit outbox events with state changes; queue delivery is at least once. Run leases and stable step IDs prevent repeated committed effects. Checkpoint before and after each tool/model operation. A crash may require redoing an uncommitted model request; never present that as exactly-once billing or execution. Persist timing so restart cannot reset the 180-second/12-action budget. Clarification and approval pauses do not consume active execution time.

C20 also owns the concrete frontend transport for submit, status/event polling,
cancel, clarify and continue, replacing C18's development fixture through its
typed boundary. Test it independently if C18 is not yet implemented; consume the
same documented contract and enable it when both capabilities are present.
Production controls remain unavailable until a real transport is configured.
C26 verifies reload, reconnect and all six actions through the assembled Chat UI.

## Independent service and frontend targets

The controller, task queue, outbox, secrets and run state use v1 resources only.
Connect the concrete transport to frontend-v1 using P00's reviewed interaction
states and C18's integration contract. Do not proxy to legacy /chat or use its
credentials as a fallback. Keep fixture execution visibly local; unconfigured
v1 execution reports unavailable. Ownership/session checks use v1 identities.

## Resumable checkpoints

1. Add additive run/event/outbox persistence and owner-scoped APIs using C17 models; document transaction and transition invariants.
2. Add worker dispatch abstraction, leases, step checkpoints and local fake-queue implementation. Retain observations before publishing progress events.
3. Add cancellation, expiry, clarification and linked continuation; exercise retry/crash boundaries, implement the live Chat transport and expose status to C18/C21 without altering legacy enums.

## Future verification and acceptance

Existing regressions: `python -m pytest tests/test_auth.py tests/test_rate_limit.py tests/test_migration_configuration.py -q`. During implementation, add a dedicated durable-run suite and record its invocation; test with local fixtures/fake queue and disposable local PostgreSQL where transactional races require it.

Acceptance requires identical snapshot/context after redelivery, no duplicate committed steps, monotonic event cursors, expired-lease recovery, no budget reset, permission revocation, cancel-versus-complete races and retained partial observations. Browser disconnection must not cancel a run. A cancelled experiment is not treated as stopped until its execution boundary confirms termination. Cloud integration checks remain pending until explicitly authorized.

Current local verification:4847 backend/231 gated skips/85.64%,76 required compatibility;104 actual PostgreSQL (44 C20/60 C17) with zero schemas remaining and owned server stopped;781 v1 frontend tests/typecheck/build/zero-vulnerability audit; nine generated checks/Ruff and independent reviews. The [local receipt](../evidence/C20/verification.json) binds46 owned paths and167 tested source paths. All912 older evidence and protected files are unchanged. Original parity, sandbox/head-assertion and scheduler failures are preserved with explicit tested amendments. The final pagination amendment adds fresh owner-authorized retention for up to25 recent explicit run acknowledgements per conversation;805 frontend tests, full types/build/audit and independent repair review pass. Original backend/PG sources and evidence are unchanged. Amended sourcea149239 is committed/pushed; [exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39209113719) and final delivery pass. The [original fc46da3 run](https://github.com/jarondlk/ocean-platform/actions/runs/39207358123) is historical and cannot accept the repaired source.

## Compatibility, rollback and handoff

Keep migrations additive and preserve legacy `/chat` and history. Disabling dispatch stops new work without deleting runs; checkpoint state enables later resumption. Write `handoffs/C20.md` and [status](../STATUS.md) after each checkpoint with migration IDs, transition behavior, tests and recovery limitations.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c20). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Final hosted delivery

Sourcea149239 is committed/pushed; [exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39209113719) passes: 4838 backend / 231 gated skips / 86.27% coverage, 231 actual PostgreSQL cases, 805 v1 and 132 legacy frontend tests, both typechecks/builds/audits, generated contracts, migrations/idempotence and isolated backup/restore. [Final delivery receipt](../evidence/C20/delivery.json). The original fc46da3 run was superseded/cancelled by the required pagination repair. Its results remain historical; the amended source itself passes all hosted gates. C21 readiness follows the separately committed/pushed delivery record.
