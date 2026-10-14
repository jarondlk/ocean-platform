# P00 — Local UI and UX prototype

**Status:** Complete (accepted 2026-10-14 JST). **Prerequisites:** None. **Contract:** provisional v1 frontend interaction models.

## Objective and boundaries

Build and iteratively review the future v1 interface locally before implementing
backend components. Follow [UI_UX_BRIEF.md](../UI_UX_BRIEF.md) and
[SITE_SEPARATION.md](../SITE_SEPARATION.md). Work on overhaul in a new frontend-v1
directory with its own package/runtime configuration; keep the legacy frontend
and production site intact. P00 was explicitly selected on 2026-10-13 JST.

Included: runnable local frontend, navigation, realistic synthetic fixtures,
interactive journeys, responsive layouts, English/Japanese and theme support,
local presentation/demo state, screenshots and user feedback iterations.
Excluded: real authentication, production API access, backend implementation,
database migrations, live model calls, real experiment execution, data transfer,
cloud provisioning and deployment. Existing frontend code may be read/reused as
a reference without changing its deployed architecture.

## Resumable checkpoints and acceptance

1. **Runnable shell and primary journey.** Establish frontend-v1 with a documented
   localhost command, provisional typed fixture adapter and obvious preview
   labelling. Implement start/resume investigation, ask a sample question and
   open sample evidence. Verify it works without backend services or credentials.
2. **Complete interaction prototype.** Add catalogue/context selection, separate
   conversations, evidence/results, clarification, partial/error/retry/cancel
   states and simulated experiment review. Preview controls must be functional;
   any unavailable function explains why. Nothing executes real analysis.
3. **Review and refine UX.** Open the local app for the user and iterate on the
   journeys in the brief. Record feedback and specific changes. Check desktop and
   narrow layouts, keyboard/focus, long Japanese labels and both themes. Preserve
   drafts, offer reversible context changes and keep the scope understandable.
4. **Handoff the accepted direction.** Record user-reviewed choices, outstanding
   issues, fixture schema/adapter boundaries and component mapping. Complete P00
   only after the local checks pass and the user has accepted the direction for
   backend integration. If feedback is pending, keep Ready for review or In progress.

No number of iterations or implementation timeline is prescribed. Routine UI
tweaks within an explicitly selected P00 do not require repeated permission.
Backend implementation still requires the user's separate component selection.

## Verification and handoff

During implementation, define and run the new frontend's actual typecheck/build
scripts and focused interaction checks for scope controls, draft preservation,
evidence navigation and simulated approvals. Do not assume legacy frontend test
commands validate this app. Inspect local runtime network behavior to confirm
no production/provider requests; fixture output must never silently become real.
Capture local viewports and manual keyboard/accessibility observations.

Record start/stop commands, runtime prerequisites, local URL, changed files,
screenshots, reviewed scenarios, user feedback, deferred integrations and exact
next action in handoffs/P00.md and STATUS.md. Do not create a handoff until P00 is
selected. C08 reconciles the provisional contracts; C15/C16/C18/C25 retain their
real-service integration and acceptance work. Do not mark them complete from P00.

## Exact prompts

Use the independent planning, implementation or resume prompt for P00 in
[PROMPTS.md](../PROMPTS.md#p00). All modes read this specification, the UX brief,
site-separation plan, master plan, decisions and current status.
