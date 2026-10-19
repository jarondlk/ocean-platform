# Implementation status

Updated: 2026-10-19 JST. **P00 and C01–C19 are Complete; C20's amended local gates pass; repair source checkpoint and hosted delivery are pending.**
The latest plan adds local UI/UX work first and a fully isolated second GCP site.
P00 is accepted; C01 local validation was explicitly selected and completed on
2026-10-14 JST.
C02 was explicitly selected on 2026-10-14 JST and passed its software/synthetic
checks. C03 passed its local transaction-ordering and actual disposable PostgreSQL
acceptance. C04 now passes concurrent responsiveness, worker-lifetime, security
and cancellation acceptance. C05 passes embedding isolation, metagenome fidelity
and deterministic replacement-history acceptance. C06 passes strict generation/consumer acceptance. C07 passes CSV presentation/consumer acceptance; C08 passes catalogue contract/fixture acceptance; C09 is Complete for local snapshot/capture acceptance; C10 passes frozen CTD/metagenome adapter acceptance; C11 passes frozen SST product/coverage acceptance; C12 passes frozen canonical eDNA adapter acceptance; C13 passes scientific catalogue acceptance; C14 passes authenticated catalogue service acceptance; C15 passes local application-shell acceptance; C16 passes local catalogue-browser acceptance; C17 passes local investigation-persistence acceptance; C18 passes local interface acceptance and hosted delivery; C19 passes local controller acceptance and hosted delivery; C20 is Ready for review with local acceptance complete; C21–C27 remain Not started.
P00 and C01–C13 local work is authorized; the user also authorizes subsequent CXX local implementation after each readiness audit passes.
See [P00](handoffs/P00.md), [C01](handoffs/C01.md), [C02](handoffs/C02.md),
[C03](handoffs/C03.md), [C04](handoffs/C04.md), [C05](handoffs/C05.md), [C06](handoffs/C06.md), [C07](handoffs/C07.md), [C08](handoffs/C08.md), [C09](handoffs/C09.md) and [C10](handoffs/C10.md) handoffs for current evidence.

Latest local implementation: **C20 — Durable research execution**. Original backend4847/231 gated skips/85.64%,76 compatibility and104 actual PostgreSQL acceptance remains on unchanged source. The final history pagination amendment passes805 v1 tests/typecheck/build/audit and independent review. Original46/167 source maps remain historical; the amendment records exact source supersessions and preserves all1005 evidence files tracked at fc46da3 plus30 unrelated/7 scientific/2 serving/106 legacy files. Amended source checkpoint and its exact-source hosted CI remain pending; the original [fc46da3 run](https://github.com/jarondlk/ocean-platform/actions/runs/39207358123) cannot accept the repair. [Handoff](handoffs/C20.md), [contract](C20_DURABLE_EXECUTION_CONTRACT.md), [receipt](evidence/C20/verification.json).

Latest delivered implementation: **C19 — Agent exploration controller**. Source4618188 is committed/pushed; [exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39154765984) passes:4561 backend/187 gated skips/86.08%,187 actual PostgreSQL,673 v1/132 legacy frontend, both builds/typechecks/audits, generated checks, migration/idempotence and isolated backup/restore. [Handoff](handoffs/C19.md), [contract](C19_AGENT_CONTROLLER_CONTRACT.md), [delivery receipt](evidence/C19/delivery.json). C20 readiness follows delivery.

Previous delivered implementation: **C16 — Complete catalogue browser**. **3,895 backend/127 gated skips/84.87% coverage;510 v1 tests, typecheck/build, nine generated checks;134 actual HTTP/tool parity cases; all51 canonical objects through parents;100000-object client/HTTP reachability and manual browser keyboard/accessibility-tree checks pass.** Source `4981642` is committed/pushed with [passing exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39080160597):3886 backend/85.57%,127 actual PostgreSQL,510 v1/132 legacy tests and both typechecks/builds/audits. [Delivery receipt](evidence/C16/delivery.json). [Handoff](handoffs/C16.md), [contract](C16_CATALOGUE_BROWSER_CONTRACT.md), [browser observations](evidence/C16/browser-qa.md). Spoken screen-reader/independent user validation and production capacity are not claimed.

Previous delivered implementation: **C15 — New application shell**. **2,391 required; 3,823 backend/127 gated skips/84.79% coverage; 249 v1 tests, typecheck/build, nine generated checks and local browser/keyboard gates pass.** Trusted current identity, explicit preview isolation and presentation-only storage. [Handoff](handoffs/C15.md), [contract](C15_APPLICATION_SHELL_CONTRACT.md), [receipt](evidence/C15/verification.json). Source `7b1659c` is committed/pushed with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38923128922): **3,814 backend/85.49% coverage,127 actual PostgreSQL,249 v1/132 legacy frontend tests and both builds/typechecks/audits**. [Delivery receipt](evidence/C15/delivery.json).

Earlier delivered implementation: **C14 — Catalogue service and tools**. **2,367 required tests; 3,799 backend/127 gated skips/84.75% coverage; 274 new cases; nine generated checks**. [Handoff](handoffs/C14.md), [contract](C14_CATALOGUE_SERVICE_CONTRACT.md), [receipt](evidence/C14/verification.json). Source `19ba911` is committed/pushed with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38916279621): **3,790 backend/85.45% coverage, 127 actual PostgreSQL and both frontend gates**. [Delivery receipt](evidence/C14/delivery.json).

C13 — Scientific catalogue sections. Local acceptance: **1,991 required; 3,525 backend/127 gated PostgreSQL skips/84.50% coverage; nine generated checks**. Read [handoff](handoffs/C13.md), [contract](C13_SCIENTIFIC_CATALOGUE_CONTRACT.md) and [receipt](evidence/C13/verification.json). Final source `98c2769` is committed/pushed with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38876797068): **3,516 backend/85.22% coverage, 127 actual PostgreSQL, 163 v1/132 legacy frontend tests and both builds/typechecks/audits**. [Delivery receipt](evidence/C13/delivery.json).

C12 — eDNA adapter. Local acceptance: **1,646 required; 3,220 backend/127 gated PostgreSQL skips/84.11% coverage; 82 actual PostgreSQL; 163 v1 tests and eight generated checks**. Read [handoff](handoffs/C12.md), [contract](C12_EDNA_ADAPTER_CONTRACT.md) and [receipt](evidence/C12/verification.json). Source `d3ef699` is committed/pushed with [passing exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38845253029): **3,211 backend/84.85% coverage, 127 actual PostgreSQL cases, 163 v1/132 legacy frontend tests and both typechecks/builds/audits**. [Delivery receipt](evidence/C12/delivery.json).

C11 — SST adapter. Local acceptance is complete: 966 required tests; full backend 2,829 passed/84 gated PostgreSQL skips, 83.29% coverage. Read [the handoff](handoffs/C11.md), [contract](C11_SST_ADAPTER_CONTRACT.md) and [receipt](evidence/C11/verification.json). Source `41cd876` is committed/pushed; [exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38744193298) passes: 2,820 backend tests/84.04% coverage, 84 actual PostgreSQL cases and both frontend gates. [Delivery receipt](evidence/C11/delivery.json).

C10 — CTD and metagenome adapters: Committed/pushed as `c3d5b8b`; [hosted CI passes](https://github.com/jarondlk/ocean-platform/actions/runs/38731722030). [Delivery receipt](evidence/C10/delivery.json) records 2,570 backend tests/83.68% coverage, 84 actual PostgreSQL cases and both frontend gates. Read [C10 handoff](handoffs/C10.md), [contract](C10_ADAPTER_CONTRACT.md) and [receipt](evidence/C10/verification.json).

C09 — Immutable catalogue snapshots: Committed/pushed as `9214bbe`; [hosted CI passes](https://github.com/jarondlk/ocean-platform/actions/runs/38703483565). [Delivery receipt](evidence/C09/delivery.json) records 2,460 backend tests/83.39% coverage, 84 actual PostgreSQL cases and both frontend gates. Read [the snapshot contract](C09_SNAPSHOT_CONTRACT.md) and [local receipt](evidence/C09/verification.json).
C08 is committed/pushed as `6d20a75` with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38695834706);
[local receipt](evidence/C08/verification.json), [delivery receipt](evidence/C08/delivery.json).
C07 is committed/pushed as `1195796` with [passing hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/38670737411);
[local source receipt](evidence/C07/verification.json), [delivery receipt](evidence/C07/delivery.json).
C06 local acceptance and source hashes are recorded in [its receipt](evidence/C06/verification.json).
C05 is committed/pushed as `fd8f520`; its original local source receipt is preserved.
[The delivery and C06 readiness audit](C06_READINESS_AUDIT_2026-10-15.md) records
passing hosted CI and confirms that C06 can start after explicit selection.
P00 passed its local UX/user-review gate; C01 passed its offline scope-validation
checks. C02 passed its synthetic scientific-processing and eligibility checks.
Real-data regeneration and review remain outstanding. C03 fixes atomic hold/deletion
ordering and passes 12 actual PostgreSQL cases; its disposable server is stopped.
Later implementation requires prerequisite evidence;
any component can be planned now. Work stays on overhaul, with main and legacy
production unchanged. See [site separation](SITE_SEPARATION.md) and
[UI/UX brief](UI_UX_BRIEF.md).

| Component | State | Checkpoint | Validation | Handoff |
|---|---|---|---|---|
| [P00 — Local UI and UX prototype](components/P00-local-ui-prototype.md) | Complete | Accepted 2026-10-14; Pipeline & jobs omitted as requested | Typecheck, 27 tests and static build pass; scoped UX review plus final admin/keyboard checks; source and screenshots recorded | [P00](handoffs/P00.md) |
| [C01 — Scientific scope validation](components/C01-scientific-scope.md) | Complete | Shared scope contract; exact/synthesis/executor parity and saved receipts | 319 tests pass; Ruff and diff checks pass; [verified source receipt](evidence/C01/verification.json) | [C01](handoffs/C01.md) |
| [C02 — Derived scientific evidence](components/C02-derived-scientific-evidence.md) | Complete | F02/F04/F05 fixed; frozen input receipts, review gate, retained history and supersession | Required suites and composite C01/consumer regressions pass; Ruff/diff pass; [receipt](evidence/C02/verification.json) | [C02](handoffs/C02.md) |
| [C03 — Retention integrity](components/C03-retention-integrity.md) | Complete | Atomic predicate DELETE/hold UPDATE; committed count/audit parity; preserved held/dependent evidence; isolated server stopped | 35 required; 93 with auth/security; 12 actual PostgreSQL cases pass; full suite 1,684 passed, 51 expected gated skips; [receipt](evidence/C03/verification.json) | [C03](handoffs/C03.md) |
| [C04 — Authentication responsiveness](components/C04-authentication-responsiveness.md) | Complete | Complete auth/limiter operations offloaded; worker-owned resources; security and both cancellation styles; independent review passes | 87 required; full suite 1,705 passed, 51 expected PostgreSQL skips, 81.46% coverage; Ruff/preservation pass; [receipt](evidence/C04/verification.json) | [C04](handoffs/C04.md) |
| [C05 — Retrieval correctness](components/C05-retrieval-correctness.md) | Complete | Explicit query embedding identity; named Kraken/MetaEuk mapping; deterministic immutable replacements and preserved history; deferred rebuild runbook | 142 required; 12 actual C05 PostgreSQL cases; 39 existing PostgreSQL regressions; full suite 1,806 passed/63 gated skips, 81.77% coverage; [receipt](evidence/C05/verification.json) | [C05](handoffs/C05.md) |
| [C06 — Model runtime contract](components/C06-model-runtime.md) | Complete | Typed immutable generation result; strict ordinary/structured completion; API/planner usage/timing and safe failure receipts | 230 required; 24 actual-adapter/API/SQLite/planner cases; full suite 1,937 passed/63 gated skips, 81.81% coverage; 39 actual PostgreSQL regressions; [receipt](evidence/C06/verification.json) | [C06](handoffs/C06.md) |
| [C07 — Export safety](components/C07-export-safety.md) | Complete | One shared policy per language; safe strings/headers, typed numeric signs; existing CSV dialects and source data preserved | 196 required server tests; 47 shared cases; 132 legacy/76 v1 frontend tests and both builds/typechecks; full backend 2,121 passed/63 gated skips, 81.85% coverage; [receipt](evidence/C07/verification.json) | [C07](handoffs/C07.md) |
| [C08 — Catalogue contracts and fixtures](components/C08-catalogue-contracts.md) | Complete | Versioned Python/TS envelopes, additive prototype boundary, source-qualified fixtures and exhaustive canonical inventory | 274 required tests; 162 v1 tests/typecheck/build; 100,000 datasets; 10,398 parity cases; full backend 2,314 passed/63 gated skips, 82.28% coverage; [receipt](evidence/C08/verification.json) | [C08](handoffs/C08.md) |
| [C09 — Immutable catalogue snapshots](components/C09-catalogue-snapshots.md) | Complete | Content-addressed exports, bounded consistent capture, references/holds/revocation and synthetic quarantine | 206 required; 21 actual PostgreSQL; backend 2,469 passed/84 gated skips, 82.60% coverage; [receipt](evidence/C09/verification.json) | [C09](handoffs/C09.md) |
| [C10 — CTD and metagenome adapters](components/C10-ctd-metagenome-adapters.md) | Complete | Source-qualified frozen Parquet inputs; exact scoped operations and reproducible C08/C09 integration | 680 required; backend 2,579 passed/84 gated skips, 82.90% coverage; [receipt](evidence/C10/verification.json) | [C10](handoffs/C10.md) |
| [C11 — SST adapter](components/C11-sst-adapter.md) | Complete | Product-separated frozen observations; exact scoped operations, sampling-aware coverage and reproducibility | 966 required; backend 2,829 passed/84 gated skips, 83.29% coverage; [receipt](evidence/C11/verification.json) | [C11](handoffs/C11.md) |
| [C12 — eDNA adapter](components/C12-edna-adapter.md) | Complete | Frozen canonical eDNA; shared SQL predicates; qualified raw/eligible full-population operations | 1,646 required; backend 3,220/127 gated skips, 84.11%; 82 actual PostgreSQL; [receipt](evidence/C12/verification.json) | [C12](handoffs/C12.md) |
| [C13 — Analyses statistics metadata relationships](components/C13-scientific-catalogue-sections.md) | Complete | Final frozen scientific catalogue and legacy-method eligibility | 1,991 required; backend 3,525/127 gated skips, 84.50%; [final receipt](evidence/C13/method-alias-amendment/verification.json) | [C13](handoffs/C13.md) |
| [C14 — Catalogue service and tools](components/C14-catalogue-service-tools.md) | Complete | Service/routes/tools, exhaustive traversal and boundary hardening | 2,367 required; backend 3,799/127 gated skips, 84.75%; 274 new cases | [C14](handoffs/C14.md) |
| [C15 — New application shell](components/C15-application-shell.md) | Complete | Trusted runtime shell, preview isolation, browser gates and hosted delivery | 2,391 required; backend3,823/127skips84.79%; frontend249tests/typecheck/build; nine generated checks | [C15](handoffs/C15.md) |
| [C16 — Complete catalogue browser](components/C16-catalogue-browser.md) | Complete | Explicit discovery and service tree/list/inspector; protected-view invalidation | 3,895 backend/127 gated skips/84.87%;510 v1;134 actual wire parity;100000 reachability; browser gates pass | [C16](handoffs/C16.md) |
| [C17 — Investigation persistence](components/C17-investigation-persistence.md) | Complete | All3 local checkpoints; source39bb811 hosted delivery complete | 4187 backend/187 gated skips/85.08%;60 actual PostgreSQL;155 affected API; protected files and683 older evidence unchanged | [C17](handoffs/C17.md) |
| [C18 — Chat and Workspace interface](components/C18-chat-workspace.md) | Complete | All3 local checkpoints and source596d871 hosted delivery pass | 4214 backend/187 skips/85.08%;673 frontend; strict builds/typechecks; actual C17/C16 browser and account/refresh checks | [C18](handoffs/C18.md) |
| [C19 — Agent exploration controller](components/C19-agent-controller.md) | Complete | All3 local checkpoints and source4618188 hosted delivery pass | 4570 backend/187 gated skips/85.43%;356 new cases/164 compatibility;9 generated checks; actual synthetic C14/C17 and100000 backend | [C19](handoffs/C19.md) |
| [C20 — Durable research execution](components/C20-durable-execution.md) | Ready for review | Original3 local checkpoints plus history repair verified; amended source and hosted delivery pending | Unchanged4847 backend/231 skips/85.64%;104 actual PostgreSQL;805 v1/build/types/audit; independent repair review passes | [C20](handoffs/C20.md) |
| [C21 — Evidence and answer synthesis](components/C21-evidence-synthesis.md) | Not started | None | Not run | Not created |
| [C22 — Experiment proposals and frozen exports](components/C22-experiment-proposals.md) | Not started | None | Not run | Not created |
| [C23 — Isolated Python execution](components/C23-python-sandbox.md) | Not started | None | Not run | Not created |
| [C24 — Isolated GCP site and worker configuration](components/C24-gcp-worker-configuration.md) | Not started | None | Not run | Not created |
| [C25 — Experimental Workspace interface](components/C25-experimental-workspace.md) | Not started | None | Not run | Not created |
| [C26 — System acceptance and evaluation](components/C26-system-acceptance.md) | Not started | None | Not run | Not created |
| [C27 — Release preparation and rollback](components/C27-release-readiness.md) | Not started | None | Not run | Not created |

## Updating this ledger

Use Not started, In progress, Blocked, Ready for review or Complete. Before
changing a state, read the actual checkout and prerequisite handoffs. Record the
latest checkpoint, evidence and exact next action here and in the component's
handoff. Add the handoff link only after that file exists. Keep the specification's
status line aligned. Required checks that are unavailable remain visible gates;
synthetic success does not imply scientific, cloud or release acceptance.

The user authorized verification and branch delivery on 2026-10-14 JST.
[The delivery audit](DELIVERY_AUDIT_2026-10-14.md) records two additional fixes,
the clean candidate suite and current source hashes. Component acceptance receipts
remain historical; that C01/C02 audit does not imply later implementation or deployment.

C03 and the readiness audit are checkpointed as `9a2d225`. The user explicitly
approved pending C03/C04 commits and pushes to origin/overhaul on 2026-10-15 JST,
resolving the prior automatic-review rejection. C03/C04 are delivered, and hosted CI passes for source `276540f` (1,714 backend
tests, 82.28% coverage, both frontends and 51 actual PostgreSQL cases). The C03
fixture now verifies the exact job-owned Docker address in CI; local safety
checks remain intact. See [C05 readiness/delivery audit](C05_READINESS_AUDIT_2026-10-15.md).
Older unrelated audit/benchmark work remains outside this delivery.

P00 has passed only G8, the local UX direction gate. No code revision has passed
the full v1 acceptance map. See [SETUP_RECEIPT.md](SETUP_RECEIPT.md)
for document validation only, and [ACCEPTANCE_MAP.md](ACCEPTANCE_MAP.md) for future checks.

C05 local acceptance includes independent source/acceptance review and two
idempotent upserts into a fresh owned PostgreSQL database. Both disposable servers
are stopped and all C05 fixture schemas removed. The read-only serving inventory
identifies 82 affected legacy documents; [rebuild instructions](C05_REBUILD_RUNBOOK.md)
are deferred. Real files, live stores and providers were not regenerated/called.
C05 hosted CI passes for `fd8f520`: 1,797 backend tests, 82.60% coverage,
both frontends, 63 actual PostgreSQL cases and backup/restore. The 63 broad-suite
PostgreSQL skips are covered by separate hosted integration steps. C06 was then explicitly selected after checkpoint `44c85b9`; its 99-test baseline
and offline F07 probes establish readiness. Current implementation acceptance
is recorded in [its handoff](handoffs/C06.md).

C06 ordinary/structured adapters and strict string wrappers now reject limits,
refusal, malformed/missing/unknown termination. Results preserve measured monotonic
duration and optional actual usage; incomplete parseable JSON cannot execute plans.
Independent review passes. Existing model/provider configuration, retry budgets,
embedding methods and real data remain unchanged. C06 is committed/pushed as `27d76c9`; hosted CI passes: 1,928 backend tests,
82.64% coverage, both frontends, 63 actual PostgreSQL cases and backup/restore.
See [delivery receipt](evidence/C06/delivery.json). The local receipt remains historical.
C07 was explicitly selected; see [its handoff](handoffs/C07.md). C08 was subsequently selected; see its handoff.

C07 local acceptance is complete. Its intended changes supersede only the four
P00 CSV consumer/test files documented in the C07 receipt; the historical P00
receipt and remaining 32 files stay intact. All 30 older unrelated files, 7 real
scientific artifacts and 2 serving files are preserved. Original structured
records and immutable publication bundle bytes remain unchanged. Delivery and
hosted CI pass as `1195796`: 2,112 backend tests/82.67% coverage,
132 legacy/76 v1 tests, both frontend builds/typechecks and production dependency
audits, 63 PostgreSQL cases, idempotent upsert and isolated backup/restore.
The nine older unrelated local tests are excluded from delivery. C08 was subsequently selected; see its handoff.

C08 was explicitly selected on 2026-10-15 JST. P00/C01 prerequisites and C07
source receipts match the accepted checkout (including the four intentional
C07 P00 export updates). Baseline compatibility passes 81 tests. C08 implements
contracts and synthetic fixtures only; C09 and real catalogue services remain
unselected. See [handoff](handoffs/C08.md).

C08 local acceptance is complete: 2,314 backend tests/82.28% coverage,
274 required compatibility/contract tests and 162 v1 tests plus typecheck/build.
The 100,000-dataset fixture traverses all 200 pages, and 10,398 cross-runtime
cases have zero acceptance/normalization mismatches. All current P00/C01/C07
source hashes, scientific/serving files and unrelated work remain unchanged.
[Contract guide](C08_CATALOGUE_CONTRACT.md), [receipt](evidence/C08/verification.json).
Hosted delivery passes as `6d20a75`: 2,305 backend tests/83.09%
coverage, both frontends (132 legacy/162 v1), 63 actual PostgreSQL cases, idempotent
upsert and isolated backup/restore. The local receipt remains historical;
[delivery evidence](evidence/C08/delivery.json) is separate. C09 is unselected.

C09 readiness is verified: C03/C08 source receipts match, 51 baseline tests and
246 prerequisite regressions pass, and generated contracts are current. See
[C09 readiness audit](C09_READINESS_AUDIT_2026-10-15.md). C09 was subsequently selected and is Complete locally; see [its handoff](handoffs/C09.md) and [snapshot contract](C09_SNAPSHOT_CONTRACT.md). C10 remains unselected.

C09 was explicitly selected on 2026-10-15 JST after readiness checkpoint
`631bb0a`. Implement local immutable snapshots, bounded consistent source capture,
reference/hold/revocation behavior and synthetic transfer verification. No C10,
actual data transfer, legacy store access, cloud/provider or deployment work.
See [handoff](handoffs/C09.md).

C18 local interface acceptance and exact-source hosted delivery are complete. C18 was automatically selected after [98-entry prerequisite readiness](evidence/c18-readiness-2026-10-18/verification.json) and C17 hosted delivery. [Current C18 handoff](handoffs/C18.md).

Historical C19 attempt before CI budget amendment: sourcea38b181 CI reached98percent
without a reported failure before its20-minute job timeout. A verified CI-only
amendment increases that job to30minutes with all13 application/test sources
unchanged; the subsequent exact-source hosted run passes. [Amendment](evidence/C19/ci-budget-amendment/verification.json).
