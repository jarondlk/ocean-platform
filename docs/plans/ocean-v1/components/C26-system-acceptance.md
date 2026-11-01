# C26 — System acceptance and evaluation

**Status:** Complete for local deterministic preparation and source-bound hosted software delivery (2026-11-01 JST); live release acceptance remains not run. **Prerequisites:** P00, C01, C02, C03, C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, C18, C19, C20, C21, C22, C23, C24, C25.

Readiness audited 2026-10-29 JST: **ready to begin local deterministic acceptance preparation**. P00/C01–C25 receipts/current source reconcile and exact-source C25 hosted delivery passes. User selected local implementation on 2026-10-29 JST. Live beta/release acceptance remains gated by hosting/auth, real queue/worker integration, explicit target configuration and real-world validation. [Readiness audit](../C26_READINESS_AUDIT_2026-10-29.md), [handoff](../handoffs/C26.md).

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Establish whether the complete research experience satisfies the accepted architecture using traceable, repeatable acceptance evidence. Evaluate the actual agent controller alongside the catalogue, UI and execution boundaries; retriever metrics alone cannot demonstrate whole-system correctness.

Include integrated synthetic fixtures, regression checks, local failure/permission testing, acceptance reporting and a separately executable live-evaluation protocol. Exclude automatic bug-fixing across predecessor components, deployment, production mutation and paid/live model runs. Route discovered defects to their owning component with a reproducible case.

User-approved scope amendments on 2026-10-29 JST: repair the reproduced C17/C20/C21/C22/C25 retained-experimental-artifact integration (including same-session PostgreSQL resolution and current-authority reopening), and investigate/optimize C14 catalogue materialization after the 100,000-object lab exceeded its predeclared memory budget. These are bounded owning-component repairs, explicitly selected by the user after concrete failed observations. Preserve the original failures and source qualifications; the amendments authorize no live operations or scientific approval.

## Verified entry points and contracts

Inspect [benchmark implementation](../../../../evaluation/benchmark.py), [evaluation tests](../../../../tests/test_evaluation.py), [research Chat tests](../../../../tests/test_research_chat.py), [CI checks](../../../../.github/workflows/tests.yml) and [frontend scripts](../../../../frontend/package.json). Existing metrics and checks provide a baseline; they do not already exercise catalogue-guided research.

Compare legacy Chat and the new controller using identical question, permissions, scope, snapshot and provider configuration. Keep reference numerical answers independent of generated prose. Separate inventory accounting, numerical correctness, unsupported claims and task completion from citation validity. For future authorized live evaluation, retain provider/model versions, timings, tool calls, tokens and cost with the same input manifest; do not infer live quality from mocked responses.

## Prototype, integration and independent-site evidence

Retain P00's user-reviewed journeys, then repeat them through real v1 services.
Prototype screenshots and simulated success cannot satisfy integrated acceptance.
Use the actual frontend-v1 checks in addition to relevant legacy regressions.

Add the full isolation matrix from SITE_SEPARATION: explicit v1 resource targets,
independent database/storage/queues/credentials/sessions, no legacy runtime access
or fallback, and rollback with no legacy change. Verify synthetic approved-data
transfer manifests, rejected imports, provenance retention and the withdrawal
procedure. Actual IAM/network isolation and real transfers remain separate gates.
Legacy/new comparison uses isolated implementations with identical synthetic or
separately authorized copied inputs, never unsolicited production traffic.

## Resumable checkpoints

1. Reconcile all predecessor handoffs and map every master-plan acceptance requirement to a fixture/check and owner. Distinguish passed, failed, blocked and not-run gates; no missing result counts as a pass.
2. Add integrated deterministic catalogue/controller fixtures and scientific adversarial cases. Exercise snapshot rollover, run interruption, retention, owner/role changes and sandbox evidence boundaries.
3. Run authorized local backend/frontend checks and inspect the complete catalogue/research/experiment interfaces. Produce the acceptance matrix, defect list and live-evaluation protocol for C27.

## Future verification and acceptance

Local baseline commands: `python -m pytest tests/ -q --tb=short`, `python scripts/export_chat_scope.py --check`, `npm --prefix frontend test`, `npm --prefix frontend run typecheck` and `npm --prefix frontend run build`. Use isolated test settings and synthetic fixtures; do not point tests at production. Match the repository's current CI checks and record additional integrated-suite commands when created.

Required scenarios include:

- A 100,000-object inventory; relevant rank-26 and later-page targets; every permitted directory/leaf reachable; exact whole-scope totals unaffected by 100/500-row previews.
- Identical human/agent membership, summaries and counts; cross-links counted once; zero, unknown, unavailable and incomplete states distinguished.
- Rejection of incompatible scope; preserved sampling, product, assay/method, identity and scientific-authority qualifications.
- Snapshot consistency, retries, cancellation, continuation, evidence reopening, holds, revocation and no cross-account metadata/count leakage.
- Explicit attach/pin behavior, multi-chat context revisions, catalogue deep links, Back/Forward, reloads, bilingual responsive layouts and keyboard/screen-reader access.
- Proposal approval hashes, actual containment evidence, resource enforcement, reproducible outputs and persistent experimental labels; existing exact workflows/history/citations remain compatible.

Require deterministic numerical parity, complete inventory accounting and zero critical scope/authority violations. Document live/runtime gates still pending; these prevent release promotion. A preparation report may be complete while release acceptance remains pending, and must label that distinction.

## Compatibility, rollback and handoff

Do not change default routing to make tests pass. Retain reproducible failure fixtures and the exact tested code/snapshot versions. Update [status](../STATUS.md) and `handoffs/C26.md` after each checkpoint with commands, results, blockers and gate ownership.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c26). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.


Implementation delivery verified 2026-11-01 JST: original functional source `e0874e0` passes the 1,604-case assembled local run, all 43 preparation rows, all 11 shared-service scenarios, independent numerical comparison, complete 100,000-dataset traversal and 707-request actual browser QA. Accepted source `afe9cb2` passes [all four required hosted jobs](https://github.com/jarondlk/ocean-platform/actions/runs/41175282249): 6,712 backend passes (1 isolated scale + 17 covered integration + 6,694 remaining), 626 explicit skips, 83.64% combined coverage; 318 actual PostgreSQL passes/16 expected capability skips and backup/restore; 1,051 v1/132 legacy frontend tests plus both builds/typechecks/audits.

Only the workflow differs from the original local source: the covered suites are partitioned without dropping cases, the first scheduled diagnostic timer is 0, and the user extended the backend job timeout from 60 to 90 minutes. The eight coverage targets, sysmon core, appended coverage and final 70% gate remain. All 843 non-workflow source paths and 204 browser pins are unchanged. Original native-crash logs and the later 60-minute cancellation remain retained; the exact native-crash cause is unknown.

[Implementation report](../C26_IMPLEMENTATION_REPORT_2026-10-30.md), [delivery receipt](../evidence/C26/delivery.json), [verification](../evidence/C26/verification.json), [workflow-only supersession](../evidence/C26/workflow-supersession-afe9cb2.json), [defect register](../C26_DEFECT_REGISTER_2026-10-30.md). D26-07 remains open P2 for recoverable concurrent-worker automatic first-history latency. No UI deadline was raised. `release_accepted=false`; C24 live gates and real hosting/auth, queue/worker, provider/model, scientific and release checks remain pending. C27 remains Not started, ready for its bounded local prerequisite audit. Scheduler PAUSED.
