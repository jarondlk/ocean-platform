# Beta completion plan — 2026-11-14 JST

State: **In progress; internal beta is accessible; full beta acceptance is open.**
Source checkpoint reviewed: `7002312` on `overhaul`. This plan integrates the
return-to-main-Mac audit and the second Mac's deployment work. It supersedes
the *current-progress descriptions* in the November 1 preparation plans, while
preserving their original requirements and receipts. These milestones organize
the existing C01–C27 work; they do not introduce new numbered components.

## Where the project stands

P00/C01–C26 are complete within their documented software/component boundaries;
C27 is complete for local release preparation. Their completion does not mean
that all services, production execution, scientific assessments or live release
checks have passed. We are in **cloud integration and operational acceptance**.
No defensible single percentage follows from the component count.

| Layer or capability | Actual progress | Remaining beta work |
|---|---|---|
| Architecture and component implementation | Accepted contracts, local/integrated software checks, hosted delivery and release-preparation rehearsals exist | Qualify later integration changes at their own source/image/configuration identities |
| Edge, identity and application shell | Independent beta DNS/TLS, Google login, enrolled admin/internal account, real frontend/API/private SQL; login 200 and protected runtime 401 rechecked November 14 | Final signed-in origin/session/role/isolation matrix and intended beta-user enrollment checks |
| Catalogue and investigations | CTD, metagenome and MUR regional SST plus saved investigations previously accepted live | Reopen current authority/control state; complete whole-scope/UI/export and retention acceptance; resolve eDNA latency/integrity gate |
| Research delivery and evidence | Private controller, Cloud Tasks integration, durable state and evidence wiring installed; deterministic cited answer, cancellation and duplicate/outbox recovery observed | New API rollout, actual Gemini cited answer, persistence/reload, current-image recovery and history/evidence latency acceptance; supervised sweep remains gated |
| New Research API | Source `0f15bbca`, image `7889ef20…`, successful source/SDK image proofs and explicit composed hosted CI | Not deployed; serving/controller still use API `4b24ca90…` |
| Experimental execution | C22/C23/C25 contracts and actual retained Linux test evidence exist | Production admission/start integration, retained port/supervisor and current beta worker qualification are unfinished |
| Operations and release | Independent resources, cost planning and local migration/rollback rehearsals exist | Current live backup/restore, recovery, containment/capacity, alerts/cost, whole-system evaluation and release decision |

[Main-Mac audit](main-mac-return-20261114/audit.json) verifies 180 API and 71
frontend source pins, the candidate build, live serving/controller images, and
79 focused backend cases, focused frontend checks and lint. No new full suite
or signed-in journey was run for that audit. Original normal CI remains failed;
its separate source-bound PostgreSQL run passed 318 cases with 16 explicit skips
and restored 74 tables. The native interpreter crash's cause is still unproven.

The SQL-proxy hold now has an authoritative explanation: the executed
`1d2285ce…` digest is the Linux/amd64 child explicitly named by reviewed OCI
index `f333a9c5…`. Both exact raw hashes are retained in the audit directory.
**The guard has not been changed and rollout has not been cleared.**
The 15 private operator helpers are absent from this Mac's documented storage
locations. Restore them privately against their retained hashes, or reconstruct
and review equivalent tooling. Historical one-shot assumptions and phase
arguments are expired and must not be replayed.

## What “beta finished” means

The next usable-Research milestone is valuable, but full beta completion retains
the planned four source families, Research and experimental workflows. A smaller
release would need an explicit scope decision and documented unavailable
capabilities. No such reduction is assumed here.

Completion requires all of the following on one explicitly identified compatible
candidate:

- Intended beta users can sign in, browse permitted data, save/reopen
  investigations, attach/pin context, run/continue/cancel Research, inspect cited
  evidence, and use approved experiment workflows through the deployed UI.
- Every intended dataset is accounted for as active, quarantined, withdrawn,
  superseded or excluded with a reason. Inventory availability is distinct from
  scientific eligibility. eDNA controls/unresolved identities, SST product and
  coverage gaps, and metagenome units/denominators remain explicit.
- Current authorization applies to live and historical data, answers, artifacts
  and exports. There is no critical scope, authority, numerical or isolation
  violation. A citation check alone cannot establish scientific correctness.
- The candidate's locked application dependencies and deployed container images
  have current security findings triaged, with no unaccepted release-blocking
  vulnerability. A repository default-branch advisory total is not a scan of the
  beta candidate; bind findings and repairs to the actual shipped versions.
- Actual queue, worker, cancellation, crash/restart, backup/restore and rollback
  checks pass at their real resource/material identities. Uncertain worker state
  retains capacity until independent physical proof permits release.
- Every original C26 R01–R33/G0–G9 row and all 20 C27 operational gates have
  current evidence and an explicit outcome. Required missing/failed gates prevent
  full acceptance. Lower-severity findings need an explicit disposition.
- The independent scientific assessment and operator/user release decision are
  recorded by their actual owners. Operational approval to use data/GCP does
  not create scientific approval.
- Source/image/configuration/worker identities, compatible rollback, measured
  cost and recovery behavior, operators and known limitations are recorded in
  a final beta release receipt. Documentation-only progress is not a release.

## Ordered delivery milestones

| Milestone | Deliverable and owning components | Dependencies | Exit evidence |
|---|---|---|---|
| B0 — Resume the exact candidate | Recover/review operator helpers; incorporate verified index→platform-image proof without relaxing image checks; reopen current targets, authority, IAM, queue, secret metadata and ledger | Audit/source pins are available; scoped credentials for each concrete operation | Hash-bound tooling; exact index/child/platform positive and negative checks; current preflight and budget; fresh post-drain global quiescence |
| B1 — Make Research usable | Deploy qualified controller/API increment preserving service settings; complete model→tools→evidence→saved answer; address read latency in C14/C20/C21 and UI | B0 passes; actual model validation remains within refreshed limits | Actual Gemini cited answer; independent expected result; persisted answer/evidence after reload; 15-second signed-in history/evidence gate; new-image cancel, duplicate, retry and revocation checks |
| B2 — Complete data and catalogue journeys | Resolve C12–C14 eDNA bottleneck and integrity checks, register the qualified cohort through C09; finish C16–C18 context/navigation/export journeys across intended data | Current control/CAS authority; new source/image proofs for changed code | Exact cohort manifest and totals; whole-scope versus preview parity; unknown/control/method qualifications; source withdrawal/revocation; current browser latency and integrity checks |
| B3 — Complete production experiments | Amend C22/C25 admission/start integration, build retained execution port/supervisor using C23/C24 boundaries; prepare and qualify bounded isolated beta worker | Accepted approval/input contracts and explicit worker target/material/capacity/cost plan | Actual proposal→approval→reservation→sandbox→validated artifact→independent release; tamper/revocation/cancel/restart tests; all current physical containment and capacity gates |
| B4 — Prove durable operations | Finish supervised outbox lifecycle, observability, retention and live recovery; measure actual scale and cost | Research sweep follows B1 acceptance and budget; worker recovery follows B3 | Independent beta backup and isolated restore; observed RPO/RTO; held evidence and withdrawal preserved; uncertain ACK/crash recovery; alert/pause/drain readbacks |
| B5 — Accept and release beta | Repeat C26 integrated evaluation on the deployed candidate and C27 rollout/rollback rehearsal; obtain actual review and final release decision | B1–B4 and required scientific/operational evidence | Completed 43-row evaluation plus 20-gate overlay, evidence manifest, source-bound CI, signed-in UX acceptance, recovery/rollback observations and final release receipt |

B1 is the immediate user-facing priority. Local eDNA and worker preparation can
proceed independently when their inputs are available; neither may borrow a
pass from the Research milestone. B2 and B3 can overlap after their own readiness
checks. Backup/alert preparation can begin early. These are dependency-based
milestones, not calendar promises; actual model quality and production worker
qualification remain material uncertainties.

### B0/B1: immediate execution sequence

1. Recover the private helpers or reconstruct reviewable equivalents using the
   published hashes/contracts. Verify the source and candidate image again only
   if changed. Correct the exact proxy verification using both raw manifests,
   required `linux/amd64` platform, exact image repository and digest identity;
   reject unpinned substitutions and unrelated child manifests.
2. Use `scripts/gcloud_beta.sh` for its granted scopes. It works for this Mac's
   inspection/build/existing-serving updates. Controller changes, job execution,
   SQL/IAM/secret operations require their own authorized capability; validate
   personal access when actually needed. Do not expand the automation identity
   merely to pass an inspection.
3. Reopen service settings, IAM/secret metadata, exact catalogue control/audit
   references, queue tasks/Scheduler and cost. Inspect uncertain outcomes before
   retrying. Do not repeat completed bootstrap, migration, enrollment, credential,
   grant or data-copy operations.
4. Verify admission drain and the complete old-request timeout envelope; acquire
   fresh global database quiescence. November 11 observer reports are historical.
5. Update the private controller image first, then stage/promote only the serving
   API image under reviewed guards. Preserve frontend, SQL proxy, identities,
   secrets, ingress, scaling, timeouts and other settings. Read back each outcome.
6. Under the refreshed 20-question/¥500 initial validation limit, test one actual
   model question at a time against independent reference results. Verify saved
   answer/citations/reload, repair/partial outcomes, cancellation, continuation,
   duplicate delivery and owner/context changes. Confirm the unchanged 15-second
   history/evidence deadline through the signed-in frontend.
7. Reconcile usage before another question. Enable the supervised runtime sweep
   only after actual answer/recovery/cost acceptance. A manual successful task
   does not demonstrate an unattended outbox lifecycle. Three-hour Codex
   scheduling remains paused; runtime scheduling is a separate capability.

### B2/B3: data and execution limits

eDNA's earlier full-cohort paging took 15.076610 seconds *before* network cost,
failing its 15-second gate. The cache experiment is diagnostic, not accepted
production behavior. Optimize the owning catalogue/materialization path while
retaining request-bound authority checks, closing generation fences and payload
hash verification; qualify concurrent memory/latency before activation.
The prepared 39-source raw cohort has 3,498 occurrences/assays and 349,638
detections; 3,155 classifications are unknown, 343 are negative controls and
physical sample identities remain unresolved. Preserve those historical cohort
facts and verify the exact selected bytes anew before publication. Raw inventory
must not become an eligible association/detection-frequency cohort by relabeling.

CTD, metagenome and MUR SST need final current-candidate journeys and scientific
qualifications, not duplicate imports. Inventory other staged SST/JCOPE and
quarantine inputs explicitly; reconcile them to accepted source/product scope
before deciding to publish or exclude. The user's all-data operational approval
is already recorded; ask only for a genuinely missing scientific/eligibility
decision, rather than requesting that broad approval again.

The production experiment port cannot be supplied by toggling a flag on the
fake-only executor. Bind explicit starts to current owner/site, immutable
proposal/approval, input/code/environment hashes and stable retry identity.
Verify one active experiment per user and two globally against measured host
capacity. Guest network/credentials/host mounts/sockets/package installation
remain denied. Current host boot-image unique ID and disk `sourceImageId`,
rootfs/runtime/init/source hashes, process-tree termination and independent
signed-proof release must pass. The earlier C23 test host receipt is a reference,
not acceptance of a newly integrated beta worker. Keep experimental labels in
UI, evidence and exports.

## Original operational-gate reconciliation

This is a progress overlay on the immutable
[C27 gate inventory](../evidence/C27/release-gates.json). `Partial` means actual
sub-evidence exists, while full applicable acceptance remains open. No original
gate is silently changed from `not_run` to passed by this planning update.

| Original requirement ID | Current evidence/limit | Completion milestone |
|---|---|---|
| `authenticated-beta` | Partial: real enrolled login/shell and protected API; final session/role/origin matrix open | B5 |
| `cloud-queue` | Partial: actual task/controller and manual lifecycle checks; supervised recovery open | B1/B4 |
| `production-worker-port` | Not run on beta production port/supervisor | B3 |
| `iam-network-isolation` | Partial: separate beta targets and scoped grants; full current inherited/network/legacy-denial matrix open | B4/B5 |
| `backup-recovery` | Partial software evidence: real PostgreSQL CI restore; current deployed beta backup/restore/recovery still required | B4 |
| `dns-tls` | Partial full-gate coverage: public TLS/login and protected runtime observed; complete origin/session assessment remains | B5 |
| `real-data-science` | Partial: approved three-family publication; eDNA, independent review and withdrawal assessment open | B2/B5 |
| `live-model-evaluation` | Partial: two real model calls produced partial/repair-budget outcome; matched live evaluation not accepted | B1/B5 |
| `release-rehearsal` | Local rehearsal accepted; current live candidate rehearsal not run | B5 |
| `C24.whole_site_target_and_live_action_authorization` | Partial: project/region/origin and broad operator approval recorded; each remaining concrete worker/recovery action still needs configured scope | B0/B3/B4 |
| `C24.authenticated_v1_host_proxy_and_bootstrap` | Partial: real hosting/bootstrap and enrolled browser journey; final current-candidate matrix open | B5 |
| `C24.real_cloud_tasks_adapter_outbox_and_private_invocation` | Partial: real Research wiring/manual checks; unattended sweep and failure acceptance open | B1/B4 |
| `C24.production_experiment_supervisor_health_and_drain` | Not run on beta production supervisor | B3/B4 |
| `C24.worker_boot_image_unique_id_and_disk_sourceImageId` | Not run for the selected beta worker | B3 |
| `C24.DNS_TLS_Host_OAuth_cookie_and_cross_origin_validation` | Partial: real domain/OAuth and host checks; complete cookie/cross-origin/role matrix open | B5 |
| `C24.inherited_IAM_and_network_legacy_access_denials` | Partial scoped separation evidence; current full negative-access matrix open | B4/B5 |
| `C24.two_simultaneous_sandboxes_and_measured_host_capacity` | Not run on beta worker | B3 |
| `C24.crash_reboot_uncertain_ACK_recovery_and_physical_proof_release` | Historical/local physical evidence retained; production integration checks not run | B3/B4 |
| `C24.independent_backup_restore_retention_budget_and_alert_readbacks` | Partial configuration/cost planning; actual current restore, policy and alert exercises open | B4 |
| `C24.C26_C27_integrated_acceptance_and_release_promotion` | Local component preparation accepted; complete deployed acceptance/promotion not run | B5 |

The full requirement matrix remains
[R01–R33/G0–G9](../evidence/C27/requirement-evidence.json); all 43 IDs must be
carried into B5, including inventory/numerical parity, bilingual scope refusals,
deep-link/Back/Forward/reload behavior, Attach versus Pin, hostile source/model
actions, revocation, continuation and access-safe historical evidence.
Use the [C26 live evaluation protocol](../C26_LIVE_EVALUATION_PROTOCOL.md) for
matched v1 versus isolated legacy-baseline runs under identical scope, logical
publication, permission and provider configuration. Do not alter or send
unsolicited traffic to the legacy production deployment. Record numerical
accuracy, unsupported claims, task completion, citations, latency, tokens and
cost separately. Mobile, English/Japanese, light/dark, keyboard and screen-reader
journeys must use actual services. D26-07 and the later history/evidence failure
remain open until measured resolution or an explicit permitted disposition.

## Cost, review and delivery controls

The beta-only monthly target remains **¥50,000**, with notice before a proposed
change would exceed it; ¥100,000 is the stated upper budget, not a waiver of
notice. The last ¥36,810.84 monthly scenario is a historical estimate, not a
current invoice or a budget for an unmeasured always-on worker. Re-estimate
worker capacity, storage, backup, logs, model usage and recovery operations before
committing their resource shapes. Provider budget alerts are not hard spend caps.

The November 11 known observed/reserved validation total ¥487.460001901 is also
historical and includes reservations, with later drain/observer use unreconciled.
It must not be presented as actual spend or fresh remaining allowance.
Keep initial manual validation at 20 questions/¥500 unless separately amended.

Retain existing selected recovery/retention settings and measure them; identify
only genuinely missing owner decisions. Before final acceptance, name the
scientific assessor, intended beta-user/test-role roster and operational
recovery/withdrawal owner. No need to block independent implementation while
those external reviews are pending; never fabricate their completion.

Deliver one bounded source/configuration increment at a time on `overhaul`:
focused checks, source/image-bound receipts, immutable failures and explicit
supersessions, STATUS and handoff, commit/push, guarded deployment, actual
readback and relevant acceptance. Reuse unchanged evidence. Documentation-only
checkpoints may use `[skip ci]`; runtime changes need their applicable source-bound
checks. There is no need to repeat the entire backend suite for this plan.
Legacy resources/data, original scientific bytes and prior receipts remain
protected. Do not resume the paused Codex automation as part of planning.

**Next action:** execute B0, then B1. Full beta acceptance remains false until
B2–B5 and all applicable original requirements have actual evidence.
