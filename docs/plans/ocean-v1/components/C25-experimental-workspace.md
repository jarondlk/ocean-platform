# C25 — Experimental Workspace interface

**Status:** Not started. **Prerequisites:** C18, C22, C23, C24.

## Objective and boundaries

Let a researcher inspect and approve a concrete experiment, follow execution and reopen reproducible results within the investigation's Experiments tab. The interface must make the difference between proposed, approved, executing and completed work clear, while preserving the scientific qualifications attached to all results.

Include proposal review, hash-bound approval interactions, execution progress, cancellation, artifact inspection and evidence navigation. Exclude changing methods or cohort rules, implementing the executor, provisioning C24 resources, and scientific publication. Use local fixtures if live worker acceptance is pending; never imply the worker is available because infrastructure code exists.

## Verified entry points and contracts

Inspect [analysis interface](../../../../frontend/components/AnalysisWorkbench.tsx), [research result cards](../../../../frontend/components/ResearchResultCards.tsx), [permission gate](../../../../frontend/components/PermissionGate.tsx), [evidence navigator](../../../../frontend/components/EvidenceNavigator.tsx) and [frontend scripts](../../../../frontend/package.json). Reuse OCEAN's accessible tables, preferences and evidence conventions within the C18 layout.

Consume `/research/experiments/*` and C22/C23 versioned contracts. Review displays question, frozen cohort, exclusions, pairing rules, method, assumptions, code, environment, resource limits and expected outputs before approval. Bind the action to the displayed revision/hash; stale approval returns a review-needed state instead of silently approving newer content. Show scope/snapshot and experimental authority on results and downloads.

Expose pending, running, cancelling and terminal execution outcomes from the server; cancellation is not completion until termination is confirmed. Disable approval/execution affordances when permissions, proposal eligibility or worker readiness disallow them, with the concrete reason. Permission gates supplement server enforcement. Preview validated tables/raster plots only; never execute output HTML or notebooks.

## Resumable checkpoints

1. Add proposal review and revision-aware approval using synthetic API fixtures, including unavailable worker and revoked-permission states.
2. Add durable progress, cancellation, reload/reconnect and concurrent-tab handling; retain current selection in the investigation URL/state without modifying scope.
3. Add result/artifact panels, experimental labels, reproducibility details and evidence attachments. Verify responsive layouts, keyboard use and English/Japanese text.

## Future verification and acceptance

Existing commands: `npm --prefix frontend test`, `npm --prefix frontend run typecheck` and `npm --prefix frontend run build`. Add focused component/contract tests using the existing frontend runner; record their exact invocation in the handoff.

Acceptance covers changed-code approval races, oversized exports, scientific caveats, queued concurrency limits, timeout/failure/cancellation, reload recovery, cross-user access, stale downloads and result attachment. Approval must not execute a different revision; viewing results must not update catalogue classifications. Check the full flow at desktop and narrow widths, keyboard/screen-reader operation and long translated labels. Local fake execution verifies UI behavior; actual cloud execution remains an explicit unrun gate unless separately authorized.

## Compatibility, rollback and handoff

Gate Experiments independently while keeping retained artifacts accessible according to permissions. Existing published AnalysisWorkbench pages and deep links remain usable. Update [status](../STATUS.md) and `handoffs/C25.md` after every checkpoint with UI contract versions, screenshots/check evidence, unresolved live gates and next work.

## Copy-and-paste prompts

**Planning only:** “Review only C25 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C25-experimental-workspace.md, prerequisite handoffs C18/C22/C23/C24 and the checkout. Refine docs only; preserve unrelated work.”

**Implementation:** “Implement only C25. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C25-experimental-workspace.md and prerequisite handoffs C18/C22/C23/C24; reconcile the checkout. Follow checkpoints, use local fixture execution and run UI checks, updating STATUS.md and handoffs/C25.md throughout. Preserve unrelated work; no automatic advance, real experiments, provisioning, deployment or paid/live evaluation.”

**Resume:** “Resume only C25 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C25-experimental-workspace.md, handoffs/C25.md and prerequisite handoffs C18/C22/C23/C24. Reconcile checkout/evidence, continue the unfinished checkpoint and update status/handoff. Preserve unrelated work; no automatic advance, real experiments, provisioning, deployment or paid/live evaluation.”
