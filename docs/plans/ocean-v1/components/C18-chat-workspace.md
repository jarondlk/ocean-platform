# C18 — Chat and Workspace interface

Status: **Not started**. Prerequisites: **C15, C16, C17**.

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

## Resumable checkpoints

1. **Implement investigation navigation.** Connect lists, naming, conversations and restoration to C17. Acceptance: reload and Back/Forward restore the selected conversation; private investigations never leak across account changes.
2. **Implement explicit context control.** Integrate catalogue selection, attach/pin/unpin and refresh. Acceptance: ordinary browsing never mutates context; cross-chat changes are visible; revisions remain stable for submitted activity fixtures and refresh preserves prior evidence.
3. **Build result and activity presentation.** Acceptance: empty/error/partial/running states are distinguishable, citations can open retained evidence, source authority remains visible, and mobile/keyboard/localized layouts preserve essential actions. Runtime and experiment actions remain unavailable until their owning components integrate them.

## Validation, compatibility and handoff

Existing commands: `npm --prefix frontend run typecheck`, `npm --prefix frontend test`, and `npm --prefix frontend run build`. Planned new interaction tests cover explicit attachment, restrictions, multi-chat updates, refresh branches, account changes and navigation restoration. Use deterministic fixtures for unavailable later services; document manual keyboard and narrow-screen checks.

Keep legacy `/chat` accessible behind the rollout choice. Rollback changes navigation without deleting investigations. Record UI/API contracts, completed versus deferred integrations and verification evidence in `handoffs/C18.md`; update `STATUS.md` per checkpoint.

## Copy-and-paste prompts

**Planning-only**

> Review C18 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this specification, mockups and C15/C16/C17 handoffs. Reconcile with the actual checkout. Refine the plan; do not implement application changes.

**Implementation**

> Implement explicitly requested component C18 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this specification and C15/C16/C17 handoffs; verify prerequisites in the actual checkout. Complete its checkpoints and checks, preserving unrelated changes. Update STATUS.md and handoffs/C18.md throughout. Do not start another component, make cloud writes or paid calls, or publish production data.

**Resume**

> Resume C18 only. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this specification, prerequisite handoffs and handoffs/C18.md. Reconcile progress with the actual checkout and evidence. Continue the first unfinished checkpoint; update STATUS.md and handoffs/C18.md. Do not repeat completed work, start another component, make cloud writes or paid calls, or publish production data.
