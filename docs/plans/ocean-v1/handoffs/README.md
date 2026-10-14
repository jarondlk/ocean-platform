# Component handoffs

[P00.md](P00.md) records the accepted local prototype. [C01.md](C01.md) records
completed offline scientific scope validation. [C02.md](C02.md) records completed
derived-evidence software and synthetic checks. [C03.md](C03.md) records completed
transaction-ordering and disposable PostgreSQL retention acceptance. [C04.md](C04.md)
records completed local authentication responsiveness acceptance. [C05.md](C05.md) records completed local retrieval correctness and actual PostgreSQL acceptance. Create remaining component
handoffs only when work on that component is explicitly selected. Do not manufacture completion
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

P00 records the local URL/commands, prototype screenshots, reviewed journeys, user
feedback, accepted direction and provisional fixture contracts. It cannot stand
in for backend/integration evidence. All later handoffs record v1 isolation and
identify any separately authorized copied data; no live legacy access is implied.
