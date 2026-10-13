# C03 — Retention integrity

**Status:** Not started. **Prerequisites:** None. **Contract:** transactional hold/deletion ordering.

## Objective and boundaries

Fix audit F01: a hold committed after cleanup selection but before deletion must protect the interaction and dependent evidence. Establish a retention foundation for later catalogue snapshots and research receipts without implementing those new stores here.

Included: cleanup/hold race handling, audit consistency, dry-run behavior and disposable-database concurrency tests. Excluded: changing retention duration, production cleanup, schema for future research records and cloud artifact deletion. Tests may delete only their isolated fixtures.

## Existing entry points

Verified sources are [cleanup](../../../../db/retention.py), [hold endpoint](../../../../api/retention_routes.py), and [cleanup CLI](../../../../scripts/retention_cleanup.py). Existing tests: `tests/test_retention.py`, `tests/test_retention_cleanup_script.py` and PostgreSQL-gated `tests/integration/test_operational_postgres.py`. The present cleanup selects ORM instances then deletes them, allowing a stale hold decision.

## Interface decisions

Keep current endpoint and cleanup report shapes. Recheck the complete eligibility predicate atomically at deletion, including cutoff, terminal status and `legal_hold = false`; coordinate the hold update on the same row so successful hold/deletion operations have a definite transaction order. A hold committed first protects the record. If deletion commits first, a subsequent hold request reports not found and cannot report success. Count actual deleted parents, keep dependent deletion transactional, and audit only committed operations. Dry-run is an observation, not a reservation guaranteeing a later deletion count.

## Resumable checkpoints and acceptance

1. **Race fixture:** build deterministic barriers around selection, hold commit and deletion using two sessions. Acceptance: reproduce stale selection without timing-only assertions; cover both transaction orders.
2. **Atomic behavior:** repair cleanup and hold coordination, dependent evidence handling and audit records. Acceptance: hold-before-deletion survives, deletion-before-hold returns not found, repeated cleanup is safe, and failed transactions leave no misleading success audit.
3. **Database parity:** verify dry-run, cutoff/status protections and concurrent cleanup workers. Acceptance: actual PostgreSQL behavior matches the contract and counts reflect rows truly removed. Keep unrelated users' fixtures isolated.

Implementation validation: `python -m pytest tests/test_retention.py tests/test_retention_cleanup_script.py`. Add proposed `tests/integration/test_retention_concurrency_postgres.py`; run using `RUN_POSTGRES_INTEGRATION=1 python -m pytest tests/integration/test_retention_concurrency_postgres.py` only with a verified disposable local test database configured. A skipped integration test does not establish race safety. Never reuse a production database URL or run retained audit deletion probes blindly.

## Compatibility, rollback and handoff

Avoid destructive migrations. Preserve existing holds, retention configuration and history access. If reverting code, disable destructive cleanup until a safe implementation is restored; do not revert to known stale deletion. The handoff records concurrency ordering, database identity proof without credentials, tests/results and any pending integration check in `handoffs/C03.md`. Update `STATUS.md` at each checkpoint; do not claim complete while PostgreSQL acceptance remains unverified.

## Exact prompts

**Planning-only**
> Review C03 without implementing. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C03-retention-integrity.md and relevant handoffs; C03 has no prerequisites. Inspect the checkout and describe refinements only. Do not edit application code, delete retained records or begin implementation without an explicit implementation request.

**Implementation**
> Implement only C03. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this C03 specification and relevant handoffs under docs/plans/ocean-v1; no prerequisites apply. Verify the checkout and disposable test targets; preserve unrelated work. Follow checkpoints and update STATUS.md and handoffs/C03.md after each. Run required checks before completion. Do not perform real cleanup, start another component, publish, make cloud writes, provision, deploy or run paid model evaluation.

**Resume**
> Resume C03 only. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C03-retention-integrity.md and handoffs/C03.md; no prerequisites apply. Reconcile current code and actual test evidence, then continue the next checkpoint. Preserve unrelated work, confirm disposable database targets and checkpoint status/handoff. Do not mark skipped race checks complete, perform real cleanup, start another component, publish, provision, deploy, make cloud writes or run paid model evaluation.
