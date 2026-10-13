# C15 — New application shell

Status: **Not started**. Prerequisites: **C08**.

## Objective and boundaries

Establish the major UI redesign around Research, Context Catalog and Tools. Provide consistent navigation and responsive layout foundations for the later catalogue and investigation experiences while retaining existing specialist workflows.

Include application navigation, permission-aware route groups, reusable split panels, tabs/drawers, typography, themes, localization and empty/loading/error shells. Exclude functional catalogue browsing, investigation persistence, agent execution, experiments and redesigning the internals of every specialist page.

Verified entry points: [application shell](../../../../frontend/components/AppShell.tsx), [navigation](../../../../frontend/components/AppNavigation.tsx), [root layout](../../../../frontend/app/layout.tsx), [global styles](../../../../frontend/app/globals.css), and [preferences](../../../../frontend/lib/preferences.tsx). Review the planning mockups as visual references; illustrative data is not production content.

## Interfaces and decisions

Primary destinations are Research, Context Catalog and Tools. Tools groups existing Data, Explore, Provenance and Evaluation access; Settings and Administration remain permission-controlled. Preserve existing deep links and legacy `/chat` during the transition. New destinations may initially show clear empty states until their owning components are available.

Retain OCEAN branding, restrained ocean-blue accents, light/dark themes and English/Japanese support. Define shared headers, scope/snapshot labels, status treatments and accessible panel controls. Desktop investigation layouts support navigation, conversation and Workspace; the catalogue layout supports tree, listing and inspector. Layout primitives accept content supplied by later components without duplicating domain state.

At narrow widths, panels become tabs or drawers without hiding essential actions. Keyboard controls and visible focus are required for navigation, resizing and dismissal. Route changes must not accidentally reveal hidden destinations or erase future persisted investigation state. Store purely presentational preferences separately from scientific scope.

## Resumable checkpoints

1. **Map navigation and visual primitives.** Add route grouping, design tokens and reusable layout components. Acceptance: all existing permitted destinations remain reachable; restricted links remain absent; legacy deep links still work.
2. **Implement responsive shell.** Build desktop splits and narrow-screen transitions. Acceptance: keyboard operation works, panes remain readable, and Japanese text does not overflow essential controls in either theme.
3. **Verify migration behavior.** Acceptance: feature flag restores the existing navigation; loading/error/empty states are explicit; shared components accept catalogue and research fixtures without embedding fake scientific behavior.

## Validation, compatibility and handoff

Existing commands: `npm --prefix frontend run typecheck`, `npm --prefix frontend test`, and `npm --prefix frontend run build`. New shell interaction tests and manual viewport/accessibility checks are planned during implementation; document viewports, themes and locales tested. Existing automated tests do not by themselves prove keyboard or screen-reader behavior.

Use a feature flag for navigation rollout and preserve legacy routes. Rollback switches the shell without modifying application data. Record component interfaces, navigation mapping, visual references and verification evidence in `handoffs/C15.md`; update `STATUS.md` after each checkpoint.

## Copy-and-paste prompts

**Planning-only**

> Review C15 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this specification, mockups and C08 handoff. Reconcile with the actual checkout. Refine the plan; do not implement application changes.

**Implementation**

> Implement explicitly requested component C15 only. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, this specification, mockups and C08 handoff; verify prerequisites in the actual checkout. Complete its checkpoints and checks, preserving unrelated changes. Update STATUS.md and handoffs/C15.md throughout. Do not start another component, make cloud writes or paid calls, or publish production data.

**Resume**

> Resume C15 only. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this specification, prerequisite handoff and handoffs/C15.md. Reconcile progress with the actual checkout and evidence. Continue the first unfinished checkpoint; update STATUS.md and handoffs/C15.md. Do not repeat completed work, start another component, make cloud writes or paid calls, or publish production data.
