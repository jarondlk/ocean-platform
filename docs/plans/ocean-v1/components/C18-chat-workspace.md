# C18 — Chat and Workspace interface

**Status:** Ready for review; all3 local checkpoints pass; source checkpoint and exact-source hosted delivery pending. **Prerequisites:** P00, C15, C16, C17.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Make a persistent investigation the research home: a conversation alongside Workspace, with multiple separate chats and explicit shared context. Researchers must see what data and restrictions will govern a run before submitting it.

Include investigation/conversation selection, context attachments and pins, snapshot refresh branches, Workspace tabs and presentation contracts for later run activity and artifacts. Exclude implementing agent intelligence, durable execution, evidence synthesis or experiment approval. Later components supply those working integrations; fixtures must be visibly identified during development.

Verified entry points: [Chat page](../../../../frontend/app/chat/page.tsx), [Chat settings](../../../../frontend/components/ChatSourceSettings.tsx), [evidence workbench](../../../../frontend/components/EvidenceWorkbench.tsx), [answer rendering](../../../../frontend/components/MarkdownAnswer.tsx), and [citation navigation](../../../../frontend/lib/citation-navigation.ts). Preserve working citation and legacy-history behavior while introducing investigation navigation.

## Interfaces and decisions

Research opens a list of named private investigations. Desktop uses investigation/conversation navigation, Chat and a resizable Workspace. Workspace tabs are Context, Results, Experiments and Evidence. Executed activity belongs in an expandable Chat history, including elapsed time and cancellation affordances; do not display private model reasoning.

Use C17 APIs for persistent state and the C16 browser for context selection. An explicit Attach action supplements available context; Pin constraint restricts scope. Opening a node or filtering a catalogue page changes neither. Show attachments, pinned restrictions, current snapshot and context revision near the composer. Changes from another chat are visible and affect subsequent submissions only; active runs retain the submitted revision.

Refresh explicitly creates a branch and surfaces unresolved selections before use. Chats share investigation context, not narrative evidence; reusing a retained result requires attachment. Distinguish published analysis, descriptive query and experiment artifacts. On narrow screens Chat and Workspace become tabs with scope and pending actions still accessible.

Define a typed run transport boundary for submit, status/event polling, cancel,
clarify and continue; wire the Chat controls to it using a development fixture.
C20 owns the production transport and activation against its durable API.
Fixtures must never answer real user requests in a production route. This
contract allows either component to be developed first; C26 verifies the assembled
interaction, and C21 supplies final answers and retained-evidence navigation.

## Prototype-to-service integration

Read the P00 handoff and reuse frontend-v1; do not restart the UI from the static
mockup. Keep the accepted UX and iterate on any contract-driven change. P00's
synthetic interactions do not satisfy this component's real-service acceptance.
Use the actual frontend-v1 scripts established in P00 and record runtime/browser
checks against the appropriate v1 services. Existing frontend paths above are
reference implementations, not the target for the new site.

## Resumable checkpoints

1. **Implement investigation navigation.** Connect lists, naming, conversations and restoration to C17. Acceptance: reload and Back/Forward restore the selected conversation; private investigations never leak across account changes.
2. **Implement explicit context control.** Integrate catalogue selection, attach/pin/unpin and refresh. Acceptance: ordinary browsing never mutates context; cross-chat changes are visible; revisions remain stable for submitted activity fixtures and refresh preserves prior evidence.
3. **Build result and activity presentation.** Acceptance: empty/error/partial/running states are distinguishable, citations can open retained evidence, source authority remains visible, and mobile/keyboard/localized layouts preserve essential actions. Runtime and experiment actions remain unavailable until their owning components integrate them.

## Validation, compatibility and handoff

Planned commands, after P00 establishes these scripts: `npm --prefix frontend-v1 run typecheck`, `npm --prefix frontend-v1 test`, and `npm --prefix frontend-v1 run build`. Planned new interaction tests cover explicit attachment, restrictions, multi-chat updates, refresh branches, account changes and navigation restoration. Use deterministic fixtures for unavailable later services; document manual keyboard and narrow-screen checks.

Legacy `/chat` remains on the existing site. V1 rollback changes only v1 navigation without deleting investigations or changing legacy traffic. Record UI/API contracts, completed versus deferred integrations and verification evidence in `handoffs/C18.md`; update `STATUS.md` per checkpoint.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c18). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Local acceptance — 2026-10-18 JST

Actual C17 metadata/context UI and C16 selection pass browser acceptance; all14
client methods are exercised through28 actual ASGI requests. Typed development
activity covers all6 controls while production execution stays unavailable.
673 frontend tests, both production checks and separate development strict
TypeScript pass. Full backend4214/187 gated skips/85.08% covers final backend
source. Independent reviews/fixes and browser qualifications are preserved.
[Contract](../C18_CHAT_WORKSPACE_CONTRACT.md), [handoff](../handoffs/C18.md),
[local verification](../evidence/C18/verification.json). Hosted CI is pending.
