# C17 — Investigation persistence

Status: **Not started**. Prerequisites: **C03, C04, C08, C09**.

## Objective and boundaries

Persist private named investigations containing multiple conversations, selected context and immutable scope revisions. Allow later work to resume reliably without confusing historical evidence with new data or another chat's narrative.

Include additive application tables, authenticated investigation/conversation/context APIs, snapshot bindings, explicit refresh branches and retention integration. Exclude the agent controller, queues, experiment execution, collaborative sharing, UI construction and destructive migration of historical interactions.

Verified entry points: [application models](../../../../db/app_models.py), [chat persistence](../../../../api/chat_records.py), [retention](../../../../db/retention.py), [authentication](../../../../api/auth.py), and [migrations](../../../../migrations/versions). Keep new user-owned records in the application metadata lifecycle, separate from replaceable scientific corpus tables.

## Interfaces and decisions

Expose `/research/investigations/*` for investigation metadata, conversations, attachments, pins and refresh branches. Record owner, snapshot identity and append-only context revisions with stable references to catalogue objects and retained artifacts. Enforce ownership and current permissions on every read and write, including historical references.

Attaching context makes it available for use; it does not exclude other eligible data. Pins are explicit restrictions. Sharing an investigation context across its conversations does not share transcripts as evidence. Generated narrative from another conversation is never implicitly attached. Record who changed context and return its revision for later runs to freeze at submission.

Refresh creates an updated branch linked to its predecessor. Preserve original snapshot/evidence; revalidate selections and pins against the new snapshot and expose unresolved references before running. Later withdrawal overrides historical availability without erasing the provenance record. Continuing a legacy interaction creates a linked investigation while leaving old interaction records intact.

## Resumable checkpoints

1. **Add persistence and migrations.** Define investigation, conversation and context revision storage. Acceptance: clean and existing disposable databases migrate; concurrent changes cannot silently overwrite revisions; corpus replacement cannot delete investigations.
2. **Implement ownership and context operations.** Acceptance: attachments and pins remain distinct; cross-user reads/writes fail; role revocation affects historical access; submitted revision identities remain immutable.
3. **Implement refresh and retention behavior.** Acceptance: branches preserve original evidence, unresolved selections are explicit, legal holds protect retained records, and legacy continuation preserves historical links without rewriting content.

## Validation, compatibility and handoff

Existing regression command: `python -m pytest tests/test_retention.py tests/test_auth.py tests/test_chat_source_scope.py tests/test_chat_feedback.py`. Planned new tests cover concurrent revisions, ownership, branch refresh and legacy links. Migration/integration checks must use an explicitly configured disposable local database; this component does not authorize production migrations.

Additive migrations preserve legacy `/chat`, history, citations and feedback. Rollback disables investigation endpoints while keeping tables and references intact; destructive downgrade is not the rollout rollback. Record schema/API contracts, migration evidence, retention rules and unresolved-reference behavior in `handoffs/C17.md`; update `STATUS.md` per checkpoint.

## Copy-and-paste prompts

**Planning-only**

> Review C17 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this specification and C03/C04/C08/C09 handoffs. Reconcile with the actual checkout. Refine the plan; do not implement application changes.

**Implementation**

> Implement explicitly requested component C17 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this specification and C03/C04/C08/C09 handoffs; verify prerequisites in the actual checkout. Complete its checkpoints and checks, preserving unrelated changes. Update STATUS.md and handoffs/C17.md throughout. Do not start another component, make cloud writes or paid calls, or publish production data.

**Resume**

> Resume C17 only. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this specification, prerequisite handoffs and handoffs/C17.md. Reconcile progress with the actual checkout and evidence. Continue the first unfinished checkpoint; update STATUS.md and handoffs/C17.md. Do not repeat completed work, start another component, make cloud writes or paid calls, or publish production data.
