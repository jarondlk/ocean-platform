# OCEAN v1.0.0 Planning Hub

**P00 and C01–C10 are Complete locally; C11–C27 are not started.**
This folder is the portable source of truth for the accepted architecture,
component prompts and resumable progress. Start here in a fresh chat.

## Read and choose

1. Read [MASTER_PLAN.md](MASTER_PLAN.md) and [DECISIONS.md](DECISIONS.md).
2. Check [STATUS.md](STATUS.md) and the selected component's prerequisites.
3. Open its specification from [COMPONENTS.md](COMPONENTS.md).
4. Copy its planning, implementation or resume prompt from
   [PROMPTS.md](PROMPTS.md). Planning is the default until the user explicitly
   selects implementation.

**Completed:** P00 — Local UI and UX prototype, accepted on 2026-10-14 JST.
The Pipeline & jobs page is omitted as requested. Read [its handoff](handoffs/P00.md)
for the accepted direction and verified source receipt. C01 scientific scope
validation is Complete; read [its handoff](handoffs/C01.md). C02 derived-evidence
software and synthetic acceptance are Complete; read [its handoff](handoffs/C02.md).
C03 retention integrity is Complete with actual disposable PostgreSQL acceptance;
read [its handoff](handoffs/C03.md). C04 authentication responsiveness is Complete locally;
read [its handoff](handoffs/C04.md). C05 retrieval correctness is Complete locally
with actual PostgreSQL acceptance; read [its handoff](handoffs/C05.md) and
[deferred rebuild procedure](C05_REBUILD_RUNBOOK.md). Later components require separate selection.

The user subsequently authorized audited repository delivery. See the
[C01/C02 delivery audit](DELIVERY_AUDIT_2026-10-14.md) and its final source receipt;
the original component receipts remain historical after the audit corrections.
C03/C04 delivery and hosted acceptance now pass;
[C05 readiness audit](C05_READINESS_AUDIT_2026-10-15.md) records the current source
and records readiness before C05 was selected. Current C05 acceptance is
recorded separately in [its receipt](evidence/C05/verification.json).
C05 is now committed/pushed as `fd8f520` with passing hosted CI;
[the C06 readiness audit](C06_READINESS_AUDIT_2026-10-15.md) verifies its prerequisite
and 99-test baseline. C06 was explicitly selected after the readiness checkpoint and is Complete locally;
read [its handoff](handoffs/C06.md). C06 is committed/pushed as `27d76c9`
with passing hosted CI; [delivery receipt](evidence/C06/delivery.json).
C07 export safety is complete and committed/pushed as `1195796` with
[passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38670737411); read [its handoff](handoffs/C07.md) and
[delivery receipt](evidence/C07/delivery.json). C08 is Complete locally; read its handoff and contract guide. C09 is now selected and Complete locally; see its handoff.

The new site is fully isolated from the legacy production site. Read
[SITE_SEPARATION.md](SITE_SEPARATION.md) and [UI_UX_BRIEF.md](UI_UX_BRIEF.md).
All work continues on overhaul; main and the legacy deployment remain unchanged.

Use P00 first, then one C01–C27 component at a time, numerically by default.
Dependencies, not the number alone, determine readiness. Each component has
smaller checkpoints:
finishing one checkpoint and recording a useful handoff is valid partial
progress. New chats do not increase account usage limits; the purpose here is
recoverable, bounded work when a session is interrupted.

## Documents

| Document | Responsibility |
|---|---|
| [Master plan](MASTER_PLAN.md) | Full product, scientific, architecture and UI design |
| [Decisions](DECISIONS.md) | User selections, accepted defaults and exclusions |
| [Site separation](SITE_SEPARATION.md) | Independent infrastructure, approved-data copies and legacy preservation |
| [UI/UX brief](UI_UX_BRIEF.md) | Local prototype journeys, human-centered interactions and review loop |
| [Components](COMPONENTS.md) | Component map and exact dependency graph |
| [Status](STATUS.md) | Actual work state, checks and next eligible work |
| [Prompts](PROMPTS.md) | Independent planning, implementation and resume prompts |
| [Acceptance map](ACCEPTANCE_MAP.md) | Requirement ownership and integration gates |
| [Scalability review](SCALABILITY_REVIEW.md) | Data, analysis and user growth assessment; proposed capacity refinements |
| [Handoffs](handoffs/README.md) | Checkpoints, evidence and resumption |
| [UI concept](mockups/README.md) | Retained image and interaction interpretation |
| [Hub instructions](HUB_PROMPT.md) | Current planning/recovery instructions for the hub |
| [Setup receipt](SETUP_RECEIPT.md) | Planning-only preparation evidence and baseline |

The JSON [component manifest](components.json) is an index for IDs, filenames,
titles and dependencies. It is not a substitute for specifications or STATUS.
Update the manifest, index, prompts and status together if a component changes.

## Working agreement

- Starting a planning-only prompt authorizes inspection and design, not code.
- Starting a component implementation prompt authorizes that component's local
  application work and appropriate tests, not automatic work on the next one.
- Preserve unrelated changes. Inspect the actual checkout and predecessor
  evidence; dates and historical audit reports are not current test results.
- Record branch/worktree, commits or uncommitted paths, verified checkpoints,
  commands/results, remaining work and the exact next action in the handoff.
- Update STATUS and handoff after meaningful checkpoints, before expensive
  checks where practical, and before stopping. Do not rely on a final reply.
- No production mutations, acquisition, scientific publication, cloud resource
  provisioning, paid provider evaluations, deployment or destructive operations
  are implied. C24/C27 prepare configuration/runbooks only.
- Do not commit, merge or create a PR merely as a consequence of this planning
  setup. Follow the user's later instructions for repository delivery.
- P00 proves the local UX direction only; it cannot complete C15/C16/C18/C25 or
  satisfy scientific, backend, isolation or deployment gates. Reuse its frontend
  through staged real-service integration.
- A missing prerequisite blocks dependent implementation, not planning.
  Report the exact missing evidence; do not silently implement that prerequisite.

## Definition of component completion

Acceptance checks passed at a recorded code revision; failures/skips and their
implications are explicit; compatibility behavior is checked; the handoff is
usable without chat history. If a required acceptance environment is unavailable,
record the achieved checkpoints and remaining gate instead of claiming Complete.
Scientific eligibility and deployment acceptance are never inferred from local
synthetic tests.

Allowed states: Not started, In progress, Blocked, Ready for review, Complete.
Ready for review means implementation and local evidence are prepared, with
review or explicitly identified acceptance still outstanding.

## Future validation environment

Component commands are future implementation checks, not instructions to run
them during planning. Python commands assume the repository environment is
active: `source .venv/bin/activate` from the repository root. The current shell
has `python3` but no global `python`. If `.venv` is absent or stale, follow the
repository's documented locked dependency setup before testing; do not invent
successful results or silently substitute another environment. V1 frontend commands use the actual scripts created in frontend-v1 during P00.
The existing frontend/package.json remains a legacy reference and regression
boundary; its checks do not validate the new frontend. Record the actual interpreter,
dependency state and any unavailable integration environment in the handoff.

## Baseline and scope

Design began on 2026-10-12 JST; planning package prepared on 2026-10-13 JST from main at
a73ea7fa48b88fe91995fda0cc25e481e63a9355. This is a discovery baseline,
not a requirement to reset future work to this commit.
Existing unrelated README, audit and benchmark modifications are preserved.
P00 progress is recorded in [STATUS.md](STATUS.md) and [its handoff](handoffs/P00.md).
C01 and C02 are complete with offline evidence; C03 is complete with local unit
and actual disposable PostgreSQL evidence. C04 and C05 are Complete locally; C06 is Complete locally; C07 is Complete locally; C08 is Complete locally; C09 is Complete locally; C10 is Complete locally; C11–C27 remain Not started.
The 2026-10-13 revision adds P00 before the original 27 numbered components; the
setup receipt retains its historical counts and records this amendment.

C08 catalogue contracts and synthetic fixtures are complete, committed/pushed as
`6d20a75` with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38695834706);
[delivery receipt](evidence/C08/delivery.json). Read
[its handoff](handoffs/C08.md) and [contract guide](C08_CATALOGUE_CONTRACT.md)
before C09 or later integration.

C09 readiness is verified: C03/C08 source receipts match, 51 baseline tests and
246 prerequisite regressions pass, and generated contracts are current. See
[C09 readiness audit](C09_READINESS_AUDIT_2026-10-15.md). C09 was subsequently selected and is Complete locally; see [its handoff](handoffs/C09.md) and [snapshot contract](C09_SNAPSHOT_CONTRACT.md). C10 remains unselected.

C09 is complete and delivered as `9214bbe` with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38703483565).
Read [its handoff](handoffs/C09.md), [snapshot contract](C09_SNAPSHOT_CONTRACT.md)
and [delivery receipt](evidence/C09/delivery.json). C10 remains unselected.

C10 readiness is verified at `ae02e89`: 36 baseline and 534 prerequisite tests
pass; C02/C09 accepted sources reconcile and generated contracts are current.
See [the readiness audit](C10_READINESS_AUDIT_2026-10-15.md). C10 was subsequently selected and is Complete locally; read [its handoff](handoffs/C10.md) and [adapter contract](C10_ADAPTER_CONTRACT.md). C11 remains unselected.

C10 is complete and delivered as `c3d5b8b` with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38731722030).
Read [its handoff](handoffs/C10.md), [adapter contract](C10_ADAPTER_CONTRACT.md)
and [delivery receipt](evidence/C10/delivery.json). C11 remains unselected.

C11 readiness is verified at `7570345`: 55 baseline, 482 prerequisite and 69
additional SST semantic/calendar tests pass; six generated contracts are current.
C02/C09 accepted sources reconcile, and C10 exact-source hosted CI is green.
See [the readiness audit](C11_READINESS_AUDIT_2026-10-15.md). C11 remains
Not started and unselected.
