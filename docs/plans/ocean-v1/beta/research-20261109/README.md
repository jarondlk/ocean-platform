# Research questions activation review — 2026-11-09 JST

## Current checkpoint — 2026-11-11 JST

Research infrastructure is activated for bounded manual validation; full live
acceptance remains open. Deployed frontend source is `7fe5e1342e586dd994020683c3e3fb227d4b287a`.
Effective selections are unchanged startup03 API `4b24ca90…` and amendment05
frontend `be709b49…`, now live on Ready `00020-n7s` at 100% traffic, generation 33,
with no tags. Full promoted readback verifies exact preservation of all unrelated
writable settings, including API/proxy, identity, secrets and ingress. The
earlier quota-rejected attempt did not execute; the later promotion succeeded
at 01:09 UTC on Nov11.
[Live frontend receipt](frontend-amendment05/serving.json),
[effective images](frontend-amendment05/images.json).

The [amendment05 exact-source build](frontend-amendment05/build.json) passed
all affected Linux gates: 1,085 prototype, 61 host and 1 standalone HTTP test,
both production audits/typechecks/builds and actual packaged startup/login with
UID/GID1000, network disabled and Research API expected=true. It includes
independent reader-failure ownership and parallel event/evidence reads without
changing the overall 15-second history deadline or policy checks. Reuse
[source 9969 full CI 42721324508](startup-amendment03/ci.json), all jobs passed,
for unchanged backend/PostgreSQL: 318 native cases, 16 expected skips and actual
version 16.15 restore of 74 tables. The [original retry](secondary-mac-continuation/ci.json)
also succeeded as job 129184649747 in run 42594709784; the prior exit139 is retained
with cause unknown. The narrow activation serialization correction preserves
the exact replacement hash and all generation/access/scientific guards.

[Applied cloud prerequisites](startup-amendment03/cloud-prerequisites.json)
record scoped IAM, successful credential/grant jobs, enabled numeric controller
secret version 1 and temporary-grant cleanup. The exact immutable activation
`4843e61b95c0c0af27079e669d9c661556a362fef3a4c17ce6a30ebe959a7694`
is published at generation 1794232040589985. Private controller `00002-mcw`
is Ready, internal and IAM-restricted to the task-invoker. The queue is PAUSED
with 0 tasks, runtime Scheduler job absent and three-hour Codex schedule PAUSED.
Scientific approval remains false and all original scientific bytes remain
preserved. Legacy, eDNA/ANEMONE, experiments and workers retain separate gates.

Deterministic count completed with 0 model calls and a persistent native cited
answer; queued cancellation, terminal duplicate delivery and outbox recovery
passed. Actual Gemini question03 ended partial/`repair_budget` after 143 seconds
and two STOP responses. Its saved native partial answer used 0 synthesis calls,
so the Gemini-backed cited-answer gate remains open alongside signed-in
history/evidence latency and persistence/reload. Read-only diagnostic execution
`ocean-v1-beta-research-diagnostics-20261110-ssdgb` verified both leases were
closed and 2 physical calls: 10,599 input / 11,603 total tokens, including thoughts,
estimated ¥3.706505842. [Reconciliation](startup-amendment03/question03-model-cost-reconciled.json).

The Nov11 01:30 UTC [validation ledger](secondary-mac-continuation/cost-refresh-20261111/validation-ledger.json)
estimates ¥91.721211491 observed or reserved. One 600-second API build ceiling
plus a rounded ¥370 future-question reserve would leave ¥28.786488519 for
verification. Refresh after subsequent UI reads and before admission. The
20-question/¥500 initial limit remains unchanged. The independently checked
cumulative 14-call bound with the normalized wire schema is ¥365.885449638;
no new question is admitted. The [fresh bounded monthly scenario](secondary-mac-continuation/cost-refresh-20261111/monthly-scenario.json)
is ¥36,810.84 including contingency, within the unchanged ¥50,000/month target
and ¥100,000 upper budget. These are estimates, not invoices or spend caps.
Structural action-shape
execution `-d466m` succeeded read-only. Both hash-bound JSON results selected
`catalogue.open` with the correct target and matching single fact_id, no extra
fields, but `kind` was a string outside `tool`/`finish`/`clarify` (safe enum=null).
That establishes a structural mismatch rather than its provider cause. The
beta-only adapter `const`→`enum` correction is committed as source
`77c1517f9c996544d08d3dbd7cafcae868e8d78a`. [Normal CI 42939381842](https://github.com/jarondlk/ocean-platform/actions/runs/42939381842), image qualification
and new valid live question/cited-answer proof remain pending; this source is
distinct from the deployed `9969feb2` API.
Historical replays stay preserved and no new question is admitted. The recurring
outbox sweep remains gated.

Fresh signed-in frontend05 still misses the 15-second history gate:
evidence/list took 13.907 seconds after answer-list took 2.473 seconds. Server
read-path diagnosis continues without relaxing deadlines or access guards.
[Shared model cap proof](startup-amendment03/shared-model-cap-proof.json),
[structural diagnostic receipt](startup-amendment03/action-shape-diagnostic.json).

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
