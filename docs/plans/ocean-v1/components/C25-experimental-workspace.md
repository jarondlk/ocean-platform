# C25 — Experimental Workspace interface

**Status:** Not started. **Prerequisites:** P00, C18, C22, C23, C24.

Readiness audited 2026-10-28 JST: **ready to begin the local proposal-review and
approval checkpoint**. All five prerequisite receipts/current source reconcile;
234 focused backend and 930 frontend baseline cases plus typecheck/build pass.
The C22 public contract explicitly reports non-execution and has no cancellation,
execution/result/artifact retrieval API. A bounded C22/C23 public-contract amendment
is required before later checkpoints claim actual service parity; fixture UI
does not satisfy that gate. [Readiness audit](../C25_READINESS_AUDIT_2026-10-28.md),
[handoff](../handoffs/C25.md). C25 implementation has not been selected here.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Let a researcher inspect and approve a concrete experiment, follow execution and reopen reproducible results within the investigation's Experiments tab. The interface must make the difference between proposed, approved, executing and completed work clear, while preserving the scientific qualifications attached to all results.

Include proposal review, hash-bound approval interactions, execution progress, cancellation, artifact inspection and evidence navigation. Exclude changing methods or cohort rules, implementing the executor, provisioning C24 resources, and scientific publication. Use local fixtures if live worker acceptance is pending; never imply the worker is available because infrastructure code exists.

## Verified entry points and contracts

Inspect [analysis interface](../../../../frontend/components/AnalysisWorkbench.tsx), [research result cards](../../../../frontend/components/ResearchResultCards.tsx), [permission gate](../../../../frontend/components/PermissionGate.tsx), [evidence navigator](../../../../frontend/components/EvidenceNavigator.tsx) and [frontend scripts](../../../../frontend/package.json). Reuse OCEAN's accessible tables, preferences and evidence conventions within the C18 layout.

Consume `/research/experiments/*` and C22/C23 versioned contracts. Review displays question, frozen cohort, exclusions, pairing rules, method, assumptions, code, environment, resource limits and expected outputs before approval. Bind the action to the displayed revision/hash; stale approval returns a review-needed state instead of silently approving newer content. Show scope/snapshot and experimental authority on results and downloads.

Expose pending, running, cancelling and terminal execution outcomes from the server; cancellation is not completion until termination is confirmed. Disable approval/execution affordances when permissions, proposal eligibility or worker readiness disallow them, with the concrete reason. Permission gates supplement server enforcement. Preview validated tables/raster plots only; never execute output HTML or notebooks.

## Prototype-to-service integration

Read the P00 handoff and reuse frontend-v1; do not restart the UI from the static
mockup. Keep the accepted UX and iterate on any contract-driven change. P00's
synthetic interactions do not satisfy this component's real-service acceptance.
Use the actual frontend-v1 scripts established in P00 and record runtime/browser
checks against the appropriate v1 services. Existing frontend paths above are
reference implementations, not the target for the new site.

## Resumable checkpoints

1. Add proposal review and revision-aware approval using synthetic API fixtures, including unavailable worker and revoked-permission states.
2. Add durable progress, cancellation, reload/reconnect and concurrent-tab handling; retain current selection in the investigation URL/state without modifying scope.
3. Add result/artifact panels, experimental labels, reproducibility details and evidence attachments. Verify responsive layouts, keyboard use and English/Japanese text.

## Future verification and acceptance

Planned commands, after P00 establishes these scripts: `npm --prefix frontend-v1 test`, `npm --prefix frontend-v1 run typecheck` and `npm --prefix frontend-v1 run build`. Add focused component/contract tests using the existing frontend runner; record their exact invocation in the handoff.

Acceptance covers changed-code approval races, oversized exports, scientific caveats, queued concurrency limits, timeout/failure/cancellation, reload recovery, cross-user access, stale downloads and result attachment. Approval must not execute a different revision; viewing results must not update catalogue classifications. Check the full flow at desktop and narrow widths, keyboard/screen-reader operation and long translated labels. Local fake execution verifies UI behavior; actual cloud execution remains an explicit unrun gate unless separately authorized.

## Compatibility, rollback and handoff

Gate Experiments independently while keeping retained artifacts accessible according to permissions. The legacy published AnalysisWorkbench pages remain on the existing site; v1 published-result views use v1 data and links. Update [status](../STATUS.md) and `handoffs/C25.md` after every checkpoint with UI contract versions, screenshots/check evidence, unresolved live gates and next work.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c25). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.
