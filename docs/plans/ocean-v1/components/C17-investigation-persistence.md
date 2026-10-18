# C17 — Investigation persistence

**Status:** Complete for local acceptance; source checkpoint and exact-source hosted delivery pending. **Prerequisites:** C03, C04, C08, C09.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Persist private named investigations containing multiple conversations, selected context and immutable scope revisions. Allow later work to resume reliably without confusing historical evidence with new data or another chat's narrative.

Include additive application tables, authenticated investigation/conversation/context APIs, snapshot bindings, explicit refresh branches and retention integration. Exclude the agent controller, queues, experiment execution, collaborative sharing, UI construction and destructive migration of historical interactions.

Verified entry points: [application models](../../../../db/app_models.py), [chat persistence](../../../../api/chat_records.py), [retention](../../../../db/retention.py), [authentication](../../../../api/auth.py), and [migrations](../../../../migrations/versions). Keep new user-owned records in the application metadata lifecycle, separate from replaceable scientific corpus tables.

## Interfaces and decisions

Expose `/research/investigations/*` for investigation metadata, conversations, attachments, pins and refresh branches. Record owner, snapshot identity and append-only context revisions with stable references to catalogue objects and retained artifacts. Enforce ownership and current permissions on every read and write, including historical references.

Attaching context makes it available for use; it does not exclude other eligible data. Pins are explicit restrictions. Sharing an investigation context across its conversations does not share transcripts as evidence. Generated narrative from another conversation is never implicitly attached. Record who changed context and return its revision for later runs to freeze at submission.

Refresh creates an updated branch linked to its predecessor. Preserve original snapshot/evidence; revalidate selections and pins against the new snapshot and expose unresolved references before running. Later withdrawal overrides historical availability without erasing the provenance record. V1 starts with independent investigation records. Legacy-history continuation is deferred until a separately approved import/link design exists; no live legacy-history lookup is allowed.

## Resumable checkpoints

1. **Add persistence and migrations.** Define investigation, conversation and context revision storage. Acceptance: clean and existing disposable databases migrate; concurrent changes cannot silently overwrite revisions; corpus replacement cannot delete investigations.
2. **Implement ownership and context operations.** Acceptance: attachments and pins remain distinct; cross-user reads/writes fail; role revocation affects historical access; submitted revision identities remain immutable.
3. **Implement refresh and retention behavior.** Acceptance: branches preserve original evidence, unresolved selections are explicit, legal holds protect retained records, and missing legacy-history import capability is explicit without a production fallback.

## Validation, compatibility and handoff

Existing regression command: `python -m pytest tests/test_retention.py tests/test_auth.py tests/test_chat_source_scope.py tests/test_chat_feedback.py`. Planned new tests cover concurrent revisions, ownership, branch refresh and independent-site storage boundaries. Migration/integration checks must use an explicitly configured disposable local database; this component does not authorize production migrations.

Additive migrations target v1 databases only. Legacy `/chat`, history, citations and feedback remain on the unchanged legacy site. Rollback disables investigation endpoints while keeping tables and references intact; destructive downgrade is not the rollout rollback. Record schema/API contracts, migration evidence, retention rules and unresolved-reference behavior in `handoffs/C17.md`; update `STATUS.md` per checkpoint.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c17). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Accepted implementation — 2026-10-18 JST

All three checkpoints pass local acceptance. The default-off, owner-private
four-table investigation service exposes14 strict POST operations, immutable
context revisions, explicit refresh branches and conservative durable cross-store
prepare/apply/activate recovery. PostgreSQL enforces immutable history and owner/
revision foreign keys; logical retention respects holds without releasing bytes.
[Contract](../C17_INVESTIGATION_CONTRACT.md), [handoff](../handoffs/C17.md),
[accepted19-source map](../evidence/C17/accepted-source.json).

Final backend4187 passed/187 gated PostgreSQL skips/85.08% coverage; source
unchanged during the run. Actual owned disposable PostgreSQL60 cases passed,
zero schemas remained and the server stopped. Two later API/service fixes are
explicit source supersessions; final exact-source hosted CI must run all60 again.
Affected API155, required regression/guard177 and bootstrap38 pass. Previous
failed fixture/sandbox runs remain preserved. No frontend, scientific or legacy
source changed. Conversation execution/history remains C20/C21; Research UI is
C18. Production migrations, real identity, release and cloud gates remain separate.
