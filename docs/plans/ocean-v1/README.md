# OCEAN v1.0.0 Planning Hub

**P00 and C01–C20 are Complete with hosted delivery; C21 is In progress; C22–C27 are Not started.**
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
and actual disposable PostgreSQL evidence. C04 and C05 are Complete locally; C06 is Complete locally; C07 is Complete locally; C08 is Complete locally; C09 is Complete locally; C10 is Complete locally; C11 is Complete locally; C12 is Complete locally; C14–C27 remain Not started.
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
See [the readiness audit](C10_READINESS_AUDIT_2026-10-15.md). C10 was subsequently selected and is Complete locally; read [its handoff](handoffs/C10.md) and [adapter contract](C10_ADAPTER_CONTRACT.md). C11 was subsequently selected; see [its handoff](handoffs/C11.md).

C10 is complete and delivered as `c3d5b8b` with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38731722030).
Read [its handoff](handoffs/C10.md), [adapter contract](C10_ADAPTER_CONTRACT.md)
and [delivery receipt](evidence/C10/delivery.json). C11 was subsequently selected; see [its handoff](handoffs/C11.md).

C11 readiness is verified at `7570345`: 55 baseline, 482 prerequisite and 69
additional SST semantic/calendar tests pass; six generated contracts are current.
C02/C09 accepted sources reconcile, and C10 exact-source hosted CI is green.
See [the readiness audit](C11_READINESS_AUDIT_2026-10-15.md). C11 was subsequently
selected and is Complete locally; read [its handoff](handoffs/C11.md) and
[SST contract](C11_SST_ADAPTER_CONTRACT.md). Source `41cd876` is committed/pushed with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38744193298); [delivery receipt](evidence/C11/delivery.json).

C12 readiness is verified at `1d3b7b6`: 116 baseline, 677 prerequisite and 83
additional eDNA semantic tests pass; seven generated contracts are current.
C01/C09 accepted sources reconcile. See [the readiness audit](C12_READINESS_AUDIT_2026-10-15.md)
for raw-method representation, cohort/denominator and retrieval-independence work.
C12 was explicitly selected; [implementation handoff](handoffs/C12.md).

C12 local acceptance is complete: 1,646 required tests, full backend 3,220/127
PostgreSQL skips at 84.11% coverage, 82 actual PostgreSQL cases and 163 v1 browser tests
plus typecheck/build/audit. Read [handoff](handoffs/C12.md),
[contract](C12_EDNA_ADAPTER_CONTRACT.md) and [receipt](evidence/C12/verification.json).
Source `d3ef699` is committed/pushed with [passing exact-source CI](https://github.com/jarondlk/ocean-platform/actions/runs/38845253029): 3,211 backend/84.85% coverage, 127 actual PostgreSQL cases and both frontend gates. [Delivery receipt](evidence/C12/delivery.json). C13 is not selected.

C13 local acceptance is complete: 1,969 required tests, 3,503 backend/127 gated
PostgreSQL skips at 84.49% coverage, nine generated checks and preserved previous
artifacts. [Handoff](handoffs/C13.md), [contract](C13_SCIENTIFIC_CATALOGUE_CONTRACT.md),
[receipt](evidence/C13/verification.json). Source checkpoint and exact-source hosted
delivery are pending. Three-hour continuation and later sequential readiness/
implementation are user-authorized; real scientific/transfer/cloud gates remain explicit.

C13 final eligibility amendment is delivered as `98c2769` with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38876797068):
3,516 backend/85.22% coverage, 127 actual PostgreSQL, 163 v1/132 legacy frontend
tests and both builds/typechecks/audits. Final local acceptance is 1,991 required
and 3,525 backend/84.50% coverage; 305 new C13 cases. Earlier local counts above
are historical. [Delivery receipt](evidence/C13/delivery.json),
[final local receipt](evidence/C13/method-alias-amendment/verification.json).

C14 local acceptance is complete: 2,367 required tests; 3,799 backend/127 gated
PostgreSQL skips/84.75% coverage; 274 new cases and nine generated checks. One
authenticated service powers seven routes/tools, complete path/ID/name search,
100,000-object traversal and actual frozen-source parity. [Handoff](handoffs/C14.md),
[contract](C14_CATALOGUE_SERVICE_CONTRACT.md), [receipt](evidence/C14/verification.json).
Exact-source hosted delivery precedes automatic C15 readiness/implementation.

C14 source `19ba911` is committed/pushed with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38916279621):
3,790 backend/85.45% coverage, 127 actual PostgreSQL, 163 v1/132 legacy frontend
tests and both builds/typechecks/audits. [Delivery receipt](evidence/C14/delivery.json).
C15 local readiness preparation passes; final selection follows this delivery.

### C15 delivered; C16 started — 2026-10-17 JST

C15 source7b1659c passes source-bound hosted CI38923128922 and is delivered
at9688867. Trusted identity, isolated preview, responsive shell and browser gates
pass; [handoff](handoffs/C15.md), [delivery receipt](evidence/C15/delivery.json).
C16 formal prerequisites reconcile across75 accepted-current entries and the
[user-authorized readiness audit](evidence/c16-readiness-2026-10-17/audit.md)
selects implementation. [Current C16 handoff](handoffs/C16.md). No cloud or real
data operation is implied.

### C16 local acceptance — 2026-10-18 JST

Explicit authenticated snapshot discovery and the standalone service catalogue
pass local acceptance:510 v1 tests,3895 backend/127 gated skips/84.87%,134 actual
HTTP/tool wire cases, all51 parent paths and100000-object client/HTTP traversal.
Rendered EN/JA, light/dark, mobile/desktop, history, revocation and keyboard/
accessibility-tree observations are recorded in the [C16 handoff](handoffs/C16.md).
Source4981642 is committed/pushed with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39080160597):3886 backend/85.57%,127 actual PostgreSQL,510 v1/132 legacy tests and both builds/typechecks/audits. [Delivery receipt](evidence/C16/delivery.json). Original evidence
and unrelated/scientific/legacy files remain unchanged. C17 formal source audit
may now be finalized before automatic local implementation.

### C17 local acceptance — 2026-10-18 JST

Owner-private investigations, conversations, immutable context revisions and
explicit refresh branches pass local acceptance. Final backend4187/187 gated
skips/85.08%,60 actual disposable PostgreSQL cases,155 affected API and177 required
regression/guard cases pass. All19 final source hashes remain stable; original
receipts and protected unrelated/scientific/legacy files are preserved. See
[handoff](handoffs/C17.md) and [contract](C17_INVESTIGATION_CONTRACT.md).
Source39bb811 is committed/pushed with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39101652175):4178 backend/85.76%,187 actual PostgreSQL,510 v1/132 legacy frontend tests and both builds/typechecks/audits. [Delivery receipt](evidence/C17/delivery.json). C18 readiness selection follows the delivery checkpoint.

C18 readiness verifies98 prerequisite entries and C17 exact-source hosted delivery. All3 local interface checkpoints are selected; see [handoff](handoffs/C18.md).

C18 local acceptance passes:4214 backend/187 gated skips/85.08%;673 frontend,
production typecheck/build and development strict typecheck. Actual C17/C16
browser journeys cover private navigation/context/refresh/account isolation;
production execution remains unavailable. [Contract](C18_CHAT_WORKSPACE_CONTRACT.md),
[handoff](handoffs/C18.md), [receipt](evidence/C18/verification.json). Exact-source
hosted delivery is complete; C19 readiness follows.

Source596d871 is committed/pushed; [exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39124675912) passes:4205 backend/187 gated skips/85.76%,187 actual PostgreSQL,673 v1/132 legacy frontend, both builds/typechecks/audits, generated checks, migration/idempotence and isolated backup/restore. [Delivery receipt](evidence/C18/delivery.json). C19 readiness follows delivery.

C19 final readiness passes59 entries/52 unique paths after C18 delivery; local implementation is selected automatically. [Handoff](handoffs/C19.md).

C19 local acceptance passes: 4570 backend/187 gated skips/85.43%;356 new C19 cases and164 required compatibility cases; all9 generated checks/Ruff and independent source review. Inventory-first C17/C14 exploration, binding pins, full-count/later-page discovery, deterministic completion and cooperative stopping are implemented. C18 frontend23 sources remain unchanged. Exact-source hosted delivery is complete. [Handoff](handoffs/C19.md), [contract](C19_AGENT_CONTROLLER_CONTRACT.md), [receipt](evidence/C19/verification.json).

C19 hosted CI reached98percent before its20-minute job timeout. The CI-only
[amendment](evidence/C19/ci-budget-amendment/verification.json) permits30minutes;
all application/test sources and original receipts remain unchanged. This historical
attempt is superseded by the complete exact-source delivery below.

Source4618188 is committed/pushed; [exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39154765984) passes:4561 backend/187 gated skips/86.08%,187 actual PostgreSQL,673 v1/132 legacy frontend, both builds/typechecks/audits, generated checks, migration/idempotence and isolated backup/restore. [Delivery receipt](evidence/C19/delivery.json). C20 readiness follows delivery.

C20 final36-entry/34-path readiness passes after C19 exact-source delivery; isolated local implementation is selected. [Handoff](handoffs/C20.md).

C20 amended local acceptance passes: unchanged4847 backend/231 gated skips/85.64%,104 actual PostgreSQL,805 v1 frontend/typecheck/build/audit, nine generated checks/Ruff and independent source reviews. The final pagination amendment keeps newly acknowledged off-page runs visible through fresh authorization. All1005 evidence files tracked at the original source and protected files remain unchanged. Amended sourcea149239 is pushed; [exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39209113719) and final delivery pass. [Handoff](handoffs/C20.md), [contract](C20_DURABLE_EXECUTION_CONTRACT.md), [receipt](evidence/C20/verification.json).

C20 final hosted delivery: Sourcea149239 is committed/pushed; [exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39209113719) passes: 4838 backend / 231 gated skips / 86.27% coverage, 231 actual PostgreSQL cases, 805 v1 and 132 legacy frontend tests, both typechecks/builds/audits, generated contracts, migrations/idempotence and isolated backup/restore. [Receipt](evidence/C20/delivery.json). C21 final readiness and selection follow this committed/pushed delivery checkpoint.
