# Implementation status

Updated: 2026-10-14 JST. **P00, C01, C02 and C03 are Complete locally.**
The latest plan adds local UI/UX work first and a fully isolated second GCP site.
P00 is accepted; C01 local validation was explicitly selected and completed on
2026-10-14 JST.
C02 was explicitly selected on 2026-10-14 JST and passed its software/synthetic
checks. C03 passed its local transaction-ordering and actual disposable PostgreSQL
acceptance; C04–C27 remain Not started.
P00, C01, C02 and C03 local work is authorized.
See [P00](handoffs/P00.md), [C01](handoffs/C01.md) and [C02](handoffs/C02.md) handoffs for current evidence.

Recommended next implementation: **C04 — Authentication responsiveness**, after user selection.
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
| [C04 — Authentication responsiveness](components/C04-authentication-responsiveness.md) | Not started | None | Not run | Not created |
| [C05 — Retrieval correctness](components/C05-retrieval-correctness.md) | Not started | None | Not run | Not created |
| [C06 — Model runtime contract](components/C06-model-runtime.md) | Not started | None | Not run | Not created |
| [C07 — Export safety](components/C07-export-safety.md) | Not started | None | Not run | Not created |
| [C08 — Catalogue contracts and fixtures](components/C08-catalogue-contracts.md) | Not started | None | Not run | Not created |
| [C09 — Immutable catalogue snapshots](components/C09-catalogue-snapshots.md) | Not started | None | Not run | Not created |
| [C10 — CTD and metagenome adapters](components/C10-ctd-metagenome-adapters.md) | Not started | None | Not run | Not created |
| [C11 — SST adapter](components/C11-sst-adapter.md) | Not started | None | Not run | Not created |
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
remain historical; no C03–C27 implementation or deployment is implied.

P00 has passed only G8, the local UX direction gate. No code revision has passed
the full v1 acceptance map. See [SETUP_RECEIPT.md](SETUP_RECEIPT.md)
for document validation only, and [ACCEPTANCE_MAP.md](ACCEPTANCE_MAP.md) for future checks.
