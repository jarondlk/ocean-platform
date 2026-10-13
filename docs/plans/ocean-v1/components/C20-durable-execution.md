# C20 — Durable research execution

**Status:** Not started. **Prerequisites:** C04, C17, C19.

## Objective and boundaries

Make investigations survive browser reloads, process interruption and repeated queue delivery without losing observations or duplicating completed steps. This component implements application-side durability and dispatch contracts, not cloud provisioning or experimental workers.

Include research run APIs, persisted events, transactional outbox, leases, idempotent execution, continuation and cancellation. Exclude changing scientific query behavior, final synthesis (C21), experiments and live Cloud Tasks/Cloud Run resources.

## Verified entry points and contracts

Inspect [chat records](../../../../api/chat_records.py), [application models](../../../../db/app_models.py), [authentication](../../../../api/auth.py), [API entry point](../../../../api/main.py) and [migrations](../../../../migrations/versions/). Legacy chat lifecycle records are references for persistence conventions, not the new run state model.

Expose creation and cursor-based status/events under `/research/runs/*`, with clarification, continuation and cancellation actions. Use queued, running, awaiting clarification, awaiting approval, completed, partial, cancelled and failed states. Every action/read rechecks ownership and current permissions. Runs retain their C17 context revision and snapshot; refresh is a new branch, not mutation of an active run.

Use a private Cloud Run controller behind Cloud Tasks. Commit outbox events with state changes; queue delivery is at least once. Run leases and stable step IDs prevent repeated committed effects. Checkpoint before and after each tool/model operation. A crash may require redoing an uncommitted model request; never present that as exactly-once billing or execution. Persist timing so restart cannot reset the 180-second/12-action budget. Clarification and approval pauses do not consume active execution time.

C20 also owns the concrete frontend transport for submit, status/event polling,
cancel, clarify and continue, replacing C18's development fixture through its
typed boundary. Test it independently if C18 is not yet implemented; consume the
same documented contract and enable it when both capabilities are present.
Production controls remain unavailable until a real transport is configured.
C26 verifies reload, reconnect and all six actions through the assembled Chat UI.

## Resumable checkpoints

1. Add additive run/event/outbox persistence and owner-scoped APIs using C17 models; document transaction and transition invariants.
2. Add worker dispatch abstraction, leases, step checkpoints and local fake-queue implementation. Retain observations before publishing progress events.
3. Add cancellation, expiry, clarification and linked continuation; exercise retry/crash boundaries, implement the live Chat transport and expose status to C18/C21 without altering legacy enums.

## Future verification and acceptance

Existing regressions: `python -m pytest tests/test_auth.py tests/test_rate_limit.py tests/test_migration_configuration.py -q`. During implementation, add a dedicated durable-run suite and record its invocation; test with local fixtures/fake queue and disposable local PostgreSQL where transactional races require it.

Acceptance requires identical snapshot/context after redelivery, no duplicate committed steps, monotonic event cursors, expired-lease recovery, no budget reset, permission revocation, cancel-versus-complete races and retained partial observations. Browser disconnection must not cancel a run. A cancelled experiment is not treated as stopped until its execution boundary confirms termination. Cloud integration checks remain pending until explicitly authorized.

## Compatibility, rollback and handoff

Keep migrations additive and preserve legacy `/chat` and history. Disabling dispatch stops new work without deleting runs; checkpoint state enables later resumption. Write `handoffs/C20.md` and [status](../STATUS.md) after each checkpoint with migration IDs, transition behavior, tests and recovery limitations.

## Copy-and-paste prompts

**Planning only:** “Review only C20 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C20-durable-execution.md, prerequisite handoffs C04/C17/C19 and the current checkout. Refine documentation only; preserve unrelated work and report open decisions.”

**Implementation:** “Implement only C20. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C20-durable-execution.md and prerequisite handoffs C04/C17/C19; reconcile the checkout before editing. Complete checkpoints and local verification, updating STATUS.md and handoffs/C20.md throughout. Preserve unrelated work. Do not advance components, provision cloud resources, deploy or run paid/live evaluations.”

**Resume:** “Resume only C20 from docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C20-durable-execution.md, handoffs/C20.md and prerequisite handoffs C04/C17/C19. Reconcile actual code and test evidence; continue the next unfinished checkpoint and update status/handoff. Preserve unrelated work; no automatic advance, provisioning, deployment or paid/live evaluations.”
