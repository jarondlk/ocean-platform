# Component handoffs

No implementation handoffs exist yet. Create C01.md through C27.md only when
work on that component is explicitly selected. Do not manufacture completion
receipts during setup.

Copy [TEMPLATE.md](TEMPLATE.md). Maintain a current-state section and append
checkpoint receipts beneath it. Preserve earlier acceptance evidence rather
than overwriting it with a new success claim.

Record at least:

- Component and state; timestamp with timezone.
- Actual branch/worktree and commit, plus uncommitted files where relevant.
- Prerequisite evidence checked against the current checkout.
- Checkpoints completed and exact next unfinished action.
- Changed paths and interface/decision changes.
- Validation commands, outcome, code revision and material skipped checks.
- Remaining risks, blockers and environment requirements.
- A complete resume instruction.

Update after each completed checkpoint and before a long operation when useful.
A hard cutoff can still occur before writing; the next session must reconcile
the handoff with Git and the actual files before continuing.

Marking Complete requires the component's acceptance checks, not simply a
plausible implementation or a successful narrow test.
