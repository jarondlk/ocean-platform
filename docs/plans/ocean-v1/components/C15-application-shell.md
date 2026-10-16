# C15 — New application shell

**Status:** Complete for local acceptance; source checkpoint and hosted delivery pending. **Prerequisites:** P00, C08.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Integrate and harden the P00 frontend-v1 shell around Research, Context Catalog and Tools. Reuse the user-reviewed navigation and layout, reconcile C08 contracts and add v1 runtime/permission boundaries. The legacy frontend and site remain intact.

Include application navigation, permission-aware route groups, reusable split panels, tabs/drawers, typography, themes, localization and empty/loading/error shells. Exclude functional catalogue browsing, investigation persistence, agent execution, experiments and redesigning the internals of every specialist page.

Verified entry points: [application shell](../../../../frontend/components/AppShell.tsx), [navigation](../../../../frontend/components/AppNavigation.tsx), [root layout](../../../../frontend/app/layout.tsx), [global styles](../../../../frontend/app/globals.css), and [preferences](../../../../frontend/lib/preferences.tsx). Review the planning mockups as visual references; illustrative data is not production content.

## Interfaces and decisions

Primary destinations are Research, Context Catalog and Tools. Tools groups relevant v1 Data, Explore, Provenance and Evaluation workflows; Settings and Administration remain permission-controlled. Legacy deep links remain on the legacy site. Do not share its session cookies or proxy requests to its APIs. New v1 destinations show clear unavailable states until their owning components are integrated.

Retain OCEAN branding, restrained ocean-blue accents, light/dark themes and English/Japanese support. Define shared headers, scope/snapshot labels, status treatments and accessible panel controls. Desktop investigation layouts support navigation, conversation and Workspace; the catalogue layout supports tree, listing and inspector. Layout primitives accept content supplied by later components without duplicating domain state.

At narrow widths, panels become tabs or drawers without hiding essential actions. Keyboard controls and visible focus are required for navigation, resizing and dismissal. Route changes must not accidentally reveal hidden destinations or erase future persisted investigation state. Store purely presentational preferences separately from scientific scope.

## Prototype-to-service integration

Read the P00 handoff and reuse frontend-v1; do not restart the UI from the static
mockup. Keep the accepted UX and iterate on any contract-driven change. P00's
synthetic interactions do not satisfy this component's real-service acceptance.
Use the actual frontend-v1 scripts established in P00 and record runtime/browser
checks against the appropriate v1 services. Existing frontend paths above are
reference implementations, not the target for the new site.

## Resumable checkpoints

1. **Reconcile and reuse P00.** Retain accepted route grouping, design tokens and layouts; bind them to C08 contracts and v1 permission/capability state. Acceptance: permitted v1 destinations remain reachable, restricted links remain absent, and no legacy session or API is needed.
2. **Implement responsive shell.** Build desktop splits and narrow-screen transitions. Acceptance: keyboard operation works, panes remain readable, and Japanese text does not overflow essential controls in either theme.
3. **Verify independent runtime behavior.** Acceptance: v1 capability flags expose honest loading/error/unavailable states; fixture mode cannot silently serve production; rollback affects only the v1 shell and preserves v1 data.

## Validation, compatibility and handoff

Planned commands, after P00 establishes these scripts: `npm --prefix frontend-v1 run typecheck`, `npm --prefix frontend-v1 test`, and `npm --prefix frontend-v1 run build`. New shell interaction tests and manual viewport/accessibility checks are planned during implementation; document viewports, themes and locales tested. Existing automated tests do not by themselves prove keyboard or screen-reader behavior.

Use independent v1 capability flags. Rollback switches a compatible v1 shell without modifying application data or legacy routing. Record component interfaces, navigation mapping, visual references and verification evidence in `handoffs/C15.md`; update `STATUS.md` after each checkpoint.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c15). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.
