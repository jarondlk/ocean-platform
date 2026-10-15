# Implementation status

Updated: 2026-10-15 JST. **P00 and C01–C11 are Complete locally.**
The latest plan adds local UI/UX work first and a fully isolated second GCP site.
P00 is accepted; C01 local validation was explicitly selected and completed on
2026-10-14 JST.
C02 was explicitly selected on 2026-10-14 JST and passed its software/synthetic
checks. C03 passed its local transaction-ordering and actual disposable PostgreSQL
acceptance. C04 now passes concurrent responsiveness, worker-lifetime, security
and cancellation acceptance. C05 passes embedding isolation, metagenome fidelity
and deterministic replacement-history acceptance. C06 passes strict generation/consumer acceptance. C07 passes CSV presentation/consumer acceptance; C08 passes catalogue contract/fixture acceptance; C09 is Complete for local snapshot/capture acceptance; C10 passes frozen CTD/metagenome adapter acceptance; C11 passes frozen SST product/coverage acceptance; C12–C27 remain Not started.
P00 and C01–C11 local work is authorized.
See [P00](handoffs/P00.md), [C01](handoffs/C01.md), [C02](handoffs/C02.md),
[C03](handoffs/C03.md), [C04](handoffs/C04.md), [C05](handoffs/C05.md), [C06](handoffs/C06.md), [C07](handoffs/C07.md), [C08](handoffs/C08.md), [C09](handoffs/C09.md) and [C10](handoffs/C10.md) handoffs for current evidence.

Latest completed implementation: **C11 — SST adapter**. Local acceptance is complete: 966 required tests; full backend 2,829 passed/84 gated PostgreSQL skips, 83.29% coverage. Read [the handoff](handoffs/C11.md), [contract](C11_SST_ADAPTER_CONTRACT.md) and [receipt](evidence/C11/verification.json). Exact-source hosted delivery is pending.

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
| [C12 — eDNA adapter](components/C12-edna-adapter.md) | Not started | None | Not run | Not created |
| [C13 — Analyses statistics metadata relationships](components/C13-scientific-catalogue-sections.md) | Not started | None | Not run | Not created |
| [C14 — Catalogue service and tools](components/C14-catalogue-service-tools.md) | Not started | None | Not run | Not created |
| [C15 — New application shell](components/C15-application-shell.md) | Not started | None | Not run | Not created |
| [C16 — Complete catalogue browser](components/C16-catalogue-browser.md) | Not started | None | Not run | Not created |
| [C17 — Investigation persistence](components/C17-investigation-persistence.md) | Not started | None | Not run | Not created |
| [C18 — Chat and Workspace interface](components/C18-chat-workspace.md) | Not started | None | Not run | Not created |
| [C19 — Agent exploration controller](components/C19-agent-controller.md) | Not started | None | Not run | Not created |
| [C20 — Durable research execution](components/C20-durable-execution.md) | Not started | None | Not run | Not created |
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
