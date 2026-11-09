# Research questions activation review — 2026-11-09 JST

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
activation. A replacement source-bound API image is being built. Use the new
amendment's image selection and proposals once its image proof passes. The
original build receipts and proposals retain their historical identities.

Personal CLI sign-in is restored. Fresh readback confirms the queue is paused
and empty, SQL uses private networking and encrypted connections, and serving
storage writes are limited to `control.json`. Controller credential versions
remain empty. The recorded three-attempt queue retry policy is the current
policy; the ten-attempt Research policy remains a proposal. Direct SQL role
and live provider/delivery acceptance are still pending.
[Readback](compatibility-amendment01/cloud-readback.json).

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
