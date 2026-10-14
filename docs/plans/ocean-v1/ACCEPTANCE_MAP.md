# Requirements and acceptance ownership

Real-service checks below are **planned and not run**. P00 local prototype
checks are recorded in [its handoff](handoffs/P00.md); the user accepted the local
UX direction on 2026-10-14 JST, satisfying P00/G8 only. Document validation in the setup receipt does not satisfy application acceptance. Component specifications define
local checkpoints. C01 shared scope/offline checks are complete; see
[its handoff](handoffs/C01.md). C02 F02/F04/F05 and derived-eligibility software
checks are complete on synthetic inputs; see [its handoff](handoffs/C02.md).
Real affected artifacts remain unchanged and require later regeneration/review.
These checks do not complete the assembled G1 gate. C26 verifies their assembled behavior and C27 records release
readiness. Use the exact dependencies in [COMPONENTS.md](COMPONENTS.md).

C03 local retention/hold ordering is complete, including 12 actual disposable
PostgreSQL cases; see [its handoff](handoffs/C03.md). This establishes the existing
chat-record foundation only. Later snapshot/receipt protection and assembled G2
acceptance remain C09/C17/C21/C26 work; production cleanup was not run.

C04 local authentication responsiveness is complete: deterministic event-driven
concurrency, worker-owned resource lifetimes, permission/attribution parity and
both cancellation styles pass. See [its handoff](handoffs/C04.md). This does not
complete assembled G2 or establish production throughput; shared limiter SQL
remains unchanged and PostgreSQL operational integration is still gated.

## Required behavior

| ID | Requirement and observable acceptance | Implementation owners | Integration gate |
|---|---|---|---|
| R01 | One scope validator rejects incompatible geography, date, taxa/panel and method in exact and synthesis routes; include English/Japanese Hokkaido and shark counterexamples. | C01, C19, C21 | G1 |
| R02 | Reliability tiers require passing checks; top-ten omission is not zero; SST matching respects geography, product, time and resolution. Invalid derived artifacts are corrected or quarantined before exposure. | C02, C10, C11, C13 | G1 |
| R03 | Legal holds, retention and concurrent cleanup preserve protected artifacts; current authorization governs historical snapshots and receipts. | C03, C09, C17, C21 | G2 |
| R04 | Authentication avoids blocking asynchronous requests and preserves roles/session behavior under concurrency. | C04, C14, C20 | G2 |
| R05 | Legacy retrieval uses the correct embedding identity and complete relevant document fields; model truncation cannot become a successful answer. | C05, C06, C19, C21 | G1, G4 |
| R06 | CSV/table downloads are safe for spreadsheet consumers without corrupting legitimate numeric data; all new exports use the shared policy. | C07, C21, C22 | G2 |
| R07 | Five roots and all four source families use canonical identities; aliases and cross-links do not duplicate counts. | C08–C14 | G3 |
| R08 | On a 100,000-object fixture, objects at legacy rank 26 and beyond initial pages are reachable; no top-k cutoff limits catalogue membership. | C08, C14, C16, C19 | G3 |
| R09 | Global and scoped counts cover the complete authorized matching population, report entity/denominator and stay identical when preview size changes. | C08–C14, C19, C21 | G3 |
| R10 | UI and agent list/open/query the same IDs and totals under identical permissions, filters and snapshot; no hidden names or counts leak. | C14, C16, C19 | G2, G3 |
| R11 | Immutable snapshots bind source, publication, classification, relationship and operation versions; frozen adapters match exact-service reference answers. | C09–C14 | G1, G3 |
| R12 | Query readiness is independent of embeddings. Empty, zero, unknown, unavailable, incomplete source, truncated preview and query failure remain distinguishable. | C08–C16, C21 | G3 |
| R13 | CTD casts/measurements, SST products/grids, full metagenome abundance semantics and eDNA protocols/controls/assignments remain scientifically distinct. | C10–C13 | G1 |
| R14 | Physical sample identity, source occurrence and candidate overlap remain distinct. Published result, available workflow and experiment authority cannot be conflated. | C12, C13, C21–C23, C25 | G1, G5 |
| R15 | A separate Context Catalog tab exposes every authorized directory and leaf through tree, listing and inspector; paging/virtualization never hides membership. Deep links and history restore the node and snapshot. | C15, C16 | G3, G6 |
| R16 | Research presents Chat and Workspace, named private investigations, multiple separate chats, resizable desktop panels and narrow-screen alternatives. | C15, C17, C18 | G6 |
| R17 | Browse/filter has no context side effect; Attach supplements, Pin restricts; every run freezes its effective revision. Explicit refresh branches and preserves original evidence. | C09, C16–C20 | G3, G4, G6 |
| R18 | All live Chat actions work: submit, status/events, cancel, clarify and continue; reload/reconnect recovers persisted progress. C18 owns controls/boundary, C20 owns live transport. | C18–C20 | G4, G6 |
| R19 | Typed provider-independent actions use permitted catalogue operations; no unrestricted SQL/admin tools. Malformed actions and hostile source text cannot bypass scope. | C06, C14, C19 | G1, G4 |
| R20 | Deterministic completion accounts for relevant inventory and unresolved work. Enforce 180 active seconds, 12 actions and one repair; retain explicit partial outcomes and linked continuation. | C19, C20 | G4 |
| R21 | Queue retries, crashes, leases, outbox and cancellation preserve committed steps, snapshots and budgets; no claim of exactly-once provider billing. | C17, C20 | G4 |
| R22 | Evidence receipts can be reopened with original parameters/hashes/scope. Only supplied evidence can be cited; generated narrative from other chats is not implicit evidence. | C17, C21 | G1, G4 |
| R23 | Experiment approval binds concrete question/cohort/method/code/input hashes. Revision, tampering or revocation invalidates dispatch. No unpublished inputs or silent sampling. | C22 | G2, G5 |
| R24 | Real Linux/gVisor containment denies network, credentials, host files/sockets and package installation; whole-process-tree termination and resource/output limits are enforced. Mocks cannot prove this. | C23, C24 | G5 |
| R25 | Reproducible experiments retain image/code/input identities, declared seeds, logs and validated outputs. Enforce 1 active/user and 2 globally; experimental labels persist in every surface/export. | C22–C25 | G5, G6 |
| R26 | Light/dark, English/Japanese, keyboard and screen-reader operation, long labels, narrow layouts and useful error/empty/partial states work across all new surfaces. | C15, C16, C18, C25 | G6 |
| R27 | Legacy endpoints/history/links remain on the unchanged legacy site. Reused code retains appropriate regressions; independent v1 flags/rollback preserve its investigations/evidence without shared sessions or automatic history import. | C05, C06, C15, C17, C21, C27 | G7, G9 |
| R28 | Compare actual controller and legacy Chat with matched scope/permission/snapshot. Report numerical parity, factual errors, completion, latency, tool use, tokens and cost separately from citation validity. | C26 | G1, G3, G4 |
| R29 | Independent v1 release preparation has isolated-site/worker configuration, migration rehearsal, flags, rollback triggers and outstanding gates. Preparation neither provisions/deploys nor changes the main domain. | C24, C27 | G7, G9 |
| R30 | Every component can resume from a file-based handoff with revision, completed checkpoints, validation and exact next action; no automatic advancement or fabricated completion. | All components; planning package | G0 |
| R31 | P00 provides working synthetic local journeys, clear preview labels, recoverable actions and recorded user feedback/accepted UX direction before backend implementation. Prototype evidence cannot complete later integration components. | P00; C15, C16, C18, C20, C21, C25 integrate | G8, G6 |
| R32 | V1 has independent serving, project/resource targets, database, storage, credentials, sessions and queues; no legacy runtime access, fallback or main-domain cutover. | C09, C17, C20, C24, C26, C27 | G9 |
| R33 | Approved data enters through explicit one-way copies with authorization/eligibility checks, source/hash manifests, quarantine validation and origin provenance. Withdrawal handling is documented; no silent sync or account/history/credential copy. | C09–C13, C24, C26, C27 | G1, G2, G9 |

## Gate definitions and evidence

| Gate | Required evidence | Owner and limits |
|---|---|---|
| G0 — Planning continuity | 28 specifications (P00 plus C01–C27), acyclic dependencies, 84 independent prompts, status ledger, handoff convention, retained mockup and valid document links. | This setup; validates documents only. |
| G1 — Scientific correctness | Deterministic fixtures and independent expected results for scope, authority, matching, units, counts and numerical parity; zero critical scope/authority violations. | Components + C26. Any production artifact repair/rebuild is a separate authorized operation. |
| G2 — Access and integrity | Cross-owner/role checks, revocation, retention races, export safety and approval tamper cases against actual paths. | Components + C26; local/disposable integration environment. |
| G3 — Complete catalogue | Complete traversal and count reconciliation over all permitted canonical objects; 100,000-object fixture; later-page/rank-26 discovery; UI/agent parity and snapshot stability. | C08/C14/C16/C19 + C26. Record timing/memory; choose measured performance thresholds before claiming performance acceptance. |
| G4 — Durable agent | Fake-provider failure/truncation and deterministic controller cases; transactional crash/retry/cancel/expiry tests; browser reload/resume through live application transport. | C19–C21 + C26. Local fake queue proves application invariants; actual Cloud Tasks integration remains a distinct deployment gate. |
| G5 — Experiment execution | Hash-bound approval, concurrency races, real Linux/gVisor containment evidence, resource limits, safe artifact validation and repeatable numerical fixtures. | C22–C25 + C26. If compatible runtime is unavailable, retain the blocker; do not substitute host Python or mocked containment. |
| G6 — Usable interface | Automated interactions and recorded manual keyboard, responsive, theme and bilingual checks across catalog, Chat/Workspace and approvals; runtime controls actually reach durable APIs. | C15/C16/C18/C25 + C26. The saved concept image is not UI acceptance. |
| G7 — Compatibility and release | Reused-code regressions, v1 migration rehearsal against a disposable database, independent v1 rollback and retained data; legacy site unchanged. | C26/C27. Unrun live checks remain explicit; no deployment or main-domain cutover implied. |
| G8 — Local UX direction | Runnable frontend-v1 with synthetic journeys, honest preview states, responsive/keyboard/bilingual checks and recorded user feedback/acceptance of direction. | P00 only. A local prototype does not prove real backend, scientific, scale or deployment behavior. |
| G9 — Independent site | Isolation matrix for project/resource/config/session/CI targets; no legacy fallback; synthetic approved-data transfer/provenance and withdrawal cases; separate live IAM/network checks. | C09/C17/C20/C24/C26/C27. Local isolation checks cannot establish live isolation. Real resources/transfers need later authorization. |

For each result retain command/scenario, fixture version, code revision, runtime,
expected versus observed behavior and failures/skips. A local mock, real sandbox,
staging cloud service and live model evaluation are different evidence classes.
Paid/provider calls, cloud resource changes and production operations are not
authorized by component prompts. When they are required for a gate, record the
missing evidence and obtain separate explicit authorization for that operation.
Required gates cannot be relabelled optional just to mark a component Complete.
Release preparation may be complete while the runbook explicitly says **not
ready to deploy**; that is not a v1 production acceptance claim.

## Decision traceability

| Decision IDs | Responsible components or planning artifact |
|---|---|
| D01 | C15, C19, C26, C27 |
| D02 | C08, C10, C11, C12, C13, C14 |
| D03, D04, D05, D07 | C22, C23, C25 |
| D06, D10, D16, D26 | C15, C18, C25 |
| D08 | C23, C24 |
| D09, D28 | C19, C20 |
| D11, D13, D25 | C17, C18, C21 |
| D12, D24 | C16, C17, C18, C19 |
| D14, D21 | C09, C10, C11, C12, C17, C22 |
| D15 | C15, C16, C26 |
| D17, D18, D19, D20 | C08–C14, C16, C19 |
| D22, D23 | C01, C06, C14, C19, C21 |
| D27 | C17, C20, C24 |
| D29 | C22, C23, C24, C25 |
| D30 | C05, C06, C15, C17, C21, C26, C27 |
| D31 | C03, C04, C09, C14, C17, C20, C21, C22 |
| D32, D33 | C08, C13, C22, C23, C25, C26 |
| D34, D35 | README, COMPONENTS, STATUS, PROMPTS, handoffs, HUB_PROMPT, SETUP_RECEIPT |
| D36 | SITE_SEPARATION, C09–C13, C17, C20, C24, C26, C27 |
| D37 | P00, UI_UX_BRIEF, component dependencies, C08, C15, C16, C18, C25 |
| D38 | P00, UI_UX_BRIEF, C15, C16, C18, C21, C25, C26 |

No decision in this table is evidence that its implementation exists.
