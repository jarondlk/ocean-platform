# Implementation status

Updated: 2026-11-14 JST. **P00 and C01–C26 are Complete within their documented boundaries with source-bound hosted delivery; C27 is Complete for local release preparation after passing disposable rehearsals. Full live release acceptance remains gated.**

**Current beta progress — B1 in progress, 2026-11-14 JST:**

Admission generation38 / `ocean-v1-beta-serving-b1-live-20261114` is now Ready
at100%traffic with just the two Research flags true. Queue remains PAUSED;
no runtime Scheduler or new question yet. Actual authentication/private-origin
checks pass. [Admission receipt](beta/b1-20261114/admission-rollout.json).
One canonical manual-delivery helper is now portable and refuses automatic
retries after retaining a dispatch intent. Actual Gemini acceptance follows.
Latest model admission is held for the requested initial-validation allowance
amendment500→550JPY: refreshed conservative total509.1663JPY includes the full
300JPY model reserve and20JPY forward cloud margin. This is not an actual
invoice overrun. No new question/model call;136focused operator checks/Ruff pass.
[Budget hold](beta/b1-20261114/question04-budget-hold.json). Monthly target50,000JPY
is unchanged, and personal CLI/browser login work.

Serving generation36 / `ocean-v1-beta-serving-b1-provider-20261114` is now
Ready at100%traffic on API7889ef20, after fresh observer and traffic-only CAS
promotion. Controller generation3 is Ready on the same image. Existing signed-in
history loaded within10.931seconds and retained evidence within4.296seconds;
the existing deterministic answer remains readable. Admission remains false,
queue PAUSED and runtime Scheduler absent.121 focused operator tests pass.
[Promotion/UI receipt](beta/b1-20261114/drained-promotion.json),
[one-question oracle](beta/b1-20261114/question04-plan.json),
[current reservation](beta/b1-20261114/before-admission-reservation.json).
Next: fresh observer, staged admission and one actual Gemini question followed
by answer/reload/recovery/cost acceptance. No fourth question submitted yet.

Historical controller/stage checkpoint:

B1 controller image7889ef20 is deployed and Ready at generation3. Serving
generation35 has the same API image staged at zero traffic; 100% traffic remains
on drained revision00021-mgn with admission false. The first writer stopped at
the stage readback because Cloud Run retired the idle revision and retained the
old latestReady pointer. No update was retried. The amended reader now verifies
the exact immutable staged template without claiming runtime startup; actual
new-revision readiness remains required after guarded promotion.116 focused
tests and Ruff pass. [Live stage/amendment](beta/b1-20261114/idle-stage-amendment.json),
[writer preparation](beta/b1-20261114/writer-preparation.json),
[operator boundary](../../../deploy/gcp/beta/b1/README.md).
Runtime source/build/composed CI are unchanged. Fresh quiescence/cost precedes
promotion. Queue stays PAUSED/empty; no Scheduler or fourth question yet.

**Historical B0 completion — 2026-11-14 JST:**

B0 preparation and its dated live preflight passed. The exact deployed read-only
observer/entry wrapper are recovered as immutable source artifacts; a portable
job/execution/report guard now verifies the exact OCI index→Linux/amd64 digest
relationship and all unchanged job settings. All47 focused guard tests and Ruff
pass. No application image/source was changed; 180 API/71 frontend pins and
existing composed hosted CI remain unchanged. Original normal CI remains red.

Fresh personal GCP sign-in, numeric secret metadata/aliases, private task IAM,
SQL metadata, canonical catalogue control and all 22 audit entries pass.
The single observer `…-9grc7` completed at 07:36:12 UTC: 3 terminal runs,2 terminal
answer jobs,0open leases/pending work/uncertain model steps; read-only isolation
and proxy shutdown verified. Its guard proof passed while fresh at 07:37:48 UTC.
Snapshot freshness expires after 180seconds; this is not persistent rollout
clearance. Serving generation34/revision21 and controller generation2/revision2,
API/frontend images, queue PAUSED/0tasks and0Scheduler jobs remain unchanged.

The Console confirms existing¥50,000 beta alerts and¥3,000 Cloud Run cap.
Fresh conservative incremental observed/reserved planning total including the
single observer is¥176.2657, leaving¥323.7343 of the initial¥500 envelope.
This includes worst-selected-rate reserve for all storage sent bytes, not an
invoice. Model usage is still2calls/11,603tokens; no fourth question admitted.
The former¥370 model plus¥20 rollout reserve needs a defensible narrower bound
or documented amendment before B1 paid validation. No budget/cap was changed.

[B0 completion/evidence](beta/b0-20261114/README.md),
[portable tool boundary](../../../deploy/gcp/beta/b0/README.md),
[completion plan](beta/BETA_COMPLETION_PLAN.md).
Next: B1 stage/controller helper recovery or reconstruction/review, current
pre-apply gates and guarded controller→serving API rollout. The original 15-file
private helper set is not claimed recovered; new raw evidence is retained in
owner-only durable storage. Research dispatch/synthesis, scientific/worker/
experiment and release acceptance remain gated. Three-hour scheduling stays PAUSED.

**Historical main-Mac return progress — 2026-11-14 JST:**

The main Mac is synchronized to second-Mac checkpoint `7002312` on `overhaul`,
with unrelated local work preserved. The return audit rechecked live serving
revision `00021-mgn` (generation 34, 100% traffic), controller `00002-mcw`,
candidate build `ec6296cd` and 180 API/71 frontend source pins. Dedicated
`scripts/gcloud_beta.sh` inspection access works here without a new personal
sign-in. Login 200/protected runtime 401, 79 focused backend tests, focused
frontend checks and Ruff pass. No cloud update or signed-in journey was run.

The exact executed SQL-proxy digest is now verified as the Linux/amd64 member
of the reviewed OCI index; both raw manifest hashes are retained. This resolves
the missing registry relationship evidence, **not** the unchanged rollout guard
or the expired database/budget preflight. Fifteen private operator helpers are
absent from this Mac's documented locations; transfer by hash or reconstruct
and review before use. Serving/controller still use API `4b24ca90…`; qualified
API `7889ef20…` remains undeployed, Research dispatch/synthesis are off, and the
paused Codex schedule is unchanged. Original normal CI remains red; the separate
318-case/74-table PostgreSQL acceptance and its unexplained-crash limitation stand.

[Audit and exact image proof](beta/main-mac-return-20261114/audit.json),
[beta completion plan](beta/BETA_COMPLETION_PLAN.md),
[current deployment handoff](handoffs/BETA_DEPLOYMENT.md).
We are in cloud integration/operational acceptance: three live source families
and investigations are available; Research, eDNA, production experiments,
recovery and full release acceptance remain open. The plan retains all 43 C26
rows and 20 C27 gates. Next: B0 fresh scoped preflight/tool recovery, then B1
Research acceptance, followed by B2 data, B3 experiments, B4 operations and B5
integrated release. `release_accepted=false`; scientific approval remains false.

**Historical second Mac checkpoint — 2026-11-14 JST:**

The rollout is held and checkpointed at the operator's request. Fresh cloud
inspection on November 14 requires Google reauthentication; no sign-in or
further cloud mutation was started during wrap-up. All cloud observations
below are last verified November 11, not a current clearance.

The last verified serving state is temporary admission drain
`ocean-v1-beta-serving-00021-mgn`, generation 34, at 100% traffic,
observed 2026-11-11T13:01:35.482886Z. New Research dispatch and synthesis
admission flags are false. History/cancellation flags, frontend `7fe5e134` /
`be709b49…`, startup03 API `9969feb2` / `4b24ca90…` and all other writable
settings are preserved. Private controller `00002-mcw` still uses API
`4b24ca90…`; the qualified new API has not been deployed.
[Verified drain](beta/research-20261109/provider-amendment06/drain.json),
[current/prospective images](beta/research-20261109/provider-amendment06/images.json),
[effective hold and resume order](beta/research-20261109/provider-amendment06/rollout-hold.json).

Two aggregate-only read-only observer executions succeeded after the full
60-second old-request envelope: `kzm8g` at 13:06 UTC and `fpdhd` at 13:12 UTC
on November 11. Both found 3 terminal runs, 2 terminal answer jobs, no active
leases, no pending outbox work and no uncertain model steps; proxy shutdown
was verified. These snapshots have expired. The controller dry-run guard
rejected the executed proxy digest `1d2285ce…` against reviewed digest
`f333a9c5…`; their registry manifest relationship is unverified. The exact
guard remains intact. No controller intent/PUT/apply or new API serving
stage/promotion occurred.
[Completed observer and exact mismatch](beta/research-20261109/provider-amendment06/observer-completed.json).

Source `0f15bbcae3ad73ed76ddb32dd57b3a03dbedb49f` combines the beta-only
Gemini wire `const`→singleton-`enum` correction and bounded authority-read
scopes for retained answer/evidence reads. The original logical schemas,
strict host parsing, historical replay fingerprints, fresh authorization and
closing generation fences remain intact; no deadline was increased.
Tokyo [build `ec6296cd-55ea-42ec-a50a-552364f2a62c`](beta/research-20261109/provider-amendment06/build.json)
passed all four steps in 40.823529845 seconds and produced immutable API digest
`7889ef206cb34008e5a5806ab8bd0ebff486501e53160862e94bfd12b8d875f8`.
Both actual container proofs ran nonroot, network-disabled and read-only:
source/activation/role checks and the frozen SDK's real controller/synthesis
wire checks. The finite [180-source manifest](beta/research-20261109/provider-amendment06/production-source-manifest.json)
and 23-file context contain no original scientific payload or credential values.
Two earlier submissions created no builds: local staging-bucket parsing failed,
then the API rejected a proof argument over 10,000 bytes. The accepted build
splits that proof into two steps, maximum argument 6,462 bytes; only the label
step uses documented literal `$$`→`$` normalization. Their failures are retained.
[Read-scope verification](beta/research-20261109/provider-amendment06/read-scopes-verification.json),
[accepted build configuration](beta/research-20261109/provider-amendment06/cloudbuild.json).

[Normal CI 42941802734](https://github.com/jarondlk/ocean-platform/actions/runs/42941802734)
on source `0f15bbca` passed backend and all three frontend jobs. Backend evidence
is 1 scale gate, 17 shared integration cases and 7,270 remaining passes,
627 explicit skips and 83.89% coverage. Its PostgreSQL job repeated exit139
in the retained native artifact case before backup/restore. The failure remains
explicit and its cause unproven. [Isolated diagnostic 43020625782](https://github.com/jarondlk/ocean-platform/actions/runs/43020625782)
on head `41fda4d` passed both focused 120-second faulthandler and disabled-timer
variants. The full PostgreSQL test groups then passed all 318 cases with
16 explicit skips and actual PostgreSQL16.15 backup/restore of 74 tables,
including isolated restore cleanup. Successful unchanged backend/frontend
evidence is reused. This is explicit source-bound composed acceptance; the
original normal workflow remains red and the exact interpreter cause is unproven.
The checkpoint workflow change sets only this native group's scheduled diagnostic
timer to its default zero; fatal handling, every test and the 45-minute job bound
remain unchanged.
[Current composed CI receipt](beta/research-20261109/provider-amendment06/ci.json),
[exact one-scalar workflow proof](beta/research-20261109/provider-amendment06/workflow-supersession.json).
The earlier [318-case / 16-skip / 74-table restore proof](beta/research-20261109/startup-amendment03/ci.json)
belongs to the currently deployed `9969feb2` API, not acceptance of this new source.

[Applied cloud prerequisites](beta/research-20261109/startup-amendment03/cloud-prerequisites.json)
last verified scoped IAM, successful one-shot credential/grant jobs, enabled
numeric controller-secret version1 and temporary-grant cleanup. They were not
retried. Exact activation `4843e61b95c0c0af27079e669d9c661556a362fef3a4c17ce6a30ebe959a7694`
is published at generation 1794232040589985. The November 11 private controller
readback permits only the task-invoker IAM identity; queue readback is PAUSED
with 0 tasks and no runtime Scheduler. Reopen all current settings, IAM,
secret metadata, catalogue control references/audits, tasks and budget before
any write. Resolve the proxy digest proof, then obtain fresh global quiescence
after verifying drain and the preserved timeout envelope. Preserve every other
service setting during API-only rollout. Historical prepared observer details
are in [preflight.json](beta/research-20261109/provider-amendment06/preflight.json);
the completed executions and hold above supersede its preparation-only state.

Earlier live checks passed deterministic count with a native cited answer and
0 model calls, queued cancellation, terminal duplicate delivery and outbox
recovery. Actual question03 remains partial/`repair_budget` after 143 seconds
and two STOP responses; its saved native partial answer used 0 synthesis calls.
Read-only diagnostics verified valid lookup target/fact_ids but invalid action
kind strings; this proves the structural mismatch, not a provider cause.
The actual Gemini-backed cited-answer, persistence/reload and 15-second signed-in
history/evidence gates remain open. Frontend05 last measured answer-list at
2.473 seconds followed by evidence/list at 13.907 seconds. The qualified
read-scope change still requires deployed latency acceptance.
[History failure](beta/research-20261109/provider-amendment06/history-frontend05-failure.json),
[closed-model usage](beta/research-20261109/startup-amendment03/question03-model-cost-reconciled.json).

The historical [November 11, 21:27 JST ledger](beta/research-20261109/secondary-mac-continuation/cost-refresh-20261111-evening/validation-ledger.json)
records ¥95.010771902 observed plus ancillary reserve; model usage remains
2 calls, 10,599 input / 11,603 total tokens including thoughts, estimated
¥3.706505842. Replacing only the finished build's 600-second reserve with
its one-minute planning allowance of ¥0.949229999 gives
[known observed/reserved total ¥487.460001901](beta/research-20261109/provider-amendment06/candidate-budget-after-build.json),
leaving ¥12.539998099 outside the retained ¥370 model, ¥1.50 observer,
¥20 UI/rollout and already included ¥5 ancillary reserves. Post-ledger cloud
usage from the drain and two observers is not fully reconciled; this is a
stale planning reservation, not actual current spend. Refresh before any further
model question or recurring sweep. No fourth question was admitted.
The unchanged initial limit is 20 questions / ¥500. The [bounded monthly scenario](beta/research-20261109/secondary-mac-continuation/cost-refresh-20261111-evening/monthly-scenario.json)
is ¥36,810.84 including contingency, within the ¥50,000 target and ¥100,000
upper budget; these are planning estimates, not invoices or provider spend caps.

The recurring outbox sweep remains gated on actual model/citation/reload and
new-image live cost acceptance. Three-hour Codex scheduling stays PAUSED.
Scientific approval remains false. Original scientific bytes, immutable receipts
and the separate legacy, eDNA/ANEMONE, experiments and worker gates are preserved.

Reviewed helpers and their tests are retained in durable private storage,
with [hashes and replay restrictions](beta/research-20261109/provider-amendment06/retained-helpers.json).
Saved phase arguments and quiescence proofs are expired. The historical
one-shot refresh helper expects an obsolete execution count and must not be
replayed. Auxiliary diagnostic branch `codex/postgres-reopen-20261111` is retained.

**Historical checkpoints below:** These dated records preserve the sequence of
work. Their Research-off/revision17, empty-secret and pending PostgreSQL-retry
statements describe earlier states; effective pins and open gates are above.

**Secondary Mac continuation (2026-11-09 JST):** The clean receiving checkout
was fast-forwarded from `ad0c313` to the fetched `overhaul` checkpoint `4f4b616`;
no local work was discarded. All 35 scientific archive members and the manifest
match the supplied exact hashes and are restored in durable private storage
outside Git. The 31 files of older unrelated local work are preserved separately
for review, without applying them. Replacement activation `4843e61b…` is verified.
Fresh personal Google CLI sign-in and GitHub CLI sign-in succeeded on this Mac.
Fresh cloud reads retain revision `00017-kvz`, an empty PAUSED queue, zero
controller secret versions and no Research activation writes. The single failed
PostgreSQL job is being retried in run `42594709784`; successful backend and
frontend evidence is reused, and actual backup/restore acceptance remains open.
The refreshed bounded monthly scenario is ¥36,480.84 including contingency;
runtime sweep activation still requires live timing and budget evidence.
The user explicitly authorized the documented beta Research activation scope;
execution remains conditional on its CI, fresh-state and live acceptance gates.
[Continuation receipts](beta/research-20261109/secondary-mac-continuation/),
[current handoff](handoffs/BETA_DEPLOYMENT.md). Three-hour scheduling stays PAUSED.

**Portable checkpoint (2026-11-09 JST):** The user is moving to another Mac.
Private scientific inputs were recovered from pinned existing GCS objects for
an AirDrop folder, and the missing unpublished Research activation was
intentionally superseded by metadata hash `4843e61b…`. Portable API build
`f5d0d58d` passes. Full backend and all three frontend jobs pass on source
`3cdecc0`; the PostgreSQL job requires retry after an exit139 native artifact
test crash, and its final backup/restore gate is still open. The Desktop
folder's README and complete prompt carry the exact continuation.
[Current handoff](handoffs/BETA_DEPLOYMENT.md).

**Research compatibility amendment (2026-11-09 JST):** The Gemini request now
omits deprecated sampling configuration. All 67 focused Research checks and
Ruff pass, including SDK serialization against mock HTTP transport. Personal
GCP login is restored; current queue, private SQL and control-only storage
permissions were read back. The replacement API image and offline SDK wire
check pass. Full CI exposed test/lint mismatches that now pass locally; fresh
hosted follow-up is pending.
[Amendment](beta/research-20261109/README.md#compatibility-amendment).

**Research preparation checkpoint (2026-11-09 JST):** The user prioritized
Research questions and chose Gemini through Vertex AI. Four pinned images pass
build/image checks; disposable PostgreSQL16 verifies credential creation,
restricted grants and a saved cited-answer journey with synthetic data and
provider transport. [Activation review](beta/research-20261109/README.md) includes
the exact private controller, job, IAM, queue and runtime recovery proposals.
Research is not live: revision00017-kvz remains at100% traffic, model execution
off, Research queue PAUSED. New cloud scopes await specific activation approval.
Three-hour scheduling stays PAUSED; no legacy or scientific-data change.

**Live catalogue checkpoint (2026-11-05 JST):** Authenticated CTD, metagenome,
MUR regional SST and saved investigations are live on
`ocean-v1-beta-serving-00017-kvz` at 100% traffic. The latest increment removes
duplicate catalogue requests and repeated authority reads within an operation,
while preserving fresh access checks and payload verification. Initial discovery
still takes several seconds. ANEMONE/eDNA remains gated on its separate latency
and integrity acceptance; model/worker execution remains disabled. The three-hour
schedule remains paused. See the [current deployment handoff](handoffs/BETA_DEPLOYMENT.md)
and [latency receipt](beta/context-20261103/request-latency-20261105.md).
The latest plan adds local UI/UX work first and a fully isolated second GCP site.
P00 is accepted; C01 local validation was explicitly selected and completed on
2026-10-14 JST.
C02 was explicitly selected on 2026-10-14 JST and passed its software/synthetic
checks. C03 passed its local transaction-ordering and actual disposable PostgreSQL
acceptance. C04 now passes concurrent responsiveness, worker-lifetime, security
and cancellation acceptance. C05 passes embedding isolation, metagenome fidelity
and deterministic replacement-history acceptance. C06 passes strict generation/consumer acceptance. C07 passes CSV presentation/consumer acceptance; C08 passes catalogue contract/fixture acceptance; C09 is Complete for local snapshot/capture acceptance; C10 passes frozen CTD/metagenome adapter acceptance; C11 passes frozen SST product/coverage acceptance; C12 passes frozen canonical eDNA adapter acceptance; C13 passes scientific catalogue acceptance; C14 passes authenticated catalogue service acceptance; C15 passes local application-shell acceptance; C16 passes local catalogue-browser acceptance; C17 passes local investigation-persistence acceptance; C18 passes local interface acceptance and hosted delivery; C19 passes local controller acceptance and hosted delivery; C20 passes amended local acceptance and hosted delivery; C21 passes local acceptance and exact-source hosted delivery; C22 passes local acceptance and exact-source hosted delivery; C23 passes actual retained Linux/signature/release acceptance and exact-source hosted delivery; C24 passes offline configuration acceptance and exact-source hosted delivery; C25 local service/UI acceptance and exact-source hosted delivery are Complete; C26 local deterministic preparation and source-bound hosted software delivery are Complete; release acceptance remains not run. C27 local release preparation has subsequently completed; live release remains gated.
P00 and C01–C13 local work is authorized; the user also authorizes subsequent CXX local implementation after each readiness audit passes.
See [P00](handoffs/P00.md), [C01](handoffs/C01.md), [C02](handoffs/C02.md),
[C03](handoffs/C03.md), [C04](handoffs/C04.md), [C05](handoffs/C05.md), [C06](handoffs/C06.md), [C07](handoffs/C07.md), [C08](handoffs/C08.md), [C09](handoffs/C09.md) and [C10](handoffs/C10.md) handoffs for current evidence.

Current C23 delivery (Oct28 JST): **Complete.** Both actual retained synthetic
C22 approval -> reservation -> Linux scientific execution -> physical termination
signature -> independent capacity release cases pass. Actual owner suspension
after terminal denies publication while cleanup/release succeed. All 167 raw
worker members and independent DB snapshots pass full chain/wrapper/signature/
material/output/ledger audit; numeric pair agrees at 1e-12 and preserves int64.
[Completion](evidence/C23/completion-20261028.json). Accepted source f6f823b passes
[all four hosted jobs 40652395233](https://github.com/jarondlk/ocean-platform/actions/runs/40652395233):
6481 backend/622 gated skips/83.34%,315 actual PostgreSQL/16 expected
journal-host skips,930 v1/132 legacy frontend, both builds/typechecks/audits,
generated contracts and backup/restore. Full supported-runtime local/native and
actual Linux receipts remain distinct from hosted SQLite-capability skips.
All 236 actual worker source pins equal hosted/current source. VM, both private
PostgreSQL clusters and reverse tunnel are verified stopped; synthetic schemas/
roles cleared after verified export. No legacy/real-data/scientific-approval or
production-dispatch claim. C24 is ready for its configuration-only prerequisite
audit and is Not started. Scheduling stays PAUSED. [Handoff](handoffs/C23.md).

C24 preparation (2026-10-28 JST): the user proposed
`https://beta.oceaninfobio.com` for the independent overhaul site. The read-only
readiness audit reconciles 169 C20 source entries (19 intentional accepted
supersessions) and 236 C23 worker entries, with 370 distinct current source paths
matching accepted `f6f823b`. All 5,006 prior tracked evidence files and 42 unrelated
paths are preserved. [Readiness and development plan](C24_READINESS_AUDIT_2026-10-28.md)
is ready; implementation remains Not started. Independent session/OAuth/origin
checks, explicit v1 resources and offline renderer/runbook are planned. Real
auth hosting, Cloud Tasks adapter and live beta gates remain explicit. No DNS,
GCP or application-runtime change occurred. [C24 handoff](handoffs/C24.md).

Current C24 delivery (2026-10-28 JST): **Complete for offline configuration and
operator preparation.** Source `eeec2e1` passes [all four required hosted jobs](https://github.com/jarondlk/ocean-platform/actions/runs/40663077852):
6601 backend/622 gated skips/83.34% coverage, 315 actual PostgreSQL,
930 v1/132 legacy frontend, builds/typechecks/audits/generated contracts and
backup/restore. The 160 scoped local cases, Ruff, schema/example checks and
independent software review pass. All 15 C24 source/config/docs files match the
accepted hosted source; 370 prerequisite sources, original evidence and 42
unrelated paths are preserved. [Delivery](evidence/C24/delivery.json).
The beta origin is a proposed configuration target. No DNS/cloud/OAuth/provider
validation, live adapter/deployment or data action occurred. Actual host/auth,
Cloud Tasks/outbox and supervisor implementations plus all live acceptance gates
remain pending. Production dispatch disabled; scheduler PAUSED. C25 local service/UI delivery is now Complete; see the current checkpoint below.
[Configuration](../../../deploy/gcp-v1/README.md), [handoff](handoffs/C24.md).

Current C25 delivery (2026-10-29 JST): **Complete for local service/UI acceptance and exact-source hosted software delivery.** Source `d882532` passes [all four required hosted jobs](https://github.com/jarondlk/ocean-platform/actions/runs/40799302862):6628 backend/623 gated skips/83.38% coverage;316 actual PostgreSQL;1051 v1/132 legacy frontend plus builds/typechecks/audits/generated contracts and native backup/restore. Proposal review/revision/exact approval, explicit durable execution projections, cancellation intent, validated outputs, scope-bearing bundles and C17 attachment are integrated. Historical execution survives a newer proposal-head token without weakening revision/hash/state checks. All354 implementation pins match accepted source;42 unrelated paths and original evidence/physical-source qualifications are preserved. Production start remains false and no implicit production port exists. No GCP/DNS/deployment/provider/model/real-data action occurred. C26 local preparation and hosted delivery subsequently completed; live hosting/auth, queue/worker/isolation and release gates remain separate. Scheduler PAUSED. [Handoff](handoffs/C25.md), [delivery](evidence/C25/delivery.json).

Historical C26 readiness (2026-10-29 JST): **ready to begin local deterministic acceptance preparation; implementation was then Not started.** All 26 prerequisites reconcile 2,604 source entries/819 current paths with accepted C25 software `d882532`; 70 intentional superseded paths, original receipts and 42 protected unrelated paths are accounted for. C25's four required hosted jobs are green and unchanged suites are reused. The R01–R33/G0–G9 integrated matrix/scenarios and live protocol are next implementation work. Live hosting/auth, queue/worker integration, target configuration and 11 C24 live gates remain open; no GCP sign-in is needed for the local scope. Scheduler PAUSED. [Audit](C26_READINESS_AUDIT_2026-10-29.md), [handoff](handoffs/C26.md).

Original local implementation checkpoint: **C23 — Isolated Python execution preparation**. All393 scoped cases pass (292 new and101 existing regressions), Ruff passes, all17 new source/recipe/test files remain steady and946 prior source/1334 prior evidence files are preserved. Strict C22 byte/hash verification, non-executing supervisor, safe staging/output validation and fixed profile/offline image preparation are implemented. C23 remains In progress: actual runtime containment, durable integration, safe extraction and numerical acceptance remain pending. [Handoff](handoffs/C23.md), [original local checkpoint](evidence/C23/checkpoint.json).

**C23 preparation hosted checks now pass:** source `b8e929e`, run39578854643,
5556 backend/275 gated skips/86.94% coverage,275 actual PostgreSQL,930 v1/132
legacy tests and all four required jobs. [Hosted receipt](evidence/C23/hosted-preparation.json).
On2026-10-24 the authorized isolated project `ocean-v1-c23-20261024` and one
Linux/gVisor worker were created using the existing billing account. The pinned
scientific image was built offline and all22 packages verified. The worker had
a two-hour automatic STOP deadline. Authentication was restored onOct25; the
worker was verified stopped before restarting the same instance at18:04 JST.
The new actual STOP deadline is20:04 JST;24 original evidence files were exported.
The user authorized required
C23 spending using existing billing; a new budget amount is not a missing user
decision. [Worker record](C23_GCP_TEST_WORKER_PLAN.md).

Source `816c8c9` fixes the Next.js production advisories and passes all four
required hosted jobs in [run40070175545](https://github.com/jarondlk/ocean-platform/actions/runs/40070175545).
[Hosted dependency receipt](evidence/C23/dependency-hosted.json). New durable
journal, trusted guest init, real adapter and operator acceptance harness pass
388 combined local cases, Ruff and shell syntax checks on unchanged source;
independent reviews and the mount-recovery amendment are retained in
[the new receipt](evidence/C23/operator-local-20261025-amendment01/verification.json).
All1334 prior evidence paths remain unchanged; four dependency supersessions and
the preserved preexisting deployment-template edit are explicitly recorded.
No actual containment or numerical acceptance
is claimed, and C22 dispatch/release remains gated. Scheduled continuation stays PAUSED.

Previous delivered implementation: **C22 — Experiment proposals and frozen exports**. Source66b4106 is committed/pushed; [exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39539257759) passes5264 backend/275 gated skips/86.70% coverage,275 actual PostgreSQL cases,930 v1/132 legacy tests, both builds/typechecks/audits, generated contracts and backup/restore. [Delivery receipt](evidence/C22/delivery.json). C23 readiness followed that pushed delivery metadata checkpoint; its completed delivery is recorded above.

Previous delivered implementation: **C19 — Agent exploration controller**. Source4618188 is committed/pushed; [exact-source hosted CI](https://github.com/jarondlk/ocean-platform/actions/runs/39154765984) passes:4561 backend/187 gated skips/86.08%,187 actual PostgreSQL,673 v1/132 legacy frontend, both builds/typechecks/audits, generated checks, migration/idempotence and isolated backup/restore. [Handoff](handoffs/C19.md), [contract](C19_AGENT_CONTROLLER_CONTRACT.md), [delivery receipt](evidence/C19/delivery.json). C20 readiness follows delivery.

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

Current C26 delivery (2026-11-01 JST): **Complete for local deterministic preparation and source-bound hosted software delivery.** Original functional source `e0874e0` passes 1,604 local tests, all 43 R01–R33/G0–G9 preparation rows, all 11 actual shared-service scenarios, matched controller comparison and the complete 100,000-dataset traversal. Browser QA records 707 requests/204 unchanged pins and passing functional journeys, with open P2 D26-07 for concurrent-worker automatic first-history latency and explicit reload recovery. Accepted source `afe9cb2` passes [all four required hosted jobs](https://github.com/jarondlk/ocean-platform/actions/runs/41175282249): 6,712 backend passes (1 isolated scale + 17 integration + 6,694 remaining), 626 explicit skips, 83.64% combined coverage; 318 actual PostgreSQL cases/16 expected capability skips plus backup/restore; 1,051 v1/132 legacy frontend tests plus builds/typechecks/audits. The user extended only the backend job timeout from 60 to 90 minutes after the prior 60-minute cancellation. The workflow-only overlay preserves all 843 non-workflow source paths, original functional/browser identities, 5,141 original receipts and 42 protected paths. Prior exit-139 logs remain retained and their exact cause is unknown. `release_accepted=false`; all live gates remain explicit. Scheduler PAUSED; C27 local preparation subsequently completed, with live release gates retained. [Report](C26_IMPLEMENTATION_REPORT_2026-10-30.md), [delivery](evidence/C26/delivery.json), [defects](C26_DEFECT_REGISTER_2026-10-30.md), [handoff](handoffs/C26.md).

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
| [C20 — Durable research execution](components/C20-durable-execution.md) | Complete | Original checkpoints plus pagination amendment; sourcea149239 hosted delivery passes | Local 4847 backend/231 skips/85.64%, 104 actual PG, 805 v1; hosted 4838 backend/231 actual PG/805 v1/132 legacy | [C20](handoffs/C20.md) |
| [C21 — Evidence and answer synthesis](components/C21-evidence-synthesis.md) | Complete | Source567684b exact-source hosted delivery passes; original receipts and workflow-only amendment retained | Hosted5031 backend/254 gated skips/86.48%;254 actual PG;930 v1/132 legacy, builds/typechecks/audits/generated contracts and backup/restore pass | [C21](handoffs/C21.md) |
| [C22 — Experiment proposals and frozen exports](components/C22-experiment-proposals.md) | Complete | Source66b4106 exact-source hosted CI39539257759 and delivery receipt pass |5273 backend/275 gated skips/86.14%;148 actual PG, independent reviews, strict nine-action HTTP; original receipts/qualifications retained | [C22](handoffs/C22.md) |
| [C23 — Isolated Python execution](components/C23-python-sandbox.md) | Complete | Both actual retained Linux cases and raw audit pass; f6f823b hosted green: 6481 backend, 315 PostgreSQL, 930 v1, 132 legacy | Owner suspension denies publication; physical proofs release capacity; resources stopped. Unsupported crash/reboot/queued cases retain capacity; scientific approval and production dispatch remain separate | [C23](handoffs/C23.md) |
| [C24 — Isolated GCP site and worker configuration](components/C24-gcp-worker-configuration.md) | Complete | Independent offline schema/renderer/templates, isolation matrix and operator runbook | 160 scoped local cases; eeec2e1 all four hosted jobs pass; provider/live deployment gates remain closed | [C24](handoffs/C24.md) |
| [C25 — Experimental Workspace interface](components/C25-experimental-workspace.md) | Complete | d882532 exact-source hosted delivery; local review/progress/results and historical-read acceptance | 6628 backend/623 skips/83.38%;316 actual PG;1051 v1/132 legacy;354 source pins; live gates explicit | [C25](handoffs/C25.md) |
| [C26 — System acceptance and evaluation](components/C26-system-acceptance.md) | Complete | Local preparation and source-bound hosted delivery; release remains gated | 1,604 local tests; 43 preparation rows; 100k inventory; 707 browser requests; hosted 6,712 backend/83.64%, 318 PostgreSQL, 1,051 v1/132 legacy frontend; open P2 disclosed | [C26](handoffs/C26.md) |
| [C27 — Release preparation and rollback](components/C27-release-readiness.md) | Complete | Local release package, exact requirement/gate manifest and disposable rehearsals; not ready to deploy | 20 native migration checks;58table hashes preserved;11targeted+5baseline cases;844accepted sources/5,368prior receipts/42protected paths;20operational gates+P2remain | [C27](handoffs/C27.md) |

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

Scheduled continuation is PAUSED at the user’s request on2026-10-21 JST. C23 was later manually selected after readiness; the user confirmed no existing Linux/gVisor host and real execution must remain gated.

On2026-10-23, the user authorized GCP setup for C23. This supersedes the earlier
no-provisioning authorization boundary for the isolated test worker; original
receipts remain historical. It does not resume the scheduler or pass any real
runtime/scientific gate. Working sign-in, target/billing and spending limits are
required configuration before provisioning; see the worker plan above.


Historical C27 entry checkpoint (2026-11-01 JST): readiness passes against C26 closure `a69eb57` / accepted software `afe9cb2`: 844 source paths, 18 C26 proof hashes, 5,368 prior receipt files, 42 protected paths and actual single migration head `20261027_0021`. User selected implementation. Local release manifest/operator/transfer runbooks and disposable migration/history/drain/rollback rehearsals are In progress. The 5 baseline migration/template checks pass; the unsupported full-base offline SQL export is preserved as a historical reflection limitation, with supported exact spans/native upgrades under verification. All 20 operational gates and open P2 D26-07 remain; no deployment, cloud/provider/real-data action or tag/release publication. Scheduler PAUSED. [Readiness](C27_READINESS_AUDIT_2026-11-01.md), [release package](C27_RELEASE_PREPARATION.md), [handoff](handoffs/C27.md).


Current C27 delivery (2026-11-01 JST): **Complete for local release preparation; not ready to deploy.** The `v1.0.0-rc.1` document label binds accepted runtime `afe9cb2` and C26hostedCI41175282249 without a tag/image/release. Exact43masterrows/10local criteria/20unchanged pending operational gates, independenttargetworksheet, flags and operator/transfer/recovery runbooks are assembled. NativePostgreSQL20checks pass with schema/history preservation, controlled failure/retry and refused populated downgrade; supportedoffline0013/0016spans are qualified, fullbaseoffline reflection failure retained. Actual shared-stack dispatchdrain/full-off/restore/cancel/ACKloss checks preserve58table hashes;11targeted and5baseline tests pass. All844accepted source paths,5,368prior receipts and42protected paths remain unchanged. All90package artifacts verify; source-bound C26runtimeCI is reused rather than rerun for operator/evidence-only changes. OpenP2 D26-07 and all20operational gates remain. SchedulerPAUSED; no cloud/provider/real-data/deployment/tag/publication action. No further numbered component starts. [Release package](C27_RELEASE_PREPARATION.md), [verification](evidence/C27/verification.json), [handoff](handoffs/C27.md).


Beta follow-on preparation (2026-11-01 JST): **offline preparation complete; runtime implementation/cloud setup not started.** User will sign in later. Actual host, research delivery/outbox and experiment admission/port/supervisor gaps are mapped to ordered checkpoints. Separate cloud worksheet retains67pending inputs and8proposed region/names; no live values inferred.21inspected source pins, all844accepted runtime/configuration paths and90C27artifacts remain unchanged. All20operational gates and P2 D26-07 remain. No GCP/login/deployment/data/provider action; schedulerPAUSED. [Preparation](beta/PREPARATION.md), [cloud plan](beta/CLOUD_PLAN.md), [handoff](handoffs/BETA_PREPARATION.md).


Current beta deployment continuation (2026-11-02 JST): **isolated cloud foundation verified; authenticated host/API software locally accepted; public beta not deployed.** Independent Tokyo project `ocean-v1-beta-20261101`, beta-only ¥50,000 all-service alert and ¥3,000 Cloud Run cap are saved. Twenty empty registry/network/identity/storage/secret/paused-queue operations verify; the unused default Compute Editor grant was removed only in beta. No paid runtime/image/DNS/secret value/data/dispatch is created yet. Backend35+9 native checks, host50+1 actual HTTP, static1051regressions/typecheck/build/audit pass.841 accepted paths remain unchanged;3 intentional supersessions and36 additive app files are audited;5368 prior evidence/90 C27 artifacts/42 protected paths preserved. Fresh five-job CI is pending for the new app checkpoint. Container packaging, actual JPY quotes, OAuth/account enrollment and private DB/ingress/provider wiring remain. All20 live gates andP2 D26-07 stay open; scheduler PAUSED. [Current handoff](handoffs/BETA_DEPLOYMENT.md). Earlier offline-preparation/no-cloud entries describe their historical checkpoints.


Beta cloud progress (2026-11-02 JST): app50566b7 and packaging7924a28 pushed; current CI41322838746 has authenticated-host, both frontend and PostgreSQL jobs green, backend remaining checks pending. Two immutable Linux images built successfully. Private Tokyo SQL and independent empty database are created with planned settings verified; migrations/roles/secrets/accounts remain pending. Initial image smoke failed; a confirmed test-harness assertion defect was corrected and a diagnostic run is in progress, preserving the first failure. Actual bounded JPY quote is ¥35,604.05/31days with reserve; no public beta, Cloud Run service, worker, LB/IP, DNS change or data transfer exists yet. OAuth console work awaits an unlocked Mac. [Current handoff](handoffs/BETA_DEPLOYMENT.md).


Beta checkpoint (2026-11-02 09:01JST): **all five source-bound host/API CI jobs pass** on50566b7 (6747backend/626explicit skips/83.67%,318PostgreSQL,132legacy/1051prototype/50host+1HTTP), with880current app paths and original evidence/protected work verified. Two immutable images and corrected actual Linux smoke pass. Private SQL/empty DB exist. User explicitly approved the one beta parent NS delegation; it is applied, four prior records unchanged and automatic SOAserial1→2 recorded. ChildDNS/publicCNAME and managedTLS resources exist; certificate lastPROVISIONING. Operator756c7a7 passes26guards/38native/independentreview; existingbuildae32526a finalstate unverified. CLI now needs reauthentication; fresh SDKpasskey page is open, local setup work continues. No public hosting, migration, app roles, secret values, user enrollment, queue/worker activation or live release acceptance. [Current handoff](handoffs/BETA_DEPLOYMENT.md), [hosted delivery](beta/checkpoint-20261102/hosted-delivery/delivery.json).


Beta security preparation (2026-11-02 morning JST): private credential installer/job renderer passes50mocked checks and independent review without cloud calls or generated values. A separate focused review confirmed the original DBoperator can expose plaintext role passwords in ordinary PostgreSQL/CloudSQL statement-error logging. No live credentials/bootstrap occurred; its use is held while a source-bound password-safety amendment is implemented and reviewed. Fresh SDKpasskey verification remains user-pending.


Beta password-safe checkpoint (2026-11-02 JST): operator8b06a1b replaces unsafe756for futurebootstrap;32pure+26guard+48native checks and independent review pass. Original sources/receipts remain frozen. Four synthetic job bindings select8b06a1b through a recorded renderer supersession; accepted API source stays7924a28. New immutable image context/build plan is ready but unsubmitted; actualSQLprivacy/collector attestation and all live stages wait for the user’s SDKpasskey verification. No live credentials or CloudRun jobs were created. All five application CI jobs remain accepted on unchanged880-path source50566b7. [Current handoff](handoffs/BETA_DEPLOYMENT.md).


Beta deployment progress (2026-11-02 afternoon JST): CLI and Console sign-in restored. Password-safe8b operator builde403b44c succeeded; beta certificateACTIVE. Exact two-flag SQL privacy patch verified with unrelated settings preserved. Seven coupled private credential versions and narrowly scoped2DB identities/2conditioned SQL memberships/4secret memberships are installed. Independent Google web OAuth client and private secretversion1 are created after explicit agreement/credential approval; app remainsTesting,0test users, no AppUser/callback acceptance. Four corrected create bodies received actual validateOnlyHTTP200 after preserving the initial name-field rejection; no jobs executed. A non-superuser native rehearsal exposed an automatic creator-membership issue, so ordering-only bootstrap fix remains unaccepted and rollback-only provider qualification is being prepared. Public service/LB/DNS endpoint, migrations, application roles, queue/worker/scientific/release gates remain pending. [Current deployment handoff](handoffs/BETA_DEPLOYMENT.md).


Beta live milestone (2026-11-02 JST): https://beta.oceaninfobio.com/login is publicly reachable with valid TLS; login200, CSS200, wrong Host403 and actual protected `/v1/runtime`401. Independent LB/IP/child A record and certificate are deployed. Private SQL owner normalization, bootstrap, migrations through0021 and exact serving grants all succeeded. Three-container revision00004-prr is Ready. Source6f03f9d and preceding wrappers are pushed; actual account enrollment/Google callback remain next. User defers lengthy broader release checks in favor of access; scientific/worker dispatch stays closed, scheduler PAUSED and legacy boundary preserved. [Current handoff](handoffs/BETA_DEPLOYMENT.md).


Authenticated beta access delivered (2026-11-02 JST): real Google login with the approved university identity now opens https://beta.oceaninfobio.com/ and renders the v1 shell with Administrator/Internal account access. Current Ready revision00006-sd9 uses the accepted frontend/API images, a private-API startup wait, and only ENABLE_V1_SHELL=true. One-shot enrollment-g58sh and actual account readback passed; temporary token accessor removed/version1 destroyed, and two bootstrap password accessors removed. Research/catalogue and execution remain unavailable until their real services/data are configured. Broader checks are deferred at the user's request; this is access delivery, not complete system/release acceptance. All880 accepted app paths,5368 prior evidence files and42 protected paths still verify unchanged. [Deployment handoff](handoffs/BETA_DEPLOYMENT.md).


Beta catalogue connected (2026-11-02 JST): sourceabcdff7 is pushed; actual buildbddb55b2 and offline Linux image proof PASS. Current Ready revision00007-lxt renders the authenticated Context Catalog with explicit-empty “No eligible snapshots”; catalogue/browser/SHELL enabled, research/dispatch closed, no DB/IAM changes.69 focused checks/14 packaging checks/Ruff/independent review pass;882 committed source paths reconciled with5368 original receipts/90 C27 artifacts/42 protected paths preserved. User selects all eligible existing data; reviewed raw quarantine packaging reconciles1860 actual files via a separately pinned11-path alias amendment, original scientific bytes/manifest untouched. Actual upload and scientific normalization/publication remain separate. Beta read-only CLI now uses the user's isolated wrapper; no role expansion. [Current handoff](handoffs/BETA_DEPLOYMENT.md).


Beta first raw cohort staged (2026-11-02 JST): reviewed preparer/sourceb34a62a and explicit11-path alias amendment preserve the original legacy manifest/raw bytes. Actual archive verification passes1860 unique payload files/89159370bytes/1863members; four create-only objects are copied to private beta quarantine and each exact generation downloaded/SHA256 verified. No publication, C09 seal, science approval, runtime legacy access or source mutation. Metadata-only remote inventory completesraw1860/eDNA530 but SST remains partial after8MiB metadata cap; further remote copy is unselected. Catalogue revision00007-lxt remains Ready and honestly empty until eligible snapshots are sealed/registered. [Current handoff](handoffs/BETA_DEPLOYMENT.md), [raw staging receipts](beta/raw-quarantine-20261102/).


Beta CTD activation delivered (2026-11-03 JST): **real authenticated CTD catalogue and both tables are live** at https://beta.oceaninfobio.com. Pushed sourcea4923c4, actual build4b8fa356 and network-none Linux image proof pass; Ready revision00008-ngj uses immutable snapshot-api877b1b3. Exact user approval precedes eight create-only generation/SHA256-verified private snapshot objects and one conditional beta-prefix Object Viewer grant. Actual Google browser discovery/inspector/cast and depth tables show162casts/10955observations with100-row first pages and explicit qualifications. Descriptive/unpublished/scientific approvalfalse; other raw columns/families and Research/queue/model/worker remain gated.232distinct focused cases across retained231+13runs,32packaging probes/Ruff/review pass;885sources/5368original receipts/90C27artifacts/42protected paths verify. Only API image/two source selectors changed; frontend/proxy/auth/network/secrets/scale preserved. HTTPS200/TLSverified, unauthenticatedruntime401. Broad CI deferred per user; old CI source50566b7 remains unchanged. Next: remaining scientific family qualification and durable retention/context integration before Research. SchedulerPAUSED. [Current handoff](handoffs/BETA_DEPLOYMENT.md), [activation receipts](beta/snapshot-activation-20261103/).


Earlier iterative beta continuation (2026-11-03 JST; superseded by the paused checkpoint above): user reauthorizes remaining scientific data/GCP deployment and three-hour same-chat automation (existing automation updated ACTIVE). Frontend0fc4775 actual build6b48b628 and Linux proof pass; generation9 revision00009-rn7 is live with image005eda32, ONLY frontendimage changed, CTD/API/auth/proxy/network/scale preserved; HTTPS200/TLSverified, unauthenticatedruntime401. Backend remains catalogue-only. Source1d20cf2 prepares eDNA/append publication/exact context grants; b3db9e9 accepts the new explicit authorization ref.279backend+57hosting/typecheck, publisher26/eDNA28/operator35 focused tests,34packagingprobes and28actual nativePG checks pass. Private41additional datasets/250immutablefiles/68844098bytes are sealed, not uploaded.39eDNA bundles retain3155unknown+343negativecontrols and unresolved physical identities; no environmental/scienceapproval claim. Actual offline integration found a C13globalfamilycarrier collision across39eDNAsources; owningfix/performance rehearsal is in progress and APIcandidate799c034a remains undeployed. Corrected contextoperatora9be3b94 image/proof passes; no realDBgrant/job executed. Personaloperator auth expired beforefreshcontrolread; the earlier main Mac SDK sign-in was cancelled at handoff. The dedicated identity remains available on that Mac within its scopes. Keep execution closed and preserve original receipts. [Current handoff](handoffs/BETA_DEPLOYMENT.md).
