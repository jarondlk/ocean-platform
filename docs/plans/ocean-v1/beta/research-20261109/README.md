# Research questions activation review — 2026-11-09 JST

## Current progress overlay — main Mac return, 2026-11-14 JST

Use the [current deployment handoff](../../handoffs/BETA_DEPLOYMENT.md),
[beta completion plan](../BETA_COMPLETION_PLAN.md) and
[main-Mac audit](../main-mac-return-20261114/audit.json).
Dedicated CLI reads confirmed the held service/controller and successful build.
Exact public manifest bytes now prove that executed proxy `1d2285ce…` is the
Linux/amd64 child of reviewed index `f333a9c5…`. The guard remains unchanged,
private helpers are missing from this Mac's documented locations, and fresh
cost/control/quiescence checks plus actual model/reload/latency acceptance remain
required. No cloud mutation, runtime sweep or Codex scheduling change occurred.

## Historical second Mac checkpoint — 2026-11-14 JST

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
[Verified drain](provider-amendment06/drain.json),
[current/prospective images](provider-amendment06/images.json),
[effective hold and resume order](provider-amendment06/rollout-hold.json).

Two aggregate-only read-only observer executions succeeded after the full
60-second old-request envelope: `kzm8g` at 13:06 UTC and `fpdhd` at 13:12 UTC
on November 11. Both found 3 terminal runs, 2 terminal answer jobs, no active
leases, no pending outbox work and no uncertain model steps; proxy shutdown
was verified. These snapshots have expired. The controller dry-run guard
rejected the executed proxy digest `1d2285ce…` against reviewed digest
`f333a9c5…`; their registry manifest relationship is unverified. The exact
guard remains intact. No controller intent/PUT/apply or new API serving
stage/promotion occurred.
[Completed observer and exact mismatch](provider-amendment06/observer-completed.json).

Source `0f15bbcae3ad73ed76ddb32dd57b3a03dbedb49f` combines the beta-only
Gemini wire `const`→singleton-`enum` correction and bounded authority-read
scopes for retained answer/evidence reads. The original logical schemas,
strict host parsing, historical replay fingerprints, fresh authorization and
closing generation fences remain intact; no deadline was increased.
Tokyo [build `ec6296cd-55ea-42ec-a50a-552364f2a62c`](provider-amendment06/build.json)
passed all four steps in 40.823529845 seconds and produced immutable API digest
`7889ef206cb34008e5a5806ab8bd0ebff486501e53160862e94bfd12b8d875f8`.
Both actual container proofs ran nonroot, network-disabled and read-only:
source/activation/role checks and the frozen SDK's real controller/synthesis
wire checks. The finite [180-source manifest](provider-amendment06/production-source-manifest.json)
and 23-file context contain no original scientific payload or credential values.
Two earlier submissions created no builds: local staging-bucket parsing failed,
then the API rejected a proof argument over 10,000 bytes. The accepted build
splits that proof into two steps, maximum argument 6,462 bytes; only the label
step uses documented literal `$$`→`$` normalization. Their failures are retained.
[Read-scope verification](provider-amendment06/read-scopes-verification.json),
[accepted build configuration](provider-amendment06/cloudbuild.json).

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
[Current composed CI receipt](provider-amendment06/ci.json),
[exact one-scalar workflow proof](provider-amendment06/workflow-supersession.json).
The earlier [318-case / 16-skip / 74-table restore proof](startup-amendment03/ci.json)
belongs to the currently deployed `9969feb2` API, not acceptance of this new source.

[Applied cloud prerequisites](startup-amendment03/cloud-prerequisites.json)
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
are in [preflight.json](provider-amendment06/preflight.json);
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
[History failure](provider-amendment06/history-frontend05-failure.json),
[closed-model usage](startup-amendment03/question03-model-cost-reconciled.json).

The historical [November 11, 21:27 JST ledger](secondary-mac-continuation/cost-refresh-20261111-evening/validation-ledger.json)
records ¥95.010771902 observed plus ancillary reserve; model usage remains
2 calls, 10,599 input / 11,603 total tokens including thoughts, estimated
¥3.706505842. Replacing only the finished build's 600-second reserve with
its one-minute planning allowance of ¥0.949229999 gives
[known observed/reserved total ¥487.460001901](provider-amendment06/candidate-budget-after-build.json),
leaving ¥12.539998099 outside the retained ¥370 model, ¥1.50 observer,
¥20 UI/rollout and already included ¥5 ancillary reserves. Post-ledger cloud
usage from the drain and two observers is not fully reconciled; this is a
stale planning reservation, not actual current spend. Refresh before any further
model question or recurring sweep. No fourth question was admitted.
The unchanged initial limit is 20 questions / ¥500. The [bounded monthly scenario](secondary-mac-continuation/cost-refresh-20261111-evening/monthly-scenario.json)
is ¥36,810.84 including contingency, within the ¥50,000 target and ¥100,000
upper budget; these are planning estimates, not invoices or provider spend caps.

The recurring outbox sweep remains gated on actual model/citation/reload and
new-image live cost acceptance. Three-hour Codex scheduling stays PAUSED.
Scientific approval remains false. Original scientific bytes, immutable receipts
and the separate legacy, eDNA/ANEMONE, experiments and worker gates are preserved.

Reviewed helpers and their tests are retained in durable private storage,
with [hashes and replay restrictions](provider-amendment06/retained-helpers.json).
Saved phase arguments and quiescence proofs are expired. The historical
one-shot refresh helper expects an obsolete execution count and must not be
replayed. Auxiliary diagnostic branch `codex/postgres-reopen-20261111` is retained.

## Historical receiving Mac continuation — 2026-11-09 JST

The original review and amendments below preserve chronology and proposal
identities. Their Research-off/revision17, empty-secret, pending PostgreSQL retry
and unperformed-write descriptions are earlier states. Select current API and
frontend pins from the checkpoint above; the historical proposals remain evidence.

[Recovery, cloud preflight, current JPY forecast and acceptance
receipts](secondary-mac-continuation/) record the receiving Mac's verified
continuation. The user explicitly authorized this documented beta-only
activation scope. The failed PostgreSQL job is being retried through this Mac's
signed-in GitHub CLI; successful unchanged backend/frontend evidence is reused.
Cloud activation remains gated on actual PostgreSQL16 backup/restore success
and fresh live checks. Effective image/activation selection remains
`handoff-amendment02`; scientific approval remains false and the three-hour
Codex schedule stays PAUSED.

## Portable handoff amendment

The expired temporary folders on this Mac are empty. Existing catalogue objects,
the raw quarantine and the five regional SST inputs are being recovered at exact
GCS generations for the user's private Desktop/AirDrop package. Application
credentials are retrieved on the receiving Mac through fresh Google sign-in and
the existing Secret Manager resources.

The unpublished `653f1c…` activation file is unavailable here. A new private
activation is intentionally superseding it, starting from the hash-verified live
`464b0180…` activation. Only the Research flag, authorization reference and policy
revision change. All three snapshot inventories and scientific qualifications
are preserved. The original hashes, images and receipts remain historical.
[Supersession](handoff-amendment02/activation-supersession.json).
Build `f5d0d58d-9431-4049-881f-5a037d6dd080` passes its source and offline SDK
proof. The [effective images](handoff-amendment02/images.json),
[controller proposal](handoff-amendment02/controller-service.proposed.json) and
[serving proposal](handoff-amendment02/serving-changes.proposed.json) bind the
private replacement activation `4843e61b…`. These supersede the earlier
compatibility amendment's selections for future Research activation.

The next full CI run also corrects a runner/toolchain mismatch. All 318 actual
PostgreSQL cases passed, followed by a failed backup restore because the newer
runner's client emitted `transaction_timeout` against server16. The PostgreSQL
job now selects Ubuntu24.04 and explicitly checks the version16 client tools.
The restore gate remains mandatory. On source `3cdecc0`, full backend CI
passed the 100,000-object gate, 17 shared integration cases and the remaining
7,218 cases with 627 explicit skips and 83.88% coverage. All three frontend
jobs passed. PostgreSQL's subsequent attempt crashed with exit139 during the
native C23 artifact test before reaching backup/restore. Its retry and actual
restore acceptance remain open. The connector's retry request was denied with
HTTP403; browser GitHub sign-in was opened. [CI checkpoint](handoff-amendment02/ci-checkpoint.json).
[Correction](handoff-amendment02/postgres-ci-correction.json).

## Compatibility amendment

The beta Gemini adapter now omits the deprecated `temperature` field. The
regression checks cover both the complete runtime request and serialization
through the installed Google SDK with a synthetic credential and mock HTTP
transport. All 67 focused Research checks and Ruff pass. Google's detailed
rules describe this field as ignored, while its migration checklist calls for
removing it. This correction does not establish that every previous call would
have failed. [Guidance](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-flash),
[source verification](compatibility-amendment01/verification.json).

The previous API image in `images.json` is superseded for future Research
activation. Replacement build `1e7fc1c3-422c-442f-9166-4fb8b58e7463` passed
its source-bound nonroot image proof and real SDK wire check with network
disabled. Use the [effective image selection](compatibility-amendment01/images.json),
[controller proposal](compatibility-amendment01/controller-service.proposed.json)
and [serving proposal](compatibility-amendment01/serving-changes.proposed.json).
The original build receipts and proposals retain their historical identities.

Personal CLI sign-in is restored. Fresh readback confirms the queue is paused
and empty, SQL uses private networking and encrypted connections, and serving
storage writes are limited to `control.json`. Controller credential versions
remain empty. The recorded three-attempt queue retry policy is the current
policy; the ten-attempt Research policy remains a proposal. Direct SQL role
and live provider/delivery acceptance are still pending.
[Readback](compatibility-amendment01/cloud-readback.json).

A fresh full CI run on the corrected runtime source exposed three earlier
verification gaps. The catalogue regression had lint-only formatting errors.
Two UI tests still expected prose removed by the approved copy cleanup. The
standalone host test expected a submission route to be absent after the explicit
Research proxy was added. The tests now verify current availability, API
capability denial and revoked-account denial. All 1,064 prototype tests,
the actual standalone HTTP check, production host build, 19 catalogue regressions
and complete active Python lint pass locally. Fresh hosted follow-up is pending.
[Failure and correction record](compatibility-amendment01/ci-failure-followup.json).

**Prepared and qualified; not live.** The user prioritized Research questions
and selected Gemini through Vertex AI. Live beta remains revision
`ocean-v1-beta-serving-00017-kvz`, 100% traffic, with Research execution disabled.
CTD, metagenome, MUR regional SST and saved investigations remain available.
The Research task queue is still PAUSED. The three-hour Codex automation stays
PAUSED throughout this work.

## Qualified software

Source `d9a18a508d7c36b36899bad828cd81478f0101bc` adds explicit durable Research
hosting, a separate authenticated private delivery host, Cloud Tasks transport,
and a beta-only Gemini runtime. Source `fd41f7c466be7db06d9fbee20ffeee508a885efd`
adds the fixed SQL grant operator and frontend startup gate. Source
`84fe01714e426a66ee7b30559b69ebe05ef8f04f` adds the separate private controller
credential initializer, proxy shutdown and grant verification-only mode.
The last commit changes no API/frontend runtime sources.

The [four immutable images](images.json) all passed Tokyo Cloud Build builds
and nonroot, network-disabled image checks. [Build receipts](builds.json)
record exact build IDs, source archive generations and result digests. The API
image binds an unpublished Research metadata activation; it cannot be enabled
by changing flags against the previous activation. No scientific payload,
activation document or credential was put into an application image.

Verification retained outside Git in the owner-controlled task directory:

- 340 focused integration tests passed; 90 focused Research-service cases also
  passed in a separate overlapping run. These are not additive unique counts.
- Hosting proxy: 60 tests and typecheck passed. The Node startup-gate check
  passed for both expected API modes and rejected mismatches/invalid flags.
- 34 packaging boundary probes passed. Controller credential REST boundaries:
  9 tests passed. Focused Ruff checks passed.
- Disposable PostgreSQL16 build `98dd68e3-2a0d-4187-80a3-e028fcf1a5b3`
  passed the actual scoped grant operator and saved question/citation journey.
- Final PostgreSQL16 build `0ff6da45-c968-4b5b-b641-0d1a91f77d61` passed
  the actual initializer, explicit same-version reconciliation, SCRAM
  wrong-password rejection, exact grant/operator verification and the saved
  question/citation journey (1 native integration case, 19.08 seconds).
  Its isolated database container was removed. This uses synthetic scientific
  inputs, in-memory secret transport and model/delivery doubles. It does **not**
  establish live Cloud SQL, Secret Manager, Cloud Tasks or Gemini acceptance.

Initial image attempts failed because BuildKit was absent. Subsequent API and
frontend verification commands wrongly expected build-only files or a single
Next route bundle; those checks were corrected and new builds passed. The
credential qualification's first submit was rejected for an unescaped Cloud
Build shell variable; the corrected submission passed. Original failures are
retained in the private task directory, not relabelled as successful builds.
Docker Desktop was unavailable, so current native acceptance ran in disposable
Cloud Build PostgreSQL16, not in an unverified local database.

## Proposed cloud changes

[Cloud changes](cloud-changes.proposed.json) enumerate API enablement, exact
IAM grants, queue retry settings and a five-minute **runtime outbox recovery**
schedule. This is separate from the paused three-hour Codex development
automation. The runtime schedule is created paused and enabled only after
live question and cost checks pass. Successful requests normally enqueue their
own task immediately; the sweep recovers pending durable outbox entries.

The live controller secret resource exists but has no versions. The original
bootstrap did not provision the controller SQL identity. The
[credential job](controller-credential-job.proposed.json) therefore creates
only `ocean_v1_research_controller` and the first version of the existing
controller DB secret, using the existing bootstrap identity and private proxy.
The generated credential remains inside job memory, SQL's SCRAM verifier and
Secret Manager. The job refuses existing roles/versions unless an operator
explicitly reconciles one numeric version after inspecting an uncertain result.
Remove temporary secret access after verification. Never rerun original DB
bootstrap, migration, enrollment or credential finalization.

The [grant job](research-grants-job.proposed.json) runs once using the existing
migrator identity/private proxy and the [fixed grant SQL](research-grants.proposed.sql).
Both jobs have one task and zero automatic retries. Runtime roles receive fixed
table/column rights and a narrow account-row lock function; no account writes,
role memberships, wildcard grants, schema changes or deletions are added.
An uncertain grant result requires readback/`--verify-only`, not blind replay.

The new [private controller service](controller-service.proposed.json) uses the
existing controller identity, internal ingress and Cloud Run IAM, with an
additional verified task-invoker OIDC identity check inside the application.
It has min0/max1, concurrency1, a 240-second request deadline, one 1CPU/4Gi
controller and the existing pinned private SQL proxy. Its default run.app URL
stays enabled for same-project Cloud Tasks/Scheduler internal ingress. No
unauthenticated invoker grant is proposed. Confirm its actual default URL and
use that exact origin/audience before applying runtime configuration.

The [runtime config](runtime-config.proposed.json) pins `gemini-3.8-flash`,
global, LOW thinking, output4096, no provider retries and a maximum45-second
provider request within the remaining operation budget. Model processing uses
the global endpoint; Tokyo remains the infrastructure region. Research
questions may send their bounded authorized context to the selected provider.
The [serving changes](serving-changes.proposed.json) replace only the two
application images and explicit Research startup/configuration fields; all
other current identities, secrets, ingress, proxy, networking and scale settings
must be freshly read and preserved. Frontend startup must use the packaged
`/opt/ocean/beta-wait-api.cjs` with expected Research mode true, replacing the
existing inline gate that requires execution false.

[Activation metadata](activation-diff.json) records the original and proposed
hashes. The private activation is not included in Git. All three existing
snapshot inventories, datasets-only restrictions, source qualifications and
scientific approval=false are preserved. Publish the immutable activation
create-only and verify its generation/hash; do not overwrite catalogue control
with an old blob. Normal C21 evidence retention uses the existing control CAS.

## Activation order and live acceptance

1. Obtain the specific new-service/IAM/DB/job/API/runtime-schedule scope below.
   Read current templates, IAM etags, secret-version metadata, catalogue
   control and queue tasks. Stop on unexpected resources or privilege drift.
2. Verify the updated beta cost forecast and bounded validation allocation.
   Enable only the two listed APIs. Apply only missing exact resource grants,
   preserving unrelated bindings. Do not grant blanket AI user/editor roles.
3. Run credential initialization, then the Research grant operator. Verify
   numeric version/SQL access and clean proxy shutdown. Remove temporary
   bootstrap grants. No secret values are read into the operator's Mac/chat.
4. Publish the prepared immutable activation and verify its bytes/generation.
   Create the private controller and verify its Ready state, ingress, IAM,
   exact audience, role-specific DB identity and unauthenticated denial.
5. Stage a serving revision with zero traffic, compare against a fresh live
   template, verify readiness, then promote. Inspect queued tasks before
   resuming the existing queue; never purge unrelated pending tasks.
6. Signed-in checks: deterministic question, actual Gemini-backed question,
   saved evidence/citation/answer, reload, cancellation, duplicate delivery
   and recovery. Confirm CTD/metagenome/SST and saved context still work.
   A deterministic count alone is not proof of a model call.
7. Measure idle sweep and question cost/latency, then enable the five-minute
   runtime recovery job if the forecast fits the approved limit. Test recovery
   of a pending outbox entry. Record actual live results and unresolved gates.

Questions remain limited to the accepted controller grammar and registered
native operations. Unsupported scopes request clarification; this does not
provide unrestricted scientific analysis or automatic cross-snapshot joins.
Unknown abundance denominators, unreviewed regional SST and ANEMONE/eDNA gates
are unchanged. Experiments remain off. The existing15-second answer-history
latency gate and P2 D26-07 remain open until measured; do not merely raise the
deadline or claim complete beta/release acceptance.

## Cost and authorization boundary

The previous [JPY forecast](../quotes-20261102/README.md) was ¥35,604.05 for a
bounded31-day scenario, including contingency, but excluded model usage. It is
historical, not a current bill or permission to spend the difference. Before
queue/sweep activation, refresh actual usage and add measured controller/sweep,
model, build and storage costs. Begin with at most20 manual validation questions
and a ¥500 incremental validation allocation; no load test is proposed. Keep
the existing shared Cloud Run allocation/cap and min0/max1. Neither max1 nor
per-request token limits are whole-project monthly spending caps. Notify the
user **before** a beta forecast would exceed ¥50,000/month; stop new admission
if the bounded allocation cannot be kept. No always-on worker is selected.

Current [Google model pricing](https://cloud.google.com/model-garden/pricing)
lists introductory USD0.75/3.75 per million input/output tokens through2026-12-31,
then USD1.50/7.50; billing uses the applicable JPY SKUs. Obtain a current JPY
quote rather than treating an exchange-rate estimate as the account price.
[Scheduler pricing](https://cloud.google.com/scheduler/pricing) is per job;
controller compute and storage operations caused by sweeps are separate.

The repository [AGENTS.md](../../../../../AGENTS.md) requires:
“Job execution, database administration, direct secrets access, IAM changes,
new services, and other operations need their own authorized scope.”
The existing CLI write grant covers builds and updates to the existing serving
service, not these new scopes. Request approval of this concrete beta-only
activation package before those writes. The user has already chosen Vertex AI;
do not ask them to choose the provider again. No automatic approval review has
rejected an action. No live activation or scope expansion has yet been attempted.

Rollback: pause the Research queue and runtime sweep first, stop new admission,
then return serving traffic to revision00017-kvz. Retain durable rows, evidence
and immutable metadata for inspection. Do not delete roles, secrets or history
as an automatic rollback. Inspect in-flight deliveries and lease state before
any drain/retry. Legacy resources remain untouched.

Private staging at this checkpoint:
`/private/tmp/ocean-beta-research-enable.5zThWK` (not durable backup).
If it disappears, recover source-only contexts from these committed revisions,
reuse verified immutable images, and re-read the exact existing activation to
reconstruct only the documented metadata change. Verify hashes before use;
do not invent original receipts or substitute scientific input bytes.
