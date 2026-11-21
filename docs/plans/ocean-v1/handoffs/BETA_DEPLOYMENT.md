# Beta deployment continuation — 2026-11-21 JST

## November 21 — B2 image built and serving preview accepted

Resume from the [image, build and preview receipt](../beta/b2-20261116/api-image-20261121.json).
Packaging source `d9ec1f3` uses accepted runtime `a5f61ca` and inherits
the accepted B1 API image. Cloud Build `86ecd91d-d11a-4507-ad29-cac3a4b3566b`
passed and produced registry digest
`sha256:525145a88ef8bfc5c93cf468753432f16babb49597298370bcc00f98ff1e5e04`.
The source context contains the six runtime overlays and two opaque activation
bindings. The existing binding is the default. Both bindings passed the
network-disabled image proof together with the non-root identity and both entry
points. Broad CI run `43812513025` also passed its five applicable jobs.

The serving generation 62 and private controller generation 7 readbacks
match the B1 template and traffic receipts. Cloud Run accepted a validate-only
preview of the serving revision with the original binding and Research admission
closed. The after-read matched the original service exactly. The preview's
operation name returned HTTP 404 on follow-up. Use the successful preview and
unchanged readback as the evidence for this step.

The temporary workspace is `/private/tmp/ocean-b2-delivery-20261121`. Its build
context and proof are preserved in
`~/Library/Application Support/OCEAN/private-handoff-20261121-b2-build`
(20 files, 221,384 bytes). The separate prepared-data archive below still holds
the qualified 39-dataset candidate. Reuse this image and candidate on continuation.
The initial CLI call using the bare staging bucket failed URI validation. The
successful build used its existing `/source` prefix and recorded the exact
archive generation.

Operator credentials need reauthentication for the controller and catalogue.
The Google Cloud SDK sign-in has been opened. After sign-in, verify queue and
Scheduler state and production quiescence, qualify the bounded rollout and
private GCS probes, then stage the compatible API and controller on the original
activation. Read the existing Q6 evidence before appending. Refresh the
catalogue control generation at apply time and preserve the compatible
old-binding rollback. Actual GCS and signed-in acceptance remain pending.

## Current November16 — B2 source verified and real private candidate ready

Resume [qualified-private-candidate.json](../beta/b2-20261116/qualified-private-candidate.json).
Sourcea5f61caf8bad63c993853d26d96115fafec45b9e has accepted hosted run43812513072,
job133117113615:765 runtime tests,43 actualPG16 SQL/C12 cases and4 actual C21
retained-append/current-denial cases. Earlier local/pending checkpoints below are
historical. The separate broad CI43812513025 is still pending; do not call it passed.

Fresh read-only cloud selection:/private/tmp/ocean-b2-20261116/current-base02,
selectionSHA930ae9cb2826a1e21020cba80623a913af15ecbc364a34507d18eae48a51aee3.
It verifies unchanged full serving62/controller7 templates, images, traffic and
ingress; original4843e61b… activation; control generation1794766025753161,
revision34,6snapshots/28refs. Initial attempt01 hit sandbox credential-cache
filesystem restrictions before any cloud operation; authorized escalated attempt02
succeeded. No sign-in is pending. These observations must be refreshed before apply.

Actual source-guarded39-eDNA private preparation is complete at
/private/tmp/ocean-b2-20261116/prepared-edna01. Proposed activation
5460e99c15fcd5241356f254c752c7cad77fffdf4988af6b9d86809ecffa9894;
237 immutable files/62393473bytes, proposed control revision114. Every one of156
scientific table payloads matches its original oracle-bound export hash.39 generated
metadata supersessions update obsolete operational Research wording; scientific
rows, controls, unknowns, methods, physical identities and review lineage are intact.
The actual captured-base/new-candidate central retained-revision proof passes.
Nine new local cold/concurrency1/2/4 trials pass15s/3GiB, with stable response hashes;
these do not establish1CPU4Gi actual GCS/HTTP or signed-in acceptance.

New immutable private scientific archive:
~/Library/Application Support/OCEAN/private-data-20261116-b2-prepared,
320files/75934750bytes,indexd2e1ef4ffa5ba27faf2557a063f073c62aaa33c44f79409e9d5608503aeb693e.
It contains the private candidate/current selection, both retained-proof attempts,
hosted log and test/performance evidence; credentials and service environment
files are excluded. Earlier inputs/local/hosted archives stay untouched. Do not
repeat completed recovery or preparation merely because the temporary root is lost.

**Next delivery ordering is mandatory:** build/source/image-qualify the B2 API
package with explicit old/new opaque binding selection; qualify bounded cost,
fresh one-off observer/probes and exact-target rollout contracts. Stage the
compatible API/controller using the original activation before any C09 lifecycle
append: the old B1 image lacks the unrelated-seal proof and could strand Q6 after
registration. Read actual existing Q6 without resubmitting it. Then create/read
immutable objects, final exact control CAS, private actual GCS candidate probes,
deliberate activation/rearm and signed-in data/context/page-export/withdrawal checks.
A stale CAS requires a newly inspected rebase, preserving old receipts; rollback
uses compatible old binding/image with current control, never an obsolete blob.
Original observer remains generation1/count20 and may not be extended/reused.

All B2 cloud actions so far are reads. No upload/build/deployment/model call,
scientific approval, queue/Scheduler/sweep/automation activation or legacy mutation.
Logical source dispositions, JCOPE source-owned partitions/complete operations,
remaining cold/eviction/actual-container and signed-in gates stay explicit. B3–B5
remain separate. Unrelated working files are preserved.

## Current November16 — B2 current-base and retained-evidence amendment

Resume the [new source amendment](../beta/b2-20261116/current-base-and-retained-proof-amendment.json).
Fresh-base39-eDNA-only preparation and generated qualification supersession are
implemented, with exact private input selections and source guards, no input-store
lock writes, preservation of three-family Research/retention and original table
hashes. It refuses CTD-only/already-appended bases. Actual real preparation must
run only after this source is committed; do not replay the diagnostic old candidate.

An exact captured-base/candidate local check demonstrated the previous append
would make central C14 historical revision compatibility false, stranding B1
evidence. Q6/the beta DB were not read or changed by that diagnostic. Enabled
append now preserves unchanged per-index policy. C14's retained C20/C21 fallback
fully replays canonical control and permits only unrelated seals/still-bound
references outside the exact current closure; current policy/registration/denial
and all nonadditive epochs still apply. Current global revisions/cursors remain
unchanged, and an actual old cursor is rejected after append.

765 local tests and lint pass. New focused hosted CI must qualify this amendment,
43 actual SQL/C12 cases and4 new actual C21 PostgreSQL retained-read/denial cases.
Prior702/43 source7b5d935 acceptance remains immutable, not automatically extended
to this new runtime. Private repro:/private/tmp/ocean-b2-20261116/retained-revision-check01;
new operator tests and logs are alongside it. Preserve them in a new archive at
the next delivery checkpoint. Next:source checkpoint/CI, actual fresh-base private
selection/preparation, dual old/new opaque bindings in a source-bound B2 API
package, bounded cost/probe/rollout contracts. Public beta remains unchanged;
queue/Scheduler/sweep/automation stayPAUSED; no source/control write/model call.
Earlier first-increment receipts remain historical accepted evidence.

## Current November16 — B2 first implementation increment verified

B2 has started. Resume from the [implementation receipt](../beta/b2-20261116/implementation-local-checkpoint.json)
and [accepted hosted verification](../beta/b2-20261116/hosted-verification.json),
with the [delivery plan](../beta/B2_DATA_CATALOGUE_PLAN.md). Preserve earlier receipts.
Recovered and verified all41 pinned eDNA registries/328 objects; select39 current-v3
bundles. The independent original-source oracle and old canonical exports match
3498 occurrences/classifications/assays and349638 detections; controls, unknowns,
methods and unresolved physical identities are unchanged. Current six C09 snapshots,
13 payload objects and beta quarantine are also recovered. Do not repeat recovery,
transfers/imports/migrations or old B1 Jobs.

Private working root:/private/tmp/ocean-b2-20261116. Immutable scientific-input
archive:~/Library/Application Support/OCEAN/private-data-20261116-b2-inputs,
1339files/382761793bytes,indexdcffdb68ff5c423876538c6fe51a848afd561d86d9b3f483a2796320b5e84a1c.
It predates the new cache/host tests and local C14 measurements; preserve that
archive unchanged. The later evidence is now preserved separately in
~/Library/Application Support/OCEAN/private-handoff-20261116-b2-local,
29files/89400bytes,indexe3407e1340f2d55823cee3ac617013eba506d9ebc6583c5ac3a06eed5c9e9470.
Hosted logs and later costly-path measurements are preserved in the separate
private-handoff-20261116-b2-hosted archive,6files/709172bytes,
index07af6765c005799fa3a3c01ce19185877364f23ed0d40d4a7876144ab23d6663.
Scientific payloads stay private.

Runtime changes:bounded per-load C12 taxonomy/primitive validation reuse; explicit
trusted-host semantic-input cache(max1GiB/64entries/2distinct fills), exact manifest/
verified byte/generation keys, detached frames, per-caller decoded bounds, fresh
policy/namespace/registration/control/activation fences. No catalogue view cache.
After per-load optimization alone, full-cohort concurrency4 failed18.56s/3.55GiB;
retain that failure. With the cache,9 isolated local cold trials at1/2/4concurrency
pass5.39–6.16s/max1.28GiB. Warm4requests take1.39s, exact response hashes retained.
702 focused local checks and lint pass. Source7b5d9354e56a7634dec67113b1451c802668955b
passes focused hosted run43809484652/job133107699062:702 runtime tests and43 actual
PostgreSQL16 canonical SQL/frozen-row parity cases. The first run43808982872 passed
runtime checks but failed43 database setups because the new fixture omitted
pgvector initialization; original failure/log retained. Only the disposable CI
setup changed between sources1de54a7 and7b5d935; all14 runtime/test pins are equal.
The separate broad CI43809484842 remains pending at this checkpoint.
An additional88 local trials cover39-dataset listing, largest-dataset detailed
open, raw occurrence/detection pages, raw/eligible counts, coverage and inventory.
Warm detection pages take1.48–1.72s, all responses remain deterministic per case,
and peakRSS is1.52GiB; these do not replace per-path three-process-cold/GCS trials.
Research-preserving publisher amendment requires explicit true plus independently
selected base activation hash and exact remote immutable base read before writes;
default false behavior stays intact. No actual publication has happened.

Next:complete logical source dispositions and remaining per-path cold,
eviction and actual container/GCS measurements; reuse accepted unchanged evidence;
write a new current-base39-eDNA-only preparer. Replace the obsolete generated
qualification “all scientific/research execution gates false” only in the new
operational wrapper, with explicit metadata supersession and original rows/review
lineage intact. Do not replay CTD-only prepare_cohorts/all-qualified. Before any
live write/build/probe, refresh cost and current serving/controller/control bindings.
Preserve all C17/C21 references, holds, audits and current Research mode. Actual
signed-in context/page-export/withdrawal and B2 acceptance remain open.

Serving62/controller7/API55cef311/frontend0bde2554 are unchanged. There have been
no B2 cloud writes, builds, rollouts or model calls. Queue/Scheduler/sweep/Codex
schedule remainPAUSED; B3–B5 stay separate. No sign-in action is currently required.
Unrelated working files remain preserved. Earlier sections are historical.

## Current November16 — B2 plan prepared; implementation not started

B1 remains accepted. [Detailed B2 plan](../beta/B2_DATA_CATALOGUE_PLAN.md) organizes source recovery and
inventory, C12 cold-path optimization, Research-preserving append preparation,
actual GCS/guarded delivery, signed-in context/export/withdrawal journeys and
final acceptance. [Source/receipt-bound planning audit](../beta/b2-20261116/planning-audit.json). No benchmark,
cloud call, transfer, deployment, source reclassification or runtime change was
performed in this planning checkpoint.

Ready for preparation/local work; eDNA is **not ready for activation**. The old
normalized/raw private input directories are absent; the held preparation path
is an empty store directory. Recover generation/hash-pinned inputs using the
documented procedure, recording new recovery evidence without repeating uploads.
The old preparation targets a CTD-only base and its publisher requires
research_enabled=false; qualify a fresh-base append preserving current enabled
Research, old descriptors and all C17/C21 holds/references before publication.
The expected increment is39eDNA datasets, not the41old additions that included
already deployed metagenome/SST. All membership/totals require fresh reconciliation.

Prefer bounded per-load taxonomy/primitive validation improvements before adding
a production semantic cache. Measure complete39dataset cold/warm paths and
concurrency1/2/4 against current1CPU/4GiB API; proposed process-peak budget3GiB,
unchanged15s request deadline. The user's accepted17.671s full-page cold load
remains a separate nonblocking UX disposition. Private cache timing is diagnostic.
Close the incomplete SST inventory and give every intended dataset an explicit
state; preserve controls/unknowns/unresolved sample IDs, product and method units.
Use the real bounded C21 page export, not prototype transcript/bulk exports.

Next implementation increment: B2.1 exact input recovery/inventory and independent
oracle, followed by B2.2 measured cold-path repair. No new scientific decision is
needed to prepare honest raw inventory; missing generations or actual eligibility
reviews remain explicit gates. Queue/scheduling and execution stayPAUSED/gated;
B3–B5 acceptance is unchanged. Unrelated/scientific working files are preserved.
Earlier sections below are historical checkpoints.

## Current November16 — B1 complete; B2 readiness next

B1 is accepted within its documented Research scope. Fresh SDK sign-in succeeded
and actual queue/Scheduler readbacks close the former pending gate: queuePAUSED,
0tasks,0Scheduler jobs; serving62/controller7 and full settings remain unchanged.
Private controller IAM is still only the exact task-invoker identity. Original
observer/grants Jobs remain generation1,count20/1; fixture owner/probe Jobs stay
generation1,count4/6. No cloud mutation or completed test/action was replayed.
[Final B1 acceptance](../beta/b1-20261114/b1-acceptance-20261116.json).

The prior real Gemini CTD object-lookup oracle, durable Q6 answer/two citations,
reload and existing15s per-job read evidence are reused at their exact accepted
source/image identities. Current-image cancel/lost-ACK/409-FULL recovery/continue/
duplicate/revoked-restored access passed; all8 controller deliveries wereHTTP200,
all10 no-retry single-task executions completed, fixture finally suspended with
no Google sign-in path. No new model call, Q6 action, build, rollout, enrollment,
source transfer, IAM grant or scientific approval occurred in closure.

The user accepted the measured **17.671s full cold navigation for now** on
November16. Further cold-navigation optimization is deferred and nonblocking at
this beta stage. The result remains17.671s; no15s full-page benchmark pass or
deadline change is invented. [User UX disposition](../beta/b1-20261114/cold-navigation-ux-disposition-20261116.json). Fresh closing meters
still show8native model calls/26001input/1910combined output. Conservative gross
planningJPY873.80 retains the full200 recovery reserve and corrected Job minima,
under the standing operator-selected1000 allowance; no invoice/hard-cap claim.
Monthly beta target remainsJPY50000 with notice before exceeding it.

**Full beta acceptance remains open.** Next audit B2 data/eDNA/whole-scope
catalogue prerequisites. B3 production workers, B4 supervised outbox/queue/
backup/recovery and B5 whole-system evaluation/release decisions remain open.
Queue, Scheduler, runtime sweep and Codex scheduling remainPAUSED; B1 acceptance
does not claim unattended Research delivery or authorize skipping B4's gates.

New immutable closure archive: ~/Library/Application Support/OCEAN/
private-handoff-20261116-b1-closed (25files,5208333bytes,indexaa998ef6…).
Its25files supplement the unchanged728-file recovery archive/index277f301c…
and all earlier immutable receipts/backups. No auth flow, key, token, DSN or
original scientific table is included. Private control/cost roots are under
/private/tmp/ocean-b1-wrap-20261116/{control-accepted-20261116,cost-accepted-20261116}.
SDK flow03 completed successfully and its code was privately consumed; there is
no pending sign-in action. Unrelated/scientific checkout files are preserved.
Earlier sections below describe historical checkpoints, including the resolved
reauthentication hold; do not replay any of their operations.

## Current November16 — B1 functional recovery passed; final control readback pending

The actual current-image cancellation, lost-ACK/409/FULL-readback recovery,
frozen-context continuation, deterministic retained answer, four duplicate
deliveries and revoked/restored access checks passed. All eight controller
requests returned HTTP200. Ten single-task, no-retry executions completed;
fixture e59c73d1… is finally suspended with fresh SQL readback and has no Google
sign-in path. The real account, Q6 and original scientific bytes were untouched.
[Actual recovery and cost receipt](../beta/b1-20261114/current-image-recovery-result.json).

Source740f966's hosted rehearsal passed21 checks (18 operator/planner,2 synthetic,
1 actual restricted-role PostgreSQL16 lifecycle scenario). Actual image55cef311/
source4872d04 remains on serving62/controller7, frontend0bde/source6fdf666.
Every Job/Execution source, image, program, phase, identity, numeric secret version
and emitted Task interface was checked. Task secret aliases resolve through each
v1 Execution's exact mapping; egress is verified from Job and v1 metadata rather
than invented from an omitted Task field. Original audit rejections are retained.

Fresh00:27UTC meters still show8 model calls,26001input/1910combined output; no
new model call. Conservative planning is **JPY873.79**, including the fullJPY200
recovery reserve and corrected4+6 Job minimums, under the operator-selected1000
allowance supported by standing future approval. The user did not type1000.
Monthly beta target remainsJPY50000; this is no invoice or provider hard cap.

**B1 closure is still pending** fresh queue/Scheduler metadata. Personal SDK
reauthentication expired after all cloud writes completed; its fresh sign-in is
open at the university passkey check (tab12). Complete it and leave the code page
open; never paste the code into chat. The dedicated identity still reads Cloud
Run/Monitoring; its queue403 was preserved and no role was expanded. Last actual
post-delivery task list was empty with queuePAUSED; scheduling was never enabled.
Do not replay any Job, delivery, enrollment, amendment or Q6 action. After login,
perform only fresh queue/tasks/Scheduler readbacks and preserve a separate closure
receipt. No new model, build or rollout is needed.

Existing15s history/answer/evidence jobs passed on this exact image. Full cold
navigation17.671s remains an open UX finding for release acceptance. B2 data,
B3 workers, B4 supervised delivery/recovery and B5 system/release gates remain.
New immutable private checkpoint: ~/Library/Application Support/OCEAN/
private-handoff-20261116-b1-recovery (728files,45771094bytes,index277f301c…);
all earlier backups/receipts unchanged. Private root /private/tmp/
ocean-b1-wrap-20261116; auth flow is separately /private/tmp/
ocean-b1-auth-20261116-02 and excluded from backups/Git. Earlier sections below
are historical checkpoints. Unrelated checkout/scientific files remain preserved.

## Current November16 — live62/7, actual recovery qualification next

API55cef311/source4872d04 is live on serving62/controller7; frontend0bde/source
6fdf666 and all other settings preserved.253runtime/146operator/25C21 PG/19role
checks,4image proofs and24-file source archive passed. All6phases completed,
original observers l6qn8/qj6bn succeeded; original Job generation1/count20.
Do not rerun any rollout/observer/amendment. Queue/scheduling stayPAUSED.
[Actual delivery](../beta/b1-20261114/run-list-rollout-result.json).
Existing15s scheduler jobs now observe history13.211s from navigation, then
answer4.460s; exactQ6 answer7.526s, citation2.831s, complete inputs6.116s, sustained
background noerror. Total navigation17.671s remains an explicit UX finding.
B1remainsOPEN for current-image cancel/duplicate/retry/revocation. Fixed non-login
fixture harness2local tests pass; actual restricted-role PG rehearsal pending.
No live fixture account or recovery Job created yet. [Recovery plan](../beta/b1-20261114/current-image-recovery-plan.json).
Image/runtime180sources unchanged by harness; no new model call/Q6delivery.
Latest private root /private/tmp/ocean-b1-wrap-20261116; new immutable backup
private-handoff-20261116-b1-wrap (542files,index3376974f…) predates62rollout and
latest fixture source; preserve a new increment after current deliveries.
Browser signed-in on About. Earlier sections are historical checkpoints.

## Current November16 — frontend live57; list-fence candidate

Frontend0bde2554/source6fdf666 is live on57, API5aed/controller6 unchanged.
All3CloudBuild gates, exact250-file archive, affected GitHub1089+61+1 checks/
audits passed. [Delivery](../beta/b1-20261114/frontend-history-delivery.json).
Parallel event reads are observed; cold run listing10.454s still makes full
navigation exceed15s. Q6 exact answer and both citations reopen in6.307s. B1
remains OPEN. New list-only request fence preserves all context/payload/principal
checks and closes inside owner-locked SQL before commit;36local tests pass.
Hosted runtime/native PG, new API image and guarded rollout are still pending.
[Candidate](../beta/b1-20261114/run-list-repair-plan.json). Queue/scheduling remainPAUSED;
no Q6 resend/new model call, no fixture account/recovery Job yet. New private
root /private/tmp/ocean-b1-wrap-20261116 includes actualSQL/frontend outcomes.
Do not repeat successful57frontend rollout or bt2ms SQL amendment. Earlier
sections below are historical; preserve all original receipts/unrelated files.

## Current November16 checkpoint — shared owner lock live, frontend history follow-up

Serving56/controller6 retain API5aedf3ba/source148182d. Restricted one-off
migrator Job bt2ms applied only FOR SHARE owner locking; same function OID/ACL/
owner/security metadata, fresh SQL readback,19hosted PG16/operator checks pass.
Admission restored; queue/Scheduler/sweep/Codex scheduling PAUSED. No model call.
[SQL delivery](../beta/b1-20261114/shared-owner-delivery.json).
Q6 answer/citation/complete identities read in4.9/3.7/4.8s and background remains
healthy. Full reload still missed15s: serial six-run event hydration after the
6–8s listing. Do not call B1 complete. Frontend-only bounded3-reader candidate
keeps cursor order, full-batch authority checks, cancellation and15s deadline.
[Read follow-up](../beta/b1-20261114/shared-owner-read-followup.json).
NativeCI43733614756/job132871271224 is exact2d4728b; original fixture failures
43732888694/43733183614 preserved. No SQL/observer/grant operation may be replayed.
Private root /private/tmp/ocean-b1-wrap-20261116/shared-owner. Browser signed-in
on About. Next qualify/build/deploy frontend-only history candidate, then actual
reload/background and current-image recovery matrix. No fixture account/recovery
Job has yet been created. Earlier sections below are historical checkpoints.

Shared owner-lock candidate prepared November16: local51pass/native1skip; hosted
PG16 concurrency/revocation/real-role journey pending. No live SQL change. Exact
function metadata/grants and all180 runtime sources preserved;15s unchanged.
Fresh planning599.7285JPY, native8 unchanged. [Plan](../beta/b1-20261114/shared-owner-lock-plan.json).

## Current B1 checkpoint — live repair, remaining read contention

Updated November16JST: source148182d/image5aedf3ba is deployed and Ready on
serving53/controller6. All6guarded phases completed with full settings preserved,
60s old request envelope and two fresh original quiescence observers j6b59/wnhvp.
Do not repeat rollout or either observer. [Actual rollout](../beta/b1-20261114/ready-list-rollout-result.json).
Q6's existing answer and citation read passed individual observed upper bounds
8.072s/12.511s, but background refresh failed again. Reliable15s acceptance and
current-image recovery remain OPEN. [Read follow-up](../beta/b1-20261114/ready-list-read-followup.json).
No new question or model call occurred. Original source bytes/receipts preserved.

GCPCLI access works. The automatic usage-limit review interrupted the last
browser capture; normal browser access is now restored and the expired beta
session was refreshed. Tab11 is signed-in on About to stop polling. Queue,
Scheduler, sweep and Codex scheduling remain PAUSED; do not resubmit/redeliver Q6.
Private state: `/private/tmp/ocean-b1-finish-20261115/ready-list-candidate` includes
all phase/observer/source/build/CI files, failed background-read text and bounded
browser trials. Latest durable Q6 backups predate this rollout; preserve a new
indexed increment before handoff. Unrelated/scientific checkout files unchanged.

Next: validate shared owner-read locking against real disposable PostgreSQL16,
including blocked role/status changes and preserved mutation/idempotency/ACLs.
The existing owner function serializes concurrent readers with FOR NO KEY UPDATE;
any amendment must be fixed-source, restricted migrator, unchanged grants/owner/
security-definer/search_path, current quiescence and source-bound native evidence.
No SQL amendment, new recovery Job or test account has yet been created.
Then prove actual stable signed-in reload/background reads and bounded current-
image cancellation/duplicate/uncertain-outbox/revocation cases before B1 closure.

### Historical qualified preparation before the completed rollout

## Ready-list delivery qualified — guarded rollout next

Runtime148182d passed248hosted runtime checks and25actual PostgreSQL16.16
checks; operatorfc90172 passed146checks after exact180runtime-byte comparison.
Buildba3bade6…/image5aedf3ba… passed all4source/nonroot/offlineSDK/label proofs;
exact24-file generation-pinned source archive verified. Only2runtime sources
intentionally supersede a0e98fe. Separate fixed READYcontract targets exact
current83ce6e8e predecessor and full immutable settings. Fresh planning520.5131JPY
under standing1000operator allowance; no new model admission. [Qualification](../beta/b1-20261114/ready-list-delivery-qualification.json).
Next: `beta_b1_repair_rollout.py --ready-candidate` drain validate/apply, old60s
request envelope and fresh original observer, then guarded controller/stage/
promote/admit stages. New private root `/private/tmp/ocean-b1-finish-20261115`;
inspect exclusive phase/observer intents before any repeat. Existing original
receipts stay immutable. Actual15s reads and current-image recovery remain open.

## Ongoing B1 completion — ready-list candidate, not yet deployed

User requested finishing B1. Local ready-list candidate changes only
api/v1_beta_question_services.py and orchestration/research_evidence.py.
One SQL transaction retains replay, exact bytes/hashes, current owner/source/
policy, C09 protection, dependency closure and closing authority before commit.
No lock/capability/deadline/model limit change or cross-request cache. Missing/
prepared receipts use the original installation path outside the read scope.
Identical synthetic response,52→34transportreads;4newprivacy/no-write tests and
the corrected source-count case pass. Earlier owning67cases had66functional
passes and one old count expectation failure, now corrected. Native PG test
added; hosted runtime/PG/build/deployment and actual15s read/recovery acceptance
remain pending. Q6 must not be resubmitted or redelivered. Live48/5andPAUSED
queue/scheduling unchanged. [Candidate](../beta/b1-20261114/ready-list-repair-plan.json).

## Current checkpoint — Q6 real Gemini answer and persisted citations verified

On November15, the single already queued Q6 answer was delivered exactly once
with the source-bound canonical dispatcher. No new question, lookup retry,
answer retry, queue resume or schedule activation occurred. Controller returned
HTTP200 in64.888s; terminal metadata independently proves completed/STOP with
one answer physical attempt,4162input/111output tokens and no malformed repair.
Shared lookup+answer budget is78.740s,2tools/2model calls; both leases are closed.
[Delivery](../beta/b1-20261114/question06-answer-delivery.json),
[outcome](../beta/b1-20261114/question06-answer-outcome.json).

The signed-in UI showed the completed answer and two retained receipts. After a
full page reload, Q6was selected from durable history and one explicit read
retry recovered the same answer. Both citation views opened. Canonical CTDid,
CTD family, not_reviewed status and inventory's complete input child snapshot
match the predeclared independent ingestion oracle. This is a supported object
lookup/traceability pass, not an answer to Q4's unsupported cast/depth counts or
independent scientific review. No additional model call was needed for reload.

Repair83ce6e8e/source a0e98fe remains live on serving48/controller5, full other
configuration preserved. Research flags true; queue, sweep, Scheduler and Codex
scheduling remain PAUSED. Do not click Prepare again or redeliver Q6. Browser
tab11 is on About to stop polling; it is signed in. GCPCLI access works.

Original observer Job generation1 is unchanged. The two source-hashed Q6
metadata-only diagnostic executions txpq7/tttgn used args-only overrides with
unchanged identities,images,numeric secrets,proxy andnetwork; exact reviewed
OCI index→amd64 substitution verified. Count is14 executions. Before-answer
probe joined exact job/run/frozencontext/outbox delivery, queued with zero answer
attempts. After-answer probe proves closed heads and two committed generations.
Neither diagnostic is mislabeled an original quiescence observer receipt.

Fresh complete meters at11:21UTC show8 cumulative native calls,26001input and
1910output tokens. Closed-Q6 conservative planning is506.9420JPY, retaining
29.4684JPY of historical missing usage and releasing only the unused current
300JPY segment reserve. It admits no continuation or new question. Standing
future approval/transparent operator-selected1000validation allowance remain;
monthly target50000JPY/notice before exceeding it are unchanged.
[Cost](../beta/b1-20261114/question06-terminal-reconciliation.json).

B1 remains OPEN: repeated history/evidence reads are intermittent. An actual
history pipeline has1.674s listing followed by14.177s evidence hydration,
exceeding15s even before browser overhead; both RPCs200 do not pass the browser
gate. Earlier generic errors without matching RPCs remain distinct. Full reload
succeeded with an explicit read retry, not as a reliable latency pass. Long
literal qualification metadata/narrow answer panel remain UX follow-ups.
[Read reliability](../beta/b1-20261114/question06-read-reliability.json).

New operator-only terminal reconciliation keeps original native2/native7 guards
strict and requires exact closed Q6 identities/attempts, preserving older missing
usage.40budget tests and127focused operator tests/Ruff pass locally and on hosted
source4dc33a3/run43709165599/job132796786108. All180runtime bytes equal accepted
a0e98fe;232runtime/24actualPG16 tests are explicitly reused, not newly run.
[Hosted checkpoint](../beta/b1-20261114/question06-checkpoint-hosted-verification.json). Runtime bytes/images did not change. Adding budget
paths to the focused workflow makes this operator change trigger its own checks;
the earlier dispatcher was qualified at delivery before this follow-up.

Current checkpoint4dc33a3is pushed; focused hosted follow-up passed. Next:
reduce redundant verified reads in the owning C21 path without
weakening replay/hash/owner/policy/protection/dependency/closing fences. Qualify
any new runtime/source/image before rollout and repeat actual15s signed-in
history/evidence journeys. Current-image cancel/duplicate/retry/revocation and
broader B2–B5 gates remain required. No new model question is needed for this
read-reliability repair. The last LISTcontract pins9d7035b remain historical
delivery authority; the workflow changed at4dc33a3 and its new127-test hosted
proof is recorded separately. Do not treat that old contract or pending-native7
quote as fresh authority for any further dispatch. Do not reuse pending-native7 reservation for admission
after native8, or replay any completed rollout/observer/dispatch operation.

Private root `/private/tmp/ocean-b1-q6-20261115` includes all candidate build/CI/
rollout phases, single delivery acknowledgement, both diagnostic metadata/proofs,
UI reload/citation screenshots and terminal cost capture. Preserve a new indexed
private increment before handoff; older durable backups/indexes remain immutable.
[New private backup](../beta/b1-20261114/question06-completed-private-preservation.json)
retains275files/28,484,556bytes; indexSHA b1a0e385622fe1ae1799d1b4da653ee2d969e26b933610cef231ab104e0c77b8.
Old backups/indexes stay immutable; SDK auth files are excluded. Final cloud
readback proves empty PAUSED queue,0Scheduler jobs, same48/5/full settings.
All unrelated tracked/scientific/untracked files remain untouched.

### Next read-performance investigation — preserve authorization semantics

The observed failure is the combined history hydration deadline, not a failed
Gemini generation. Current frontend lists answers first, then reads retained
receipts/events concurrently under one15s deadline. Open/page citation reads
were generally1–2s warm; an evidence-list read reached14.177s. Use matched
request timings and actual PostgreSQL concurrency to separate transport,
replay/hash work and lock waits before choosing the next repair.

Source review also shows account `FOR NO KEY UPDATE` and site advisory
retention locks can serialize concurrent read transactions. That is a source
finding, not a measured attribution of this particular14.177s request. Do not
change SQL capability bodies, grants, lock modes or row-lock order merely to
remove a timeout. Any such repair needs actual PostgreSQL owner/status change,
retirement/hold and concurrent read/mutation tests. First evaluate reducing
repeated ready-retention transactions/current-source reads while keeping every
replay, receipt/blob hash, exact dependency/hold, owner/policy and closing
activation/control proof. C09 writes must remain outside read scopes. Do not
cache private authority across requests, show unverified stale data, increase
the15s deadline or make a second model question to mask this read failure.

## Historical qualification — list-read delivery qualified; guarded rollout next

Final operator source `98727f44a617287251e917863c5c720195dccc82` passed run
43695470027/job132754899455:98 operator/delivery tests and an actual180-pin
byte comparison to accepted runtime a0e98fe. This explicitly reuses its232
runtime and24 PostgreSQL16 checks. The source-bound writer and canonical
dispatcher, exact83ce6e8e image/build/archive, core CI and fresh664.4339JPY
reservation now qualify together under700 approval.
[Qualification](../beta/b1-20261114/list-read-delivery-qualification.json).
Separate fixed contract: `deploy/gcp/beta/b1/list-read-contract.json`.
Drain validateOnly passed; service remains unchanged at43/4 on181f26d4.
No GCP sign-in or additional approval is currently needed.

Immediate next action: apply the reviewed drain once with
`scripts/beta_b1_repair_rollout.py --directory /private/tmp/ocean-b1-q6-20261115/list-read-candidate --phase drain --apply --list-candidate`.
The private `drain-validate` directory is accepted validation, not an applied
drain; inspect `drain-apply` before attempting any repeat. Then honor the60s
old serving request envelope and launch the original unchanged observer with
an exclusive intent (not a replay of old Q6/source-specific helper assumptions).
Proceed through the five guarded candidate phases with fresh observer receipts,
queue/scheduling paused. Use `--list-candidate` for this writer and for the
canonical answer dispatcher. Never use the older repair contract/mode for83ce.
Q6 is completed and still unprepared; one answer/citation/reload journey remains
authorized, with full300 model reserve held and no new question admission.

## Historical preparation — list-read image built; guarded operator follow-up next

User approved the700JPY validation allowance and routine future follow-ups;
monthly beta target50,000JPY and notice before exceeding it remain in force.
[Approval](../beta/b1-20261114/question06-budget-authorization02.json).
No further GCP sign-in is currently needed. Q6 is still completed with no
successfully submitted answer; never resubmit or repeat its run delivery.

Runtime source `a0e98fe8e1e3bfc60b1f917ce6d9355e93d121ac` is pushed and passed
full source-bound CI43693489204/job132748878213:232 runtime tests,63 operator
checks and24 actual PostgreSQL16.16 tests. No full-runtime/native skip was used;
only the inapplicable old-runtime reuse step was skipped.
[Hosted verification](../beta/b1-20261114/list-read-hosted-verification.json).
Build `ab4b6868-af58-4e21-b524-97cca4c6a2d3` succeeded with all4 exact source,
non-root, offline SDK and label proofs. Image digest83ce6e8e…, exact24-file
staged archive/provider SHA verified. [Build](../beta/b1-20261114/list-read-build-result.json).
It is not deployed. Existing serving43/controller4 remain on181f26d4.

The fixed repair writer now has an explicit `--list-candidate` mode, a distinct
list-read contract/CI/build proof, an exact181f26d4 predecessor, admission drain,
fresh cost/paused-queue guards and preserved full configuration hashes. Original
default receipts and qualification remain unchanged.76 local operator tests
pass, including13 new drift/drain cases. The operator-only hosted follow-up must
pass before any live update; it reuses the232/24 unchanged-runtime acceptance
only after checking all180 source bytes against a0e98fe. Do not repeat broad
runtime/native checks for this operator-only change or claim them newly run.

First operator follow-up ae69888/run43695060802/job132753652900 failed at the
reuse-proof assertion because the loop overwrote the expected revision with a
file hash. Its failure/log remain preserved; operator checks were not reached.
The corrected workflow uses `expected_revision`; its actual180-pin script and76
local operator tests pass. [Correction](../beta/b1-20261114/list-read-operator-proof-correction.json).
The corrected operator-only hosted run is next; no live update has been made.
Fresh meters including the new build give664.4339JPY planning, within approved
700 and retaining the full300 model reserve. [Cost](../beta/b1-20261114/question06-rollout-reservation.json).

The final operator-only follow-up also qualifies the canonical manual dispatcher
for `--list-candidate`. It selects this separate contract before any cloud/task
request, rejects ambiguous modes and retains the original one-task/OIDC/body/
prior-dispatch/paused-queue/intent guards.98 local operator/delivery tests pass.
The final operator CI must bind all5 operator/workflow/test source pins; do not
use the earlier writer-only run as acceptance for the extended dispatcher.
Runtime source a0e98fe and the built83ce6e8e image remain unchanged.

Next: commit/push the operator-only follow-up, retain its exact CI metadata/log,
create the separate fixed `deploy/gcp/beta/b1/list-read-contract.json` bound to
the actual build/image/core CI/operator CI, refresh complete meters/prices and
observer metadata, and run qualification/validateOnly. Candidate private root:
`/private/tmp/ocean-b1-q6-20261115/list-read-candidate` (build, exact archive,
context/source pins and full CI evidence). Full conservative pending-Q6 plan
was663.4312JPY before this build, including300 model reserve/20 cloud margin/2
future observers; reconcile the new build before rollout and preserve all
missing-usage allowances. No new question is admitted by these receipts.

Then drain Research admission on the unchanged181 image; wait its60-second
old serving-request envelope and run the unchanged original read-only observer
for fresh closed-head/outbox authority. Guarded controller/stage/promote and
fresh observer before admit-stage/admit-promote preserve identities, numeric
secrets, sidecars, ingress, networking, scaling and timeouts. Queue and sweep/
Scheduler/Codex scheduling remain PAUSED throughout. Inspect every uncertain
mutation before retry; phase intent directories forbid automatic duplicate PATCH.
Resume the same Q6 and prepare its answer once after evidence/history verify.
Actual latency, citations/reload/recovery and B1–B5 gates remain open.

Q6's reviewed earlier evidence is durable under
`~/Library/Application Support/OCEAN/private-handoff-20261115-q6`:100files,
9.14MB,0700 directories/0600 files, indexed hashes; SDK material excluded.
[Preservation](../beta/b1-20261114/question06-private-preservation.json).
Later build/CI captures are currently only in the private working root; preserve
an additional indexed increment before handing off, without altering that index.

## Historical checkpoint — Q6 lookup completed; evidence-list repair awaiting hosted checks

Fresh Google SDK login completed privately and both CLI identities work. No
further user sign-in is currently needed. Q6 `f7e35a7a-4196-4431-9f3f-d5edbca66bc8`
was submitted and manually delivered exactly once. The UI shows Completed,
34 seconds active time, six activity events; controller request returned 200.
Complete native meters now show seven cumulative model calls (one new), 21,839
input and 1,799 output tokens. [Outcome](../beta/b1-20261114/question06-lookup-outcome.json).

Evidence history intermittently hits its 15-second deadline; a transient run
history 403 also reset selection. Its exact cause is not yet proven. Both Q6
receipts were briefly verified, but preparation was disabled again before a
successful click. There is no answer-submit intent or answer task. A later
attempt to locate/click the disabled control matched no actionable control;
queue readback confirms PAUSED and empty. Do not resubmit Q6 or repeat its run
delivery. Tab11 is signed in on About to stop polling. Original Q4/Q5 failures
and the original cast/depth question remain unchanged, without scientific approval.

Local repair combines the retained-list projection with the final retention
transaction and its current actor, dependency memo and closing authority fence.
Full replay, current reference/protection checks, ownership, payload hashes and
rollback remain enforced; there is no cross-request cache. Synthetic transport
reads reduce from 8/8/15/35 to 6/6/12/28 (activation/control/manifest/object).
51 retention/read-scope tests and 28 budget tests pass, plus 34 package checks,
Ruff and the C21 wire-contract check. Native PostgreSQL and full hosted source
checks remain required. [Candidate plan](../beta/b1-20261114/list-read-repair-plan.json).
Only `orchestration/research_evidence.py` differs among the accepted 180 runtime
pins. Original delivery and source receipts are immutable; this is a candidate,
not a deployed repair. Existing serving43/controller4 remain on image181f26d4.

Fresh cloud meters and all31 current JPY prices retain the entire existing
300JPY/shared14-call Q6 reserve, historical missing usage,20JPY forward cloud
margin and2 future observer executions. Conservative planning is663.4312JPY,
above the explicitly approved650JPY allowance. This is a planning envelope,
not an invoice. [Reconciliation](../beta/b1-20261114/question06-pending-reservation.json).
The new fixed `reconcile_pending_q6` path rejects any eighth model call and
does not admit another question. The original pre-submit/Q5 calculators stay
strict. No new build, Job execution, deployment or model call while this
allowance gate is open; finish independent hosted verification first, then
request a concrete amended allowance before further paid live validation.

Next: commit/push this candidate and inspect its source-bound focused CI,
including actual PostgreSQL16 checks. The workflow's old180-pin reuse proof now
applies only to explicitly marked native-only follow-ups; a changed runtime
must run the full focused checks. Do not use `[native-followup]` for this change.
After acceptance and budget authorization: prepare a new source-bound image and
reviewed rollout/drain plan preserving current181f26d4 configuration, fresh
authority/quiescence/original-source observer, then verify Q6 evidence and prepare
its answer once. The old fixed repair writer intentionally rejects this new
runtime source; never weaken it or rewrite old receipts. Actual latency,
answer/citation/reload/recovery and B1–B5 acceptance remain open. Queue, sweep,
Scheduler and Codex scheduling remain PAUSED. Current private evidence root:
`/private/tmp/ocean-b1-q6-20261115` (not yet copied into the older durable backup).

## Historical Q6 checkpoint — submitted once, canonical manual delivery next

Fresh SDKlogin completed; both CLI identities verified. Budget650approved and
fresh621.4768JPY plan includes the full300model/shared14call reserve. Serving
admit-stage42 and admit-promote43passed exact guards with original-source
observer`…-xdqns`. Controller4/serving43Ready on181f26d4,100%traffic, onlythe2
Research flags true; other full settings preserved. Queue/sweep/Codex scheduling
remain PAUSED. Observer freshness expires; never reuse it for a later mutation.

Actual UI context matches snapshot50bfdf55…/revision401844d5…/payloadcb28a278…,
original investigation/conversation and independent oracle SHA. Only5prior runs
were present. Q6was submitted once through the UI and accepted queued as
`f7e35a7a-4196-4431-9f3f-d5edbca66bc8`. No model/answer acceptance yet.
[Submission/admission](../beta/b1-20261114/question06-submitted.json).
Do not resubmit or continue it as a new question. Tab11signed in on About to
stop polling; the6thqueued card/screenshot and intent are retained privately.

Next: `scripts/beta_b1_dispatch.py --repair-candidate` on current private root
`/private/tmp/ocean-b1-q6-20261115`, kindrun, exact UUIDabove. It verifies current
qualified43/4 services, paused queue, single canonical undispatched task/body/
OIDC/deadline and retains intent before onePOST. Inspect uncertain outcomes;
never retry automatically. Then reopen same run, verify completion, prepare its
answer once and manually dispatch only that canonical answer. Actual citation,
independent oracle and reload remain open. Q4/Q5failures stay immutable.

## Historical fresh Q6 reservation/admission preparation — login restored, fresh621.4768JPY reservation

User requested SDK login reopened. The stale prior flow was cancelled; fresh
Google SDK login completed privately and both personal/beta CLI identities now
verify intended services. Code was delivered to non-echoing child stdin and its
private transfer file removed; no code/token/DSN printed or copied to Git.
[Login restoration](../beta/b1-20261114/question06-login-restored.json).
Old PTY51805 is closed; newer helper session20039 completed successfully. Do not
restart an old auth flow or reuse a consumed code. SDKtab10 was closed after use.

Fresh source/build/archive/composed-CI qualification still passes. Serving41/
controller4 are Ready on181f26d4, full settings preserved and admissionfalse.
QueuePAUSED/0tasks,0Scheduler; original observer generation1/9executions.
Fresh complete model/cloud meters contain6native calls. Both public Gemini
price records re-read200 and exactly match accepted rates; other29prices are
explicitly reused. [Fresh reservation](../beta/b1-20261114/question06-reservation.json)
is621.4768JPY including full300new shared14-call reserve, missing prior usage,
20cloud margin and1future observer, within user-approved650. Monthly50k unchanged.

Admit-stage validateOnly succeeded with service unchanged. Next: execute original
unchanged read-only observer using `/private/tmp/ocean-b1-q6-20261115/start_observer_q6.py`
(once, inspect intent before retry), then repair writer admit-stage/admit-promote
using fresh post-drain quiescence. Q6 is still unsubmitted. Reverify actual UI
frozen context/oracle before one click, retain run UUID and use canonical manual
run/answer dispatch `--repair-candidate`. No queue resume, sweep or Codex schedule.
Actual answer/citations/reload and remaining recovery gates are still open.
Current private working root `/private/tmp/ocean-b1-q6-20261115`; no beta tab was
present in current browser inventory, so open a fresh beta tab for the UI test
and reuse existing cookie if valid. No new user sign-in action is needed now.

## Historical Q6 authorization/SDK handoff —650approved, SDK passkey handoff pending

User explicitly approved650JPY initial live validation (monthly50k unchanged).
[Authorization](../beta/b1-20261114/question06-budget-authorization.json) supersedes
only the former550gate. Q6 remains unsubmitted. Prepared prior plan616.3901JPY
is historical until fresh meters after reauthentication; retain full300model
reserve, missing usage and original failures. No arbitrary scope/limit change.

After the overnight gap, beta's expected8-hour app session expired; the existing
Google identity signed in again successfully. This is not evidence of a new
session bug or a reason to weaken its security. Personal CLI refresh failed with
explicit reauthentication required; dedicated beta CLI reads still work. Fresh
read-only service checks verify serving41/controller4 Ready on181f26d4, full
configuration preservation and serving admissionfalse.180runtime source pins,
exact staged archive and composed CI still qualify.
[Current resumption](../beta/b1-20261114/question06-resume.json).

Fresh Google Cloud SDK sign-in tab9 is open at the university account passkey
check, awaiting user confirmation. Auth flow PTY51805 waits for its verification
code; use this same flow if still active and inspect before restarting. Never
put auth codes/tokens in chat, Git, handoff indexes or logs. User was asked to
finish the passkey/prompts, leave the verification-code page open and reply done.
Do not expand the limited beta CLI's grants to bypass personal authentication.
Tab7 beta is signed in; no new question/task/admission action. Queue/sweep/Codex
scheduling remain PAUSED. Current working root `/private/tmp/ocean-b1-q6-20261115`
contains static exact candidate qualification and fresh service readbacks.

After authentication: fresh complete usage/cost and authority, original-source
observer on the repaired serving/controller configuration, then repair writer
admit-stage/promote; verify current UI frozen context against Q6plan before one
submission. Retain UUID and manually deliver only canonical run/answer tasks with
`--repair-candidate`, no automatic retry. Verify actual answer/citations/reload.
B1 recovery and wider beta gates remain explicit; no completion claim.

## Historical live repair/budget decision checkpoint — repaired beta live, new-model allowance decision pending

Reviewed Q4/Q5/repair evidence is durable at
`~/Library/Application Support/OCEAN/private-handoff-20261115-repair`:248files,
17.83MB,0700directories/0600files and hash-bound private index. No key/token/
auth code/credential store/DSN/scientific table payload copied. Original working
roots remain untouched. [Preservation](../beta/b1-20261114/repair-private-preservation.json).

Controller generation4 / `ocean-v1-beta-research-controller-b1-fix-1115` and
serving generation41 / `ocean-v1-beta-serving-b1-fix-1115` are Ready on repair
image181f26d4 / runtime source9eb9de8. Serving has100%traffic; Research dispatch
and synthesis admission remainfalse. All identities/frontend/proxy/numeric
secrets/ingress/network/scaling/timeouts are preserved. Original-source observer
`…-vq7mr` completed post-drain before all3guarded phases; original Job unchanged,
now9executions. That freshness is historical after180seconds; do not replay it.
[Actual rollout](../beta/b1-20261114/repair-rollout-result.json).

Routine beta Google session refresh completed with the existing enrolled account;
no user action or new GCP login is currently needed. Actual timed hot signed-in
history13.731s and Q5retained evidence11.226s meet15seconds for this journey.
The earlier coarse17.054s observation was not a precise timed gate; keep it
qualified. Two Q5receipts remain readable; historical answer is still unavailable.
[Readback](../beta/b1-20261114/repair-ui-readback.json). This is not a new Gemini
answer or cold-load/scale-matrix pass. Tab7 is signed in on About to stop polling.

Fresh terminal/cloud planning316.3901JPY of550 includes all6native model calls,
4new physical attempts (Q5controller/synthesis +2synthetic schema probes),29.4684
missing-usage reserve, image build,9completed observers,20cloud margin and1future
observer. [Cost](../beta/b1-20261114/repair-cost-after-readback.json).
The exact [Q6 plan](../beta/b1-20261114/question06-plan.json) is one supported CTD
lookup/real synthesis/citations/reload on the same frozen context, reverified
before submission. A fresh full14-call/300JPY reserve puts planning616.3901JPY
above the earlier explicit550initial allowance. A user question requests650;
DO NOT treat an unanswered question, earlier broad GCP approval or continuation
as the numeric amendment. No new question/task/admission action yet. Monthly50k
unchanged. New-model/reload and current-image recovery gates remain open; B1 is
not complete. Runtime queue/sweep/Codex scheduling stay PAUSED.

After an explicit allowance reply: refresh usage/source/context and confirm the
new reservation still fits, run the original unchanged observer on the repaired
configuration (no replay of start_observer.py's old-image-only assumptions),
then guarded admit-stage/admit-promote with the repair writer. Submit Q6 once
through the existing UI, retain UUID, manually deliver its one canonical run/
answer task with `--repair-candidate`. Preserve all intents; inspect uncertain
outcomes before retry. No replacement tasks, silent budgets, old-job rewrites or
scientific-approval claims. Current working root `/private/tmp/ocean-b1-repair-20261115`;
Q4/Q5 originals remain under their original working/private locations.

## Historical qualified preparation before apply — actual repair delivery qualified

Repair source9eb9de8/image181f26d4… is qualified by exact4-step buildd3735340,
provider-hashed archive/all24files and180runtime pins, actual hosted220unit
checks plus successful native-followup43620300346/job132524284823 onfafbed7.
Follow-up verified all180runtime bytes match9eb9de8, passed48operator checks
and24native PostgreSQL16.16 tests. Original native setup failures remain
immutable; broad CI is separate and not claimed complete.
[Delivery qualification](../beta/b1-20261114/repair-delivery-qualification.json).
The repair contract now pins actual CI source/job/log hashes and clears only
hosted preparation. Current68operator task/phase/archive/cost adversarial tests
andRuff pass locally. No repaired service rollout has occurred yet.

Current cost plan311.9020JPY of550 includes both synthetic probes, image build,
full missing-usage bounds,20forward cloud and1future observer. No new paid
question admitted. [Cost](../beta/b1-20261114/repair-cost-before-rollout.json).
Next: validate-only controller/stage, original-source fresh post-drain observer,
then new repair writer controller/stage/promotion. Preserve serving39drain and
controller3until each exact guarded step is observed. Keep queue/sweep/Codex
scheduling PAUSED and new Research admission false. Actual saved-history/
evidence latency, cited model answer/reload and recovery gates stay open.
Use manual dispatcher `--repair-candidate` only after repaired live admission
qualifies, with a separately reconciled currency reservation for the question.

## Historical built candidate/native setup follow-up — repair built, native CI setup follow-up next

Repair source9eb9de8 / image181f26d4… built successfully in exact approved
Cloud Build`d3735340-23c0-45b3-88d9-7b47fb44b333`. All4source/non-root/offline
actual-SDK/label steps passed. Exact staged archive SHA and all24files match
reviewed context;180runtime pins differ from0f15only in the2intended paths.
[Build receipt](../beta/b1-20261114/repair-build-result.json). No repaired image
has been deployed. Source-bound Linux220tests passed on9eb9de8. Native24cases
all stopped at expected-server identity setup because the focused workflow did
not provide its actual owned container peer. The address guard was correct and
is unchanged. [Setup amendment](../beta/b1-20261114/repair-ci-native-setup.json).

The native-followup workflow now supplies docker-inspected exactIPv4 and first
compares every180Git/runtime pin with9eb9de8. It reuses the actual220successful
checks, skips that long repeated step explicitly, and runs48current operator
checks plus real native C21 acceptance. Original failed receipts stay immutable.
The repair contract intentionally has hosted_acceptance_pendingtrue/null IDs;
no apply/validate can pass qualification until actual native success and pinned
source/job/log receipts are installed. New guarded repair writer has18phase/
configuration preservation tests;48operator/privacy/cost tests/Ruff pass locally.
Full original broad CI remains separate and is not claimed passed by this work.

Serving remains drained39/image7889ef20; controller3/image7889ef20. Queue/
sweep/Codex scheduling PAUSED. New observer must use the original unchanged Job
source (the successful Q5 diagnostic execution is not a quiescence receipt).
Original Job generation1,8executions; reserve and reconcile before execution.
Use a fresh post-drain observer and the new repair writer for guarded controller,
stage, promotion. Do not invoke the old fixed-image writer after source edits.
Saved-history/evidence latency precedes any new Research admission. Actual cited
answer/reload/recovery and cost gates remain open. Initial allowance550JPY and
monthly50k unchanged. Current private working root `/private/tmp/ocean-b1-repair-20261115`;
original Q4/Q5/diagnostic/probe working evidence remains unchanged elsewhere.

## Historical repair preparation — admission drained, two source repairs under test

Serving generation39 / `ocean-v1-beta-serving-b1-drain-20261114` is Ready at
100%traffic on the same7889ef20image, with only Research dispatch/synthesis
flagsfalse. Every other input setting is preserved. [Drain](../beta/b1-20261114/repair-drain.json).
Controller remains generation3/image7889ef20. Queue/sweep/Codex scheduling
remain PAUSED; beta and saved history remain available. No new admission.

One fixed read-only diagnostic completed`…-zqrbg`, original Job template
unchanged/generation1, now8executions. Q5 reason is generation_incomplete;
controller and answer heads terminal/leasesclosed. Controller generationSTOP,
5342input/125candidate/5767total tokens; answer failed with missing usage and
no diagnostic finish reason. Do not invent its missing usage or provider text.
[Actual report](../beta/b1-20261114/question05-diagnostic-result.json).
Conservative terminal reconciliation302.3942JPY of550 includes21.2746JPY for
missing usage, combined thought-output accounting,20forward cloud and1future
observer. Accepted price capture reused after fresh429; no billing-role expansion.

Two reserved synthetic-only engineering probes used the original C21 response
schema and the same empty-selection prompt. Original400 INVALID_ARGUMENT;
removing only array minItems/maxItems succeeded200STOP. [Controlled result](../beta/b1-20261114/schema-probe-result.json).
This isolates an accepted wire-schema difference, not provider-internal cause
or a beta answer pass. Beta adapter now removes array bounds only at provider
schema locations. Original schema/replay inputs and strict host size/witness/
evidence checks remain unchanged. Shared legacy runtime untouched.

C21 _retain now skips redundant C09 writes for already-ready receipts, after
matching canonical receipt/blob identity, and fully revalidates current refs,
protection, payload hashes, owner/context and dependency closure before final
authority fence. Prepared/uncertain reconciliation remains. Scoped evidence/list
metadata drops16activation+16control to8+8, with unchanged response and source/
policy/replay checks. Negative/recovery tests added. New runtime source is local
until the next source checkpoint; no repaired image has been built/deployed.
Focused Linux/PostgreSQL CI is prepared; original broad CI remains unchanged.
Keep actual signed-in latency/answer/reload/recovery and cost gates open.

## Historical Q5 diagnosis preparation — Q5 answer unavailable, read-only diagnosis next

Q4's unsupported free-form fixture reached pre-model clarification and was
cancelled once; no Gemini call. Preserve its [failed outcome](../beta/b1-20261114/question04-outcome.json).
Q5 used the predeclared supported object lookup, submitted/delivered once.
Controller completed with2tools/1model call. Answer jobbb9994e4… was submitted
and manually delivered once, then became unavailable with cumulative2model
calls/55.801active seconds/0repairs. No answer/citation pass or automatic retry.
[Q5 outcome](../beta/b1-20261114/question05-outcome.json). Native meters now show
4total calls,3HTTP200/1HTTP400; exact retained generation failure is unobserved.
Evidence/list also returned503 at the existing15-second deadline. Earlier hot
latency observations do not qualify this failing journey. No deadline increased.

Next is the [fixed read-only diagnostic](../beta/b1-20261114/question05-diagnostic-plan.json):
one args-overridden execution of the existing observer with identical identity,
network/proxy/secret/resources and no Job template mutation, SQL write, model
or queue delivery. Validate first, retain intent before one POST, inspect outcome
before any retry.9privacy/fail-closed tests/Ruff pass. Its1.5JPY bound uses the
existing20JPY forward cloud reserve. Reconcile terminal model/actual cloud
usage against550JPY before any further paid question. Fresh price reads were
429; reuse accepted price bytes explicitly, without claiming a fresh read.
Budget metadata read403 does not authorize role expansion. Monthly target50k
unchanged. No fresh Google sign-in is currently required.

Serving38/controller3 remain on accepted7889ef20/runtime0f15bbca; no runtime
source edit yet. Queue and recurring sweep/Codex automation remain PAUSED.
Before runtime repair, drain existing admission using the qualified old-image
writer, wait the full old request envelope and obtain fresh quiescence. Preserve
all180runtime source pins until that drain is complete. Minimal ready-receipt
read optimization and the confirmed provider failure need source-bound tests,
image/hosted evidence and guarded rollout; neither is implemented or passed.
Private current directory `/private/tmp/ocean-b1-20261115-q5`; after-q5 preserves
before/current usage separately. Browser was moved to About after the unavailable
answer to stop polling; no new paid question is authorized by an elapsed timer.

## Historical budget and browser gate

The user explicitly approved the initial validation allowance500→550JPY for
the single predeclared Q4 question/answer segment, then requested continuation
on November15JST. [Authorization](../beta/b1-20261114/question04-budget-authorization.json)
supersedes only the prior budget hold; the14-call shared segment cap,300JPY
model reserve,20JPY cloud margin and50,000JPY/month beta target remain unchanged.
Original plans/hold receipts are immutable. Fresh current planning is522.0093JPY,
leaving27.9907JPY under550; [approved reservation](../beta/b1-20261114/question04-approved-reservation.json).

[Current cloud/readiness receipt](../beta/b1-20261114/resume-20261115.json)
verifies serving38/controller3 Ready on exact accepted API7889ef20, complete
input preservation, private task-invoker IAM, queue PAUSED/0tasks,0Scheduler,
observer generation1/7executions and unchanged22-audit catalogue authority.
All6 selected snapshots remain current; numeric secret metadata is enabled.
Candidate180-source/build/composed-CI qualification passes; the original normal
CI failure is still explicit. No runtime change or broad suite repeat. There
are still only2historical model calls; Q4 has not been submitted or dispatched.
GCP credentials work; no fresh Google sign-in is needed for these checks.

Browser observation of existing beta tab7 was rejected by automatic approval
review after the earlier usage-limit interruption. The November15 retry was
also rejected because the earlier block required explicit guidance. A new
question asks approval to retry read-only observation of this same beta tab.
Do not retry before that reply, bypass the gate through another browser, use
raw browser commands, or submit the UI test through an indirect API. Finish
the actual signed-in UI acceptance only after browser access is cleared.

Active private directory is `/private/tmp/ocean-b1-20261115-q4`, containing
fresh service/control/activation/usage captures and unchanged build/CI inputs.
Older phase readbacks and durable copies remain preserved. After clearance:
check the existing signed-in conversation for any intervening submission,
submit the exact Q4 once, retain its public UUID, then use the reviewed single-
task dispatcher for its canonical run and answer tasks. Keep queue/runtime
sweep/Codex scheduling paused. Actual answer/citations/reload/recovery and
cost reconciliation remain required; B1 is not complete.

## Historical B1 deployment and budget hold — November14

Immediate Q4 gate: refreshed conservative plan is¥509.1663 with all7observer
executions costed, no future observer, full¥300model reserve and¥20forward
cloud margin. The initial¥500 allowance remains unchanged. A user question is
pending for¥550; do not treat silence as approval. No fourth question or new
model call was submitted. [Exact hold](../beta/b1-20261114/question04-budget-hold.json).
The monthly beta target stays¥50,000.136focused operator checks/Ruff pass.
Service admission38 remains active, queue paused; no recurring runtime dispatch.
GCP CLI and beta Google session work, so no new sign-in is currently needed.
Private evidence is now durable at
`~/Library/Application Support/OCEAN/private-handoff-20261114/b1`,129files with
0700directories/0600files and a hash-bound private index. No key, token/store,
auth code or original scientific table payload was copied.
[Preservation receipt](../beta/b1-20261114/private-evidence-preservation.json).
Keep `/private/tmp/ocean-b1-20261114` as the active phase directory; restored
captures must be reread/requalified for current state rather than replayed.
Tab7 is retained signed-in on existing saved results; the new model test remains
unsubmitted. The screenshot shows original saved history, not a new Gemini pass.

Later admission increment: generation38 / `ocean-v1-beta-serving-b1-live-20261114`
is Ready at100%traffic with only the two Research flags true. Fresh observer
`…-wlwl2` succeeded08:50:29UTC before both guarded phases. Queue stays PAUSED,
Scheduler absent; unauthenticated runtime401/private-controller404 verified.
[Admission receipt](../beta/b1-20261114/admission-rollout.json). No fourth question
yet. Portable `scripts/beta_b1_dispatch.py` supports one canonical undispatched
task per public UUID with retained-before-POST intent and no automatic retry.
Reconcile the fresh zero-future-observer cost capture before submitting the
predeclared Q4; then use the manual helper for its run and answer task only.
The later budget hold above supersedes the earlier pending reconciliation.

Serving generation36 / `ocean-v1-beta-serving-b1-provider-20261114` is Ready
at100% traffic on API7889ef20, matching private controller generation3. Fresh
observer`…-dz544` succeeded08:43:01UTC before the traffic-only CAS update;
complete input preservation/readiness pass. Admission flags remain false,
queue PAUSED and empty, Scheduler absent. No model question submitted yet.
[Promotion and signed-in evidence](../beta/b1-20261114/drained-promotion.json).
Existing saved conversation activity loaded within10.931seconds and retained
evidence within4.296seconds; old deterministic cited answer is readable. These
are this journey's observed upper bounds, not a scale/cold-load matrix.

The browser tab7 is signed into beta as the enrolled admin/internal user and
shows the original retained CTD inventory evidence. Continue using this session.
Question04 is predeclared against independent CTD162casts/10,955depth-row
receipts in [oracle plan](../beta/b1-20261114/question04-plan.json).
Fresh cost includes6observer executions and reserves only1future observer plus
¥300shared14-call model segment/¥20remaining cloud allowance:¥499.0271 of the
initial¥500 envelope. No monthly target or actual model limit changed. The
budget estimator now separates completed executions from future observer
reserves;121focused checks/Ruff pass. Reconcile before model submission.
Next: fresh observer, `admit-stage`/`admit-promote`, one UI question and exact
manual Cloud Tasks delivery while queue remains paused. Actual answer/reload,
cancel/duplicate/recovery and cost gates remain open; no runtime sweep yet.

## Historical B1 controller/stage checkpoint

Controller generation3 / `ocean-v1-beta-research-controller-b1-provider-20261114`
is Ready with accepted API7889ef20; complete preserved input configuration passes.
Serving generation35 has `ocean-v1-beta-serving-b1-provider-20261114` staged,
with100% traffic still on drained00021-mgn/admission false. The stage PATCH was
accepted once. Its idle revision is imported/Ready with `RETIRED`; latestReady
remains the prior revision. The writer stopped at that readback, without retry.
[Amendment and exact outcomes](../beta/b1-20261114/idle-stage-amendment.json)
qualify immutable staged configuration separately from runtime startup; the
latter remains required after promotion.116 focused checks/Ruff pass. Regional
namespace endpoint and bounded log pagination are corrected in source0884ad3;
original failed pre-PATCH attempt is retained. Runtime source/build unchanged.

Private working directory `/private/tmp/ocean-b1-20261114` retains original
controller/stage before/plan/operation/after, controller result and stage
`idle-stage-requalification.json`; do not replay controller/stage applies.
Observer`…-tsrjh` succeeded08:34:36UTC; its180-second freshness is historical
after expiry. Refresh current observer/cost before promotion. No fourth question,
queue/Scheduler/automation change. Next: guarded traffic-only promotion, actual
signed-in saved-history/evidence latency, then separately admit one reserved
Gemini question and actual answer/reload/recovery/cost acceptance.

## Historical B1 writer preparation

The user selected B1. New `scripts/beta_b1_rollout.py` and
`scripts/beta_b1_apply.py` reconstruct the fixed-candidate writer, qualified by
100 focused tests/Ruff and actual controller/stage `validateOnly` success with
full service readbacks unchanged. [Preparation/source hashes](../beta/b1-20261114/writer-preparation.json),
[operator usage and boundaries](../../../../deploy/gcp/beta/b1/README.md).
The original private writer is not claimed recovered. New code keeps its own
identity; existing runtime source0f15bbca/image7889ef20 and original receipts
remain unchanged. Live GitHub job metadata and exact workflow/PostgreSQL-log
hashes requalify the accepted composed CI; normal CI remains red, cause unproven.

Private working directory: `/private/tmp/ocean-b1-20261114`. It contains fresh
v1/v2 service/build/GitHub readbacks, qualified plans and provider validation
results. Do not overwrite existing phase directories or replay stale commands.
Fresh metadata/authority and usage/price probes are running before reserved
observer execution and image apply. Next: qualify current budget and source,
obtain fresh post-drain global quiescence, then guarded controller image update,
API zero-traffic stage and promotion. Actual signed-in history/latency checks
precede admission flags and one separately reserved question. No deployment,
new model question, queue/Scheduler or Codex automation change at this checkpoint.

## Historical B0 completion and next-step record

B0 preparation and its dated live preflight passed on November 14. Read the
[B0 completion and next gates](../beta/b0-20261114/README.md),
[source/readiness receipt](../beta/b0-20261114/readiness.json) and
[beta completion plan](../beta/BETA_COMPLETION_PLAN.md). The former proxy
manifest hold has a verified exact index/child implementation and actual
observer execution proof. No controller/serving rollout occurred.

The existing observer source and 402-byte entry wrapper are recovered exactly
from Cloud Run, with original hashes preserved. New
`scripts/beta_b0_preflight.py` and its pinned contract pass 47 tests/Ruff and
verify actual `…-9grc7` execution/report. The 15-file second-Mac helper set is
not recovered; B1 still needs the stage/controller writer recovered by hash or
reconstructed/reviewed. Do not replay old one-shot arguments. New raw captures
and read-only recovery helpers are durable at
`~/Library/Application Support/OCEAN/private-handoff-20261114/b0` (0700/0600),
with hashes in the B0 private evidence index. No key/store/auth-code copy.

Personal Google CLI sign-in is connected and scoped reads succeeded. Continue
using `scripts/gcloud_beta.sh` for its grants and the explicit operator account
only for separately authorized capabilities; no role expansion was made.
Numeric secrets are enabled after resolving Cloud Run aliases; current private
IAM/subject/custom permissions match. Catalogue control generation1794325728054265,
SHA `94f56925…`, revision22/full audit replay and 16 references pass; selected
activation `4843e61b…`/generation1794232040589985 and six registered snapshots
remain current. No data/control/SQL write or completed setup job was repeated.

Observer `ocean-v1-beta-provider-preflight-20261111-9grc7` succeeded at
07:36:12 UTC; 3 terminal runs,2 terminal answer jobs,0active leases, pending
outbox or uncertain model steps; read-only transaction and proxy shutdown pass.
Guard proof verified at 07:37:48 UTC, with 180-second max freshness. Treat it as
historical after expiry and reacquire current quiescence for a later apply.
Closing service specs/generations/traffic match: serving34/`00021-mgn`,
controller2/`00002-mcw`, old API `4b24ca90…`, frontend `be709b49…`.
Research admission remains false; queue PAUSED/0tasks,0runtime Scheduler jobs.
Qualified API `7889ef20…` is still undeployed. Runtime source/CI evidence is reused;
the normal CI native crash remains explicit despite composed PostgreSQL acceptance.

Budget Console readback confirms beta-only¥50,000 alerts (reported¥10,357.58)
and the existing Cloud Run-only¥3,000 enforced cap (directional~¥270.97).
No billing/API/IAM/cap setting changed. Budgets API `SERVICE_DISABLED` used a
read-only Console fallback. Fresh 31 JPY prices are unchanged. Conservative
incremental gross/reserves including one observer are¥176.2657;¥323.7343 remains
inside the initial¥500 envelope, with ingestion-lag reserves retained. This
includes all storage sent bytes at the worst selected internet rate and is not
an invoice. The old¥370 model plus¥20 rollout reserve no longer fits; before
new paid validation, bound a smaller safe model/call envelope or record an
explicit amendment. Still3 submitted questions/2 historical model calls.

Exact next action: begin B1 writer recovery/reconstruction/review and frozen
source/image/build/composed-CI preservation checks. Immediately before any
apply, refresh current configuration/authority/queue/budget and post-drain
quiescence; private-controller image readiness precedes serving API staging
and promotion. No new question or runtime sweep before actual new-image
answer/reload/history/recovery and cost gates. B2–B5 remain open; scientific
approval and release acceptance remain false. Codex scheduling stays PAUSED.

## Historical main Mac return and completion plan

Main-Mac return audit on November 14 fast-forwarded `overhaul` by 8 commits to
`7002312`, preserving existing unrelated work. The current follow-on is the
[beta completion plan](../beta/BETA_COMPLETION_PLAN.md); it carries all 43 C26
rows and 20 C27 operational gates into six bounded milestones. Full beta and
scientific acceptance remain false. This is a progress/evidence integration,
not a deployment or a restart of the paused three-hour automation.

[Audit receipt](../beta/main-mac-return-20261114/audit.json) records fresh
service/controller/build reads through the main Mac's dedicated CLI identity,
180 API and 71 frontend source pins, 79 focused backend passes, focused frontend
checks/lint, and login 200/protected runtime 401. Serving is still generation 34,
revision `00021-mgn` at 100% traffic; controller `00002-mcw` is unchanged. Both
use API `4b24ca90…`; frontend is `be709b49…`; new API `7889ef20…` is undeployed.
New Research dispatch and synthesis remain false. Existing catalogue,
investigation, history and cancellation settings are preserved.

**Proxy finding supersession:** raw registry bytes now prove reviewed index
`f333a9c5…` explicitly names executed digest `1d2285ce…` as its Linux/amd64
manifest. Exact index and child SHA256 checks pass, with raw bytes retained in
the audit directory. The prior observer failures remain immutable. The guard
was not modified; this proof still needs reviewed integration and negative
checks before a rollout. Old quiescence observations and budget are expired.

**Portability gap:** 15 hash-pinned private operator helpers retained on the
second Mac are absent from the two documented locations checked on this Mac.
Transfer privately against `provider-amendment06/retained-helpers.json`, or
reconstruct/review equivalent tools. Do not replay historical phase arguments
or the obsolete one-shot observer refresh helper. No credentials or scientific
payloads were copied into the new audit.

Dedicated wrapper inspection works without new personal sign-in; it does not
provide controller-update, job-execution, SQL/IAM or direct-secret capabilities.
Use already authorized concrete scopes and validate the required operator
credentials when those operations are reached. Fresh queue/Scheduler, IAM and
secret metadata, catalogue control/audits, database quiescence and usage ledger
were **not** requalified by this read-only inspection.

Exact next action: B0 tool recovery/review, exact index/child guard correction,
and fresh scoped preflight/cost/quiescence; then B1 private controller image
update followed by preserved-settings API staging/promotion and actual Gemini
answer/reload/history-latency acceptance. B2 eDNA/data, B3 production experiments,
B4 operations and B5 full acceptance remain in scope. Do not rerun successful
bootstrap, migrations, enrollment, grants or imports. Keep unchanged historical
CI evidence; the original normal run remains failed and its native crash cause
unproven despite separate source-bound PostgreSQL/restore acceptance.

## Historical second Mac checkpoint — 2026-11-14 JST

The following checkpoint is retained as captured on the second Mac. Its lack
of fresh cloud access and unverified proxy relationship are superseded only by
the main-Mac observations above; all other acceptance limitations remain.

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
[Verified drain](../beta/research-20261109/provider-amendment06/drain.json),
[current/prospective images](../beta/research-20261109/provider-amendment06/images.json),
[effective hold and resume order](../beta/research-20261109/provider-amendment06/rollout-hold.json).

Two aggregate-only read-only observer executions succeeded after the full
60-second old-request envelope: `kzm8g` at 13:06 UTC and `fpdhd` at 13:12 UTC
on November 11. Both found 3 terminal runs, 2 terminal answer jobs, no active
leases, no pending outbox work and no uncertain model steps; proxy shutdown
was verified. These snapshots have expired. The controller dry-run guard
rejected the executed proxy digest `1d2285ce…` against reviewed digest
`f333a9c5…`; their registry manifest relationship is unverified. The exact
guard remains intact. No controller intent/PUT/apply or new API serving
stage/promotion occurred.
[Completed observer and exact mismatch](../beta/research-20261109/provider-amendment06/observer-completed.json).

Source `0f15bbcae3ad73ed76ddb32dd57b3a03dbedb49f` combines the beta-only
Gemini wire `const`→singleton-`enum` correction and bounded authority-read
scopes for retained answer/evidence reads. The original logical schemas,
strict host parsing, historical replay fingerprints, fresh authorization and
closing generation fences remain intact; no deadline was increased.
Tokyo [build `ec6296cd-55ea-42ec-a50a-552364f2a62c`](../beta/research-20261109/provider-amendment06/build.json)
passed all four steps in 40.823529845 seconds and produced immutable API digest
`7889ef206cb34008e5a5806ab8bd0ebff486501e53160862e94bfd12b8d875f8`.
Both actual container proofs ran nonroot, network-disabled and read-only:
source/activation/role checks and the frozen SDK's real controller/synthesis
wire checks. The finite [180-source manifest](../beta/research-20261109/provider-amendment06/production-source-manifest.json)
and 23-file context contain no original scientific payload or credential values.
Two earlier submissions created no builds: local staging-bucket parsing failed,
then the API rejected a proof argument over 10,000 bytes. The accepted build
splits that proof into two steps, maximum argument 6,462 bytes; only the label
step uses documented literal `$$`→`$` normalization. Their failures are retained.
[Read-scope verification](../beta/research-20261109/provider-amendment06/read-scopes-verification.json),
[accepted build configuration](../beta/research-20261109/provider-amendment06/cloudbuild.json).

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
[Current composed CI receipt](../beta/research-20261109/provider-amendment06/ci.json),
[exact one-scalar workflow proof](../beta/research-20261109/provider-amendment06/workflow-supersession.json).
The earlier [318-case / 16-skip / 74-table restore proof](../beta/research-20261109/startup-amendment03/ci.json)
belongs to the currently deployed `9969feb2` API, not acceptance of this new source.

[Applied cloud prerequisites](../beta/research-20261109/startup-amendment03/cloud-prerequisites.json)
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
are in [preflight.json](../beta/research-20261109/provider-amendment06/preflight.json);
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
[History failure](../beta/research-20261109/provider-amendment06/history-frontend05-failure.json),
[closed-model usage](../beta/research-20261109/startup-amendment03/question03-model-cost-reconciled.json).

The historical [November 11, 21:27 JST ledger](../beta/research-20261109/secondary-mac-continuation/cost-refresh-20261111-evening/validation-ledger.json)
records ¥95.010771902 observed plus ancillary reserve; model usage remains
2 calls, 10,599 input / 11,603 total tokens including thoughts, estimated
¥3.706505842. Replacing only the finished build's 600-second reserve with
its one-minute planning allowance of ¥0.949229999 gives
[known observed/reserved total ¥487.460001901](../beta/research-20261109/provider-amendment06/candidate-budget-after-build.json),
leaving ¥12.539998099 outside the retained ¥370 model, ¥1.50 observer,
¥20 UI/rollout and already included ¥5 ancillary reserves. Post-ledger cloud
usage from the drain and two observers is not fully reconciled; this is a
stale planning reservation, not actual current spend. Refresh before any further
model question or recurring sweep. No fourth question was admitted.
The unchanged initial limit is 20 questions / ¥500. The [bounded monthly scenario](../beta/research-20261109/secondary-mac-continuation/cost-refresh-20261111-evening/monthly-scenario.json)
is ¥36,810.84 including contingency, within the ¥50,000 target and ¥100,000
upper budget; these are planning estimates, not invoices or provider spend caps.

The recurring outbox sweep remains gated on actual model/citation/reload and
new-image live cost acceptance. Three-hour Codex scheduling stays PAUSED.
Scientific approval remains false. Original scientific bytes, immutable receipts
and the separate legacy, eDNA/ANEMONE, experiments and worker gates are preserved.

Reviewed helpers and their tests are retained in durable private storage,
with [hashes and replay restrictions](../beta/research-20261109/provider-amendment06/retained-helpers.json).
Saved phase arguments and quiescence proofs are expired. The historical
one-shot refresh helper expects an obsolete execution count and must not be
replayed. Auxiliary diagnostic branch `codex/postgres-reopen-20261111` is retained.

## Historical receiving Mac continuation — 2026-11-09 JST

The sections below retain earlier checkpoints and proposals. Their revision17,
Research-off, zero-secret and pending-retry statements are historical; the
effective pins and remaining gates are recorded above.

The receiving checkout was clean at `ad0c313` and fast-forwarded to fetched
`origin/overhaul` `4f4b6166370f475bf27801531e8b1ce0ec587250`. No newer local
commits or uncommitted checkout changes were lost. The older Desktop AirDrop
folder contains the scientific archive, manifest, `local-uncommitted-work` and
`PREPARING.txt`; the newer package files described below were never required
to reconstruct this checkpoint because the repository and the user's exact
continuation instructions supply their replacement evidence.

All 35 regular scientific members passed size/hash verification after unsafe
paths, links, duplicates and unexpected members were rejected. Archive SHA256
`ac44ac66cfcbbe35a71797d9fa87c00ada3b64a7b6f60f7925634ff6f8edd172`,
manifest SHA256 `ab5b1b4c474079fa6de9f9490db73dda060f7db3f1cd8da98ed8b8c3ad9865ac`.
Durable owner-only restoration is under
`~/Library/Application Support/OCEAN/private-handoff-20261109/scientific`.
The 31 older local-work files are preserved separately and have not been applied.
The replacement Research activation has exact hash `4843e61b…`; canonical
serialization and all unchanged scientific inventories/qualifications pass.

This Mac has no dedicated automation credential configuration. A fresh personal
Google CLI sign-in succeeded with the requested Tohoku account, and explicit
beta-project access was verified. GitHub CLI is signed in as `jarondlk` through
this Mac's browser. No credential values enter repository receipts. The SDK is
installed in `~/Library/Application Support/OCEAN/tools/google-cloud-sdk`;
GitHub CLI is `/opt/homebrew/bin/gh`. The Homebrew SDK installation encountered
an existing certificate-link conflict; the downloaded vendor SDK runs with the
existing Python without altering unrelated Homebrew links.

Fresh cloud metadata matches revision `ocean-v1-beta-serving-00017-kvz`,
generation26, 100% traffic, empty PAUSED Research queue and zero controller
secret versions. Private encrypted PostgreSQL16, successful prior setup jobs,
scoped control writes and qualified build `f5d0d58d`/digest `c326fc…` are verified.
Current catalogue control is generation `1793758432247371`, SHA256 `65ea4c9a…`;
the full canonical14-audit chain and8references pass and equal restored bytes.
No old bootstrap/migration/enrollment job is rerun.

The user explicitly approved the concrete beta Research scope in the receiving
Mac continuation prompt. PostgreSQL run `42594709784` is retrying only its failed
job; actual backup/restore remains a required gate. The expanded current JPY
scenario is ¥36,480.84/month with10% contingency. Initial model validation
reserves ¥450 for one question at a time and reconciles actual usage before
admitting another, within20manual questions/¥500 total incremental spend.
Runtime sweep stays paused until live duration/cost checks pass. A safe
Scheduler initialization must avoid creating an immediately active five-minute
job: its state is output-only, so create with verified future cron, pause/read
back, then patch the five-minute schedule while paused.

[Continuation receipts](../beta/research-20261109/secondary-mac-continuation/)
record verification and remaining gates. Research is not yet live. The
three-hour Codex schedule remains PAUSED; scientific approval remains false.

## Historical portable handoff — 2026-11-09 JST

The user is preparing to continue on another Mac. A private AirDrop package is
being finalized at `~/Desktop/OCEAN-Handoff-2026-11-09` with verified cloud-recovered scientific inputs,
source checkpoint and a complete continuation prompt. The three-hour schedule
stays paused. Read the portable handoff amendment in the Research review before
selecting an activation/image; it supersedes the missing temporary private file
through an explicit new metadata identity.

The user explicitly deferred GitHub sign-in and the remaining PostgreSQL retry
to the receiving Mac. The Desktop package includes `CONTINUE_PROMPT.txt`,
`ACCESS.md`, an offline `overhaul.bundle`, private scientific inputs and a hash
verifier. Its `MANIFEST.json` records the exact bundled commit. Require a
successful `verify_handoff.py` run and `TRANSFER_READY.txt` before using it.
No main-Mac continuation or three-hour scheduling is selected by this handoff.

All 318 hosted PostgreSQL cases passed, but final backup/restore exposed an
Ubuntu26 client/server-version mismatch. The workflow now selects Ubuntu24 and
explicit version16 backup clients. A fresh hosted restore pass remains required.
The main application's runtime sources are unchanged by this CI correction.
Source `3cdecc0` passes the full backend and three frontend jobs. PostgreSQL
attempt01 subsequently crashed in the native C23 artifact case with exit139;
backup/restore was not reached. Retry permission through the GitHub connector
was denied; a browser sign-in is pending. Retain this gate in the receiving
Mac's continuation prompt. The portable image build `f5d0d58d` passes and is
bound to the included replacement activation `4843e61b…`. Use the effective
handoff-amendment02 proposals, preserving all original receipts.

## Historical compatibility amendment — 2026-11-09 JST

The Gemini adapter now omits deprecated sampling configuration. All 67 focused
Research checks pass, including real SDK request serialization against mock HTTP
transport. Replacement API build `1e7fc1c3` passes its source-bound nonroot
image proof and offline SDK wire check. The amendment records the effective
image and proposals while preserving the original receipts. See the
[compatibility amendment](../beta/research-20261109/README.md#compatibility-amendment).

Fresh full CI exposed earlier test/lint mismatches. Their corrections pass
1,064 prototype tests, the actual standalone host test, production host build
and complete active Python lint locally. Hosted follow-up is pending.

Fresh personal CLI sign-in and cloud readback confirm an empty paused Research
queue, private encrypted SQL and the exact control-only serving storage write
grant. The controller secret has zero versions. Live SQL role/provider/task
acceptance remains pending. The corrected SDK flow is not a real model call.

Research questions are prioritized, with the user selecting Gemini through
Vertex AI. The [Research activation review](../beta/research-20261109/README.md)
contains four successfully built immutable images, scoped cloud changes,
private-controller/one-shot-job configurations and rollback. The final disposable
PostgreSQL16 qualification passes credential initialization/SCRAM denial, exact
runtime grants and the saved cited-answer journey with synthetic data/provider
transport. It is not live Cloud SQL/Gemini acceptance. Live revision remains
`ocean-v1-beta-serving-00017-kvz`, 100% traffic; Research execution is disabled
and its Cloud Tasks queue is PAUSED at fresh readback. New-service, IAM, database,
job execution, API enablement and runtime outbox scheduling require the specific
activation scope documented in that review. No such writes have been applied.
The three-hour Codex schedule stays PAUSED; legacy and eDNA gates are unchanged.

## Live catalogue checkpoint — 2026-11-05 JST

The authenticated beta serves saved investigations alongside the CTD,
metagenome, and MUR regional SST catalogues on revision
`ocean-v1-beta-serving-00017-kvz` at 100% traffic. The
[request latency update](../beta/context-20261103/request-latency-20261105.md)
removes duplicate listings, ancestor requests and repeated Research discovery
polling. Backend reads verify activation/lifecycle at request boundaries while
preserving per-operation payload verification. Live collection discovery sampled
5.142–5.727 seconds; initial loading still takes several seconds, and scale-to-zero
can add startup delay. The [copy cleanup](../beta/context-20261103/copy-cleanup-20261104.md)
removes promotional and repeated explanatory text while retaining controls,
errors and source-specific scientific qualifications. The [collection-browsing rollout](../beta/context-20261103/catalogue-browsing-20261104.md)
adds visible links to all three authorized collections and clears stale filters
when switching. Search stays within the selected collection; no new data was
activated. The preceding rollout occasionally reached its 15-second discovery
timeout; the latency receipt records the subsequent optimization and its limits.
The [reference-verification follow-up](../beta/context-20261103/reference-verification-20261104.md)
records the deployed API optimization: context changes returned 200 in 8.286
and 8.887 seconds; sampled context reads took 1.504–3.472 seconds. ANEMONE's
separate raw-data latency/integrity acceptance remains open.
The [confirmation follow-up](../beta/context-20261103/save-confirmation-20261104.md)
records the deployed frontend fix and the preceding revision's timing limit.
The [saved investigations receipt](../beta/context-20261103/live-20261104.md)
records the approved grants and initial browser workflow.
The [metagenome/SST rollout receipt](../beta/cohorts-20261103/meta-sst-live-20261104.md)
records the active image, browser checks, and remaining latency limits.
The branch is `overhaul`, and the three-hour schedule remains paused.
The [second Mac handoff](SECONDARY_MAC_HANDOFF.md) describes pinned input
recovery and the earlier CTD-only checkpoint.

## Paused checkpoint — 2026-11-03 JST

The live service remains generation 9, with the updated frontend and the
original CTD-only API. The C13 carrier fix passed 197 local regressions;
explicit staged cohort selection passed 16 tests, and packaging passed 34
probes. The fix is checkpointed in source and has not been built or deployed.
The full cohort passed local catalogue correctness after the fix, but raw eDNA
paging took 15.076610 seconds before network cost, failing the existing
15-second gate. The cache experiment is a local diagnostic only. Resume with
a fresh `meta-sst` append; no new bundle was prepared during the pause.
Context grants and actual Cloud SQL/GCS/browser acceptance remain pending.
[Source receipt](../beta/cohorts-20261103/secondary-mac-source-checkpoint.json).

## Earlier iterative continuation — 2026-11-03 JST

The user explicitly requested iterative deployment of all remaining beta work,
authorized all project scientific data/GCP use, and reactivated a three-hour
same-chat continuation. Existing automation `continue-ocean-overhaul-checkpoints`
was updated, not duplicated. It notifies only on meaningful progress/failure or
required action, checks existing work before continuing, and retains the beta-only
¥50,000 target/notice boundary. No legacy mutation or independent scientific
approval is inferred. [Authorization](../beta/cohorts-20261103/automation-and-authorization.json).

Actual frontend source0fc4775 build6b48b628 succeeded with network-none/nonroot
image proof; immutable image `context-frontend@sha256:005eda32b803676c17a4cdc72ffda3dedc447f4cf73b7533161b43f55d695ea3`
is now Ready generation9 revision `ocean-v1-beta-serving-00009-rn7`. Exact
readback verifies ONLY the frontend image changed. API/proxy/identity/secrets/
network/scale/flags preserved. HTTPS login200/TLSverified and unauthenticated
runtime401; refreshed authenticated browser still renders the CTD catalogue.
The frontend forwards exactly eight C17 context paths through existing auth/
origin/body guards, but the API remains catalogue-only, so context writes remain
unavailable until their actual grants and host composition pass. Do not confuse
this live frontend increment with complete Research deployment.

Pushed source checkpoints:0fc4775 (279 focused backend/57 hosting/typecheck,
32packaging probes/Ruff; qualified meta/SST and context-only source),1d20cf2
(eDNA/append publisher/exact context-grant operator and private aggregate driver),
b3db9e9 (renderer accepts the user’s new Nov3 authorization reference;34probes).
New publisher26tests, eDNA28tests, operator35tests and actual disposable native
PostgreSQL28checks pass. Native C17 transactions reproduced that audit INSERT
RETURNING needs SELECT(created_at); only that column is added, full audit reads
remain denied. Native cluster is stopped/removed. No real SQL grants or jobs run.

All328normalized eDNA artifacts/127885817bytes were read at exact existing source
generations and registry SHA/CRC verified into private staging.39current bundles
normalize to39datasets/3498occurrences/3498assays/349638detections;2older bundles
are excluded.3155classifications are unknown and343negative controls; all3498
physical identities remain unresolved. This allows raw inventory, not an eligible
environmental detection-frequency/association cohort. MUR1455observations and
sixgaps remain an unreviewed regional preview. Metagenome82source-column keys,
106runQC records and125952method-separated cells retain unknown abundance units/
denominators and all zero cells. No calibration/reclassification or science review.
Raw JCOPE remains separate:1837valid source-time grids plus one malformed all-fill
placeholder repeated11paths; missing SST cells remain missing and no dates invented.

Actual private aggregate `/private/tmp/ocean-beta-multi-catalogue-prepared-20261103`
source1d20cf2 seals41additional datasets into three new indices while preserving
the original CTD entry. Activation SHA3fee1baeb47d9d4b9df323ba8041aa661574b8f1e5233fc67498c1f6fcae07c6;
250immutable files/68844098bytes, controlrev4→92. This uses the LAST accepted
basecontrol generation1793637712460705/hash276e0190, not a fresh cloud-read claim.
Publisher must recheck the exact current generation/bytes before any upload and
CAS control last, preserving all refs/audits. Local preparation/publication manifests
and data remain private; nothing from this new cohort is uploaded or activated.

**Actual integration gate discovered:** offline all-family discovery on the new
package fails for eDNA with “Scientific/source canonical identities collide”.
CTD/metagenome/SST per-index overview succeeds. C13 incorrectly reserves the
shared canonical c12:edna directory under each distinct source owner;39legitimate
sources collide. The owning runtime fix and adversarial/multisource regression
checks were in progress at that point. The paused checkpoint above records
the fix and the subsequent latency failure; do not activate this candidate.
Old private preparation and failed diagnostic receipts remain immutable.

API candidateb3db9e9 build896039e7 and network-none source proof succeed, image
`snapshot-api@sha256:799c034a10366ea6ed1e736cc03986c6c979607ff4a77447ac508517e06f87c2`.
It is UNDEPLOYED and gated by the C13 defect; its source/binding must be superseded
explicitly after the fix, not retargeted. Context-operator1d20cf2 corrected build
6b0cba18 and offline source proof succeed, image
`context-operator@sha256:a9be3b94b156c9d1260c609fb5958c4e503772d3564b95c097fa9f3d47bb1340`.
First operator build2b08f03a failed only because its image-proof script had an
invalid broad text substitution; the correction/source-unchanged receipt and
first failure are retained. Initial API binding renderer also refused the new
Nov3 authorization reference locally; the explicit allowlist amendment and empty
preflight submission receipt are retained. Neither failure touched data or DB.

**Earlier authentication gate:** personal GCP authentication expired before a
fresh control read. No upload, grant or job attempt occurred. The automation
identity still worked within its read/build/existing-service update scopes.
The main Mac sign-in has since been cancelled; start a fresh sign-in on the
second Mac. Preserve the empty local preflight directory at
`/private/tmp/ocean-beta-multi-catalogue-20261103`.

Broad CI is deferred per user; the older receipt remains bound to 50566b7.
[New receipts](../beta/cohorts-20261103/),
[context operator/native checks](../beta/context-20261103/).

## Current CTD activation — 2026-11-03 JST

Pushed source `a4923c4e41fba694f77ebb60c1d3f768390e8b1b`; actual build
`4b8fa356-9261-4a0a-9df9-df61c88669ef` and both build/network-none image-proof
steps succeed. Ready generation8 revision `ocean-v1-beta-serving-00008-ngj` uses
`snapshot-api@sha256:877b1b3f7db703f5a8e9fedc3cca30f4a5aa67d238201cb5e9159482561e7eb9`.
Only API image and two source-selection settings changed; frontend/proxy/auth/
network/secrets/scale preserved. Only SHELL/CATALOGUE/CATALOGUE_BROWSER flags
are on in the API. Research/worker/model/scientific dispatch stays off.

After exact user approval, eight create-only CTD objects were copied into private
`gs://ocean-v1-beta-20261101-snapshots/v1/catalogue/`, each exact generation
SHA256-readback verified, lifecycle control last. Serving SA received only the
approved conditional Object Viewer prefix grant. No public, write, project-wide
or legacy grant. Original scientific files/manifest remain unchanged. Actual
operator source and all selection/readback/grant/build/deployment receipts are
retained; do not rerun upload, grant, DB bootstrap/migrations or enrollment.

Actual Google sign-in, catalogue discovery/drill-down, inspector and both tables
render:162cast rows and10955depth rows, with100-row first pages and explicit
source/query completion. Data remains descriptive/unpublished/not_reviewed.
Depth/temperature/salinity retain source rows and signed values; existing contract
units do not imply independent calibration. Other raw columns remain quarantined.
Child snapshot04f779af and index50bfdf55 are explicit registrations; activation
74674398 is immutable. No scientific findings/approvals or cross-source pairing.

232 distinct focused cases across231+final13 retained runs,32packaging checks,
Ruff, independent final review and actual nonroot Linux image proof pass. New
reconciler verifies885composed sources,5368original receipts,90C27 artifacts and
42protected paths. Broad CI is deferred; old run stays bound to50566b7. HTTPS
login200/TLSverified and unauthenticatedruntime401; actual browser observation
and private screenshot hash retained. [Activation delivery](../beta/snapshot-activation-20261103/).

Next: qualify/register metagenome, SST and eDNA under their actual provenance
constraints; integrate durable retention/context writes before Research; then
outbox/queue/model/worker integration and broader release/operational acceptance.
The GCS runtime store is deliberately read-only; it does not provide durable
retention writes needed for research bundles. No missing personal GCP sign-in
currently blocks granted read/build/existing-service-update operations. Use the
local beta wrapper for those authorized scopes, explicit beta project/Tokyo,
exact build SA and approved source bucket. Do not broaden roles for other work.
The user's CLI/AGENTS/wrapper edits remain unrelated and are not staged.

## Historical catalogue and data continuation — 2026-11-02 JST

Catalogue API source `abcdff79d8695be2e493efa29dc92c454d5b6dfe` is pushed.
Actual build `bddb55b2-bd82-4d84-aa07-385bc78d6dcf` and both build/image-proof
steps SUCCEEDED. Current Ready generation7 revision
`ocean-v1-beta-serving-00007-lxt` uses catalogue API image
`asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/catalogue-api@sha256:0de4842308efeef1b64c3e51b9c225d2ce0dbdd5b4b321ea4c65c1b6e37de13d`.
Catalogue/browser flags and SHELL are enabled only in the API. No database, IAM,
network, OAuth or dispatch change. Frontend and private proxy images unchanged.
Actual authenticated browser now renders Context Catalog controls and the honest
**No eligible snapshots** state. It is a real configured empty inventory, not a
fallback for missing scientific data. Research remains unavailable.

69 focused host/authority checks,14 packaging checks, Ruff and independent review
pass. Actual nonrootLinux/no-network image proof confirms root-owned0444 files,
source/config identity, import closure and real empty discovery. New delivery
reconciles882 committed source paths (two intentional source/test supersessions
and two additions),5368 original receipts,90 C27 artifacts and42 protected paths.
The previous hosted run remains bound to50566b7; broad CI/release acceptance is
deferred per user. [Catalogue delivery](../beta/catalogue-20261102/).

User answered **“Lets do all”** for the initial beta dataset selection. This
covers preparation/copy of all eligible existing scientific data to independent
beta, not accounts/history/backups/credentials or invented scientific reviews.
The first available raw CTD/metagenome/SST cohort has1860 unique files and
89159370 payload bytes. Its immutable legacy manifest9ac5170f has1860 entries but
1849 unique paths; a separately pinned11-path raw-alias amendment reconciles the
complete actual local inventory while retaining the original manifest unchanged.
Different-date SST filenames with identical bytes do not establish independent
observations or valid observation dates. Embedded time/provenance and scientific
deduplication remain publication gates. The reviewed quarantine preparer has23
focused tests plus Ruff and is committed at `b34a62a9168b58f8aba96632fe213bf08fc8a9f3`.
Actual preparation succeeded:1863 archive members/91934720 archive bytes, SHA256
`e62eb0e62ad1a1b0b9354944cb46b3b1d818fd12b5076b1e2749fb317cf471cb`.
Four create-only objects are now stored under private
`gs://ocean-v1-beta-20261101-quarantine/v1/raw-imports/local-20261102-e62eb0e62ad1/`.
Each exact generation was downloaded and SHA256 verified. Bucket Tokyo/PAPenforced/
uniform access and no public bindings were checked; no IAM or source mutation.
The first upload preflight stopped locally on an atime comparison before any
cloud call; stable metadata comparison fixed it before the single selected upload.
Do not rerun preparation/upload: accepted local package and source/target receipts exist.
The private archive and full source/transfer manifests remain outside Git.
Raw archive/staging is not a C09 seal, catalogue registration or scientific approval.
Metadata-only origin inventory separately observed all1860 raw source objects
(89159370bytes) and530eDNA objects (329136303bytes). SST inventory stopped at its
8MiB metadata cap after16000objects, so the overall remote inventory is explicitly
partial/unaccepted. Completed prefix inventories must not be repeated blindly.
No source object body was read by that inventory, and no remote cohort copied.
Five existing regional-publication objects (2619780bytes) were subsequently read
at exact generations into private Mac staging, CRC-verified, and publication/period/
registry SHA256 bindings reconciled to current operational publicationd34da58.
Actual source decision is user-accepted operational publication; independent
researcher approval/provider endorsement remain false. Retained period is explicitly
unpublished regional-context preview with scientific_approval=false. Preserve
those exact qualifications; historical embedded instructions do not grant new
authorization. Two referenced analysis dependencies remain pending. No regional
publication/data was copied to beta or registered. Source objects/private data
remain outside Git; sanitized readback/qualification receipts are in raw staging.

Precise remaining SST/current-publication selection is next; exclude operational,
backup, account/history/secret and serving-cache material. [Raw staging](../beta/raw-quarantine-20261102/).

Historical read-only scope at that checkpoint: use `./scripts/gcloud_beta.sh`
when local config is present, per user AGENTS instructions. It has viewer roles
only; do not broaden them. It successfully inspected current service/jobs/build
and regular logs. Authorized deployment/data writes use the separate operator
identity and explicit target; read-only legacy scientific inventory uses explicit
legacy project only for the user's approved data preparation. No legacy writes.
The user's new CLI/AGENTS documentation and wrapper remain unrelated local work,
not staged by this continuation. Scheduler remains PAUSED.

The following milestones are historical; the current CTD section above controls
current image, source and next work. Next: normalize/export the retained raw cohort, verify the current cloud publication
dependency graph, and register eligible scientific snapshots with real policy and
a durable cloud-backed store,
then durable catalogue retention/context CRUD and queue/model integrations.

## Latest actual continuation — public beta milestone

Source `6f03f9d37d29b4ebeefc7c7fc35d61bc6ef495cb` and its predecessors
`8e2a163`, `094841c`, `dcde1ef` are pushed to `overhaul`. Accepted application
bytes remain unchanged; deployment wrappers have separate source/evidence.

The independent beta edge is deployed: global Premium IP `136.81.62.56`, one
443 forwarding rule, HTTPS proxy/certificate map, URL map, backend service and
Tokyo serverless NEG. The exact beta certificate is ACTIVE. Child-zone A record
`beta.oceaninfobio.com. -> 136.81.62.56`, TTL300, is publicly resolving. No further
legacy/parent-zone changes occurred. Actual public normal-DNS login is200/TLS
verified, CSS200, wrong hostname403, correct unauthenticated `/v1/runtime`401.
The earlier optional build smoke failed and is preserved; its protected route
was incorrectly `/api/runtime/v1/runtime` (live404), not the actual `/v1/runtime`.
No claim is made that this failed optional smoke passed.

Cloud Run `ocean-v1-beta-serving` has default URL disabled, LB-only ingress,
application authentication, min0/max1 and closed dispatch flags. Frontend-only
revision00003-frs made the login publicly accessible. Generation4 revision00004-prr attached the real API and private SQL proxy.
Generation5 added a deployment-only startup wait for loopback API health before
starting Next, keeping startup CPU allocated until the API is ready while retaining
request billing/min0. Current generation6 revision
`ocean-v1-beta-serving-00006-sd9` is Ready and enables only `ENABLE_V1_SHELL`;
all other ENABLE_V1 flags remain false, authentication remains required. Runtime identity has only the existing three auth/OAuth secret reads,
one exact serving-DSN secret read and instance-conditioned Cloud SQL Client.
[Public edge evidence](../beta/edge-live-20261102/),
[backend attachment](../beta/backend-live-20261102/).

Actual images (all under the beta Tokyo registry except the official proxy):

- `serving-frontend@sha256:db0b822805cd3599abf33a5a05b931a0d05c2c337b87381927b4dc6233eb77e2`, source6f03f9d, successful build6872f1eb. Its14 actual Node HTTP checks pass. The deployment-only adapter removes Cloud Run's redundant RFC Forwarded field only after exact canonical beta transport checks; accepted Next/auth sources stay unchanged. Temporary secret-free diagnostic revision00002 is inactive.
- `serving-api@sha256:28f769ee6b44cb46b10c936f045e609bb83ad9d9bc8ccefa98603801a52157ab`, sourcedcde1ef, builde539fd8a. Config-only layer over accepted APIf2e; root-owned0444 `/opt/ocean/beta-host-config.json`, unchanged source validation, nonrootUID10001.
- Official proxy2.26.3 `gcr.io/cloud-sql-connectors/cloud-sql-proxy@sha256:f333a9c59890c3c67b8505166c5dbdcc0b29fca9173a2e09ca0446ab6997a736`, private IP/loopback5432.

Actual private Cloud SQL qualification succeeded: readback-r2gk5 observed initial
managed ownership; rollback-only qualify-xk4cm found no automatic memberships,
and left the fixed NOLOGIN probe absent. Native failure receipts remain immutable.
A reviewed one-flag `pg_stat_statements.track_utility=off` overlay was applied,
then fresh-session owner/bootstrap receipts verified it. Explicit empty-database
normalization to ownerpostgres succeeded under operator source8e2a163/image
`operator@sha256:0a89057b7459342e191e4b194628bee00cc7544749489df9f85f31508399e7b3`
(buildc6339079). The owner operation's23 guards and independent review passed.

Selected once, actual jobs all succeeded with structured operator completion and
successful provider execution:

- Owner `ocean-v1-beta-db-normalize-owner-rljsn`.
- Bootstrap `ocean-v1-beta-db-bootstrap-mktnv`: vector0.8.5, two restricted LOGIN roles, no memberships.
- Migrate `ocean-v1-beta-db-migrate-wvzh4`: all migrations through0021.
- Finalize `ocean-v1-beta-db-finalize-kbwr5`: exact serving table/column grants verified; no PUBLIC ACL or broad all-tables grant.

[Actual database stages](../beta/sql-20261102/backend-8e2a163/). Do not rerun
these executions, reinstall existing credentials or reset the database. Proxy
shutdown was acknowledged; the previously qualified distinction between provider
successful completion and a separately exposed operator exit line remains.

User selected exactly one verified Google **admin/internal** account for
`dilokkalayakul.jaronchai.p8@dc.tohoku.ac.jp`. Enrollment source8e2a163 and actual
image `enrollment@sha256:65592dada494d70dd5cb13cf923fc4c67172a7aa20648cb6ee5ce1c05f7fa564`
(build634ba0bf) are ready. Genuine Google SDK signature/issuer/audience/email verification succeeded.
One-shot execution `ocean-v1-beta-enrollment-first-account-g58sh` SUCCEEDED; its
structured result and new-connection readback verify exactly one active verified
admin/internal account. Temporary enrollment token accessor was removed and its
version1 destroyed after terminal success. The original unbounded log reader
refused a continuation token; an exact execution-time window found one outcome
and no continuation, recorded as a separate reader amendment. No account retry.
Real browser Google sign-in with that approved account returned to the beta root
and loaded authenticated navigation with the Administrator/Internal account badge.
[Enrollment evidence](../beta/enrollment-20261102/).

The immediate access milestone is complete. Screenshot and browser-observation
receipt are in backend-live-20261102. Research/catalogue are honestly unavailable
without configured services/data; Settings/About and the authenticated shell
are visible. Two temporary bootstrap password accessors were also removed after
all database stages completed. Preserve the working beta and continue remaining
service/data integration and broader checks separately. Scientific/queue/worker
dispatch, broad system/release acceptance and P2 D26-07 remain explicit later
gates. No release tag or complete-platform claim. Historical prospective sections
below must be read against this actual current continuation.

## Accepted software and images

App source `50566b7cfa4a0d8ee19686f0109e74f3a2a45d45` passes all five required
jobs in [CI41322838746](https://github.com/jarondlk/ocean-platform/actions/runs/41322838746):
6747 backend passes/626 explicit skips/83.67% coverage;318 actual PostgreSQL/
16 capability skips plus migration/upsert/backup/restore;132 legacy/1051 prototype/
50 host-unit+1 actual standalone HTTP cases. Coverage threshold remains70%.
The conditional push-only dependency review is skipped as configured.
[Hosted delivery](../beta/checkpoint-20261102/hosted-delivery/delivery.json).

The current880-path app identity is
`sha256:1d3b93f3abbf914d165982a43d4a24f830d975712029e7e5570cb0b868828128`:
841 unchanged accepted paths,3 intentional supersessions and36 additive paths.
5368 prior receipts,90 original C27 artifacts and42 protected paths are retained.
Later deployment wrappers have separate source/evidence; their changes are not
attributed to that earlier hosted app run. P2 D26-07 remains open.

Source-only containers built from packaging `7924a28`:

- Frontend: `asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/frontend@sha256:adb5bc75dbc56d146bdf6e63f83a3dc8b3867b0318de0c2c02ba6fc56023e9dc`
- API: `asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/api@sha256:f2e73ca98ba915e29a4dd7dc429e34a165475faa7f9000bc8cefaa10e5a6ee4f`
- Password-safe8b operator: `asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/operator@sha256:ccd38dae9065b73e89865434123abe07d984af906bf3da626961e727c9a37f3d`

Operator build `e403b44c-e92e-48fa-b94a-6b43d6a84b84` inasia-northeast1
is SUCCESS. Earlier756operator is superseded and must not be executed.
[Actual Linux smoke](../beta/builds-20261102/container-smoke-receipt.json)
for the frontend/API passes; the first failed harness attempt remains preserved.
Operator32pure/26guard/48actual native password-safety evidence and independent
review remain historical accepted local evidence, not CloudSQL qualification.

## Cloud target and financial boundary

Only new beta project `ocean-v1-beta-20261101`, number534831104543, Tokyo
asia-northeast1. Ambient gcloud project remains legacy: **every command must use
an explicit project**. CLI sign-in completed and actual authenticated reads and
reviewed writes succeeded; do not restart sign-in absent a new auth failure.

Beta-only target is¥50,000/month. Notify before exceeding it; the stated¥100,000
upper amount does not remove that notice gate. Saved beta-only all-service¥50k
alert and Cloud Run¥3k cap remain; neither is a whole-project hard cap.
The [31-day bounded public JPY scenario](../beta/quotes-20261102/README.md)
is¥35,604.05 with10% reserve and no credits. Actual usage/tax/invoice are separate.
No always-on worker/model/data acquisition is budgeted.

Private VPC/subnet, registry,4private buckets, initially separate runtime
identities,8initial empty secret containers and PAUSED Cloud Tasks queue exist.
The default Compute identity's automatic Editor was removed only in beta.
The dedicated build account has narrowly scoped source/registry/log access.
No legacy deployment/data/IAM/billing change is authorized.

## Private SQL and installed credentials

Private-only Enterprise PG16 `ocean-v1-beta-sql`, independent DB`ocean_v1_beta`,
Tokyo-zone-a/db-custom-2-7680/ZONAL/SSD20GiB/growth-limit30/private10.93.0.3,
connectorREQUIRED/ENCRYPTED_ONLY/backup7/PITR7/deletion protection are verified.
[Original settings](../beta/sql-20261102/settings-verification.json).

The reviewed logging overlay log_statement=none/log_min_error_statement=panic
was applied once, operationDONE, settingsVersion3/RUNNABLE, unrelated settings
preserved. QueryInsights remains defaultfalse. First preflight stopped on v1 vs
CLI beta4 response representation differences before mutation; the difference
was explicitly qualified and a fresh same-API comparison preceded application.
[Live flag evidence](../beta/sql-20261102/logging-policy/live-20261102/verification.json).
Actual session collector/logging attestation remains required before password SQL.

The reviewed installer successfully created4exact Tokyo secret containers and
installed7coupled versions: auth/internal/bootstrap DSN/migrator DSN/serving DSN/
migrator password/serving password. Only the independent instance's postgres
password was updated after all7versions were retained; UPDATE_USER reachedDONE.
[Metadata receipt](../beta/sql-20261102/setup/live-credentials-20261102.json).
Never rerun the installer, regenerate values or print/read payloads as diagnostics.

Two dedicated DB identities were created with zero user-managed keys, exactly
2instance-conditioned CloudSQL Client memberships and4secret-scoped Accessor
memberships. Unrelated IAM preserved; no project-wide secret access or runtime
Admin/Editor/key grant. [IAM proof](../beta/sql-20261102/iam-jobs-plan/live-20261102/verification.json).

No actual CloudSQL application role/schema migration has run. A limited-creator
native rehearsal exposed a deeper automatic creator-membership/grantor issue;
the proposed ordering-only fix is **not accepted**. Failed run, safe logs and
complete owned-cluster stop/removal are retained under
[bootstrap amendment](../beta/packaging-20261102/operator/bootstrap-order-amendment/).
A source-bound rollback-only qualification stage and finite provider metadata
are being prepared. Preserve strict zero-membership/finalizer checks; do not
weaken them or blindly attempt actual role bootstrap.

Actual Cloud Run validateOnly rejected the first body because job.name must be
empty on create. The owning renderer omits that output-only identity, retaining
external jobId and every other policy. All4corrected bodies received HTTP200 in
new validateOnly responses; no job was created/executed or reconciled by those
requests. Old50/four-case receipts, before-source and failed provider response
remain immutable. New operator source/revision/digest binding is still required.
[Create amendment](../beta/sql-20261102/setup/create-request-amendment/README.md).

## Beta domain and real Google OAuth

The exact child zone `beta.oceaninfobio.com` is delegated to e1/e2/e3/e4
CloudDNS servers. Managed certificate is now **ACTIVE**, exact beta domain
AUTHORIZED, expiry2027-01-30; map entryACTIVE.
[Fresh cert readback](../beta/dns-20261102/certificate-active-20261102.json).
There is no published servingA/AAAA, externalIP/LB/CloudRun service yet.

User specifically approved the single beta NS delegation in legacy project
`data-infra-infobio` / `oceaninfobio-com`, TTL300. It was applied once; four prior
non-SOA sets unchanged, provider SOAserial1→2 with other fields preserved.
[Exact authorization](../beta/dns-20261102/delegation-user-authorization.json),
[preservation proof](../beta/dns-20261102/parent-preservation-proof.json).
This exception does not authorize any other legacy mutation.

User completed Console passkey reauthentication and explicitly approved Google
API Services User Data Policy plus the independent web client and secret storage.
OCEAN Beta app remains EXTERNAL/Testing with0test users. Actual web client
`534831104543-4l3hm9dqd60u320mf73ql0d3s9rsuprn.apps.googleusercontent.com`
has only `https://beta.oceaninfobio.com/api/auth/callback/google` as redirect,
no JavaScript origins. App requests only openid/email/profile. Its secret is
ENABLED numeric version1 in ocean-v1-beta-oauth. It was privately transferred to
SecretManager; the temporary0600file/0700directory were removed, and no secret,
its hash or credential-page screenshot was exported into source/chat.
[OAuth metadata](../beta/oauth-20261102/credential-installation.json).
The browser is on the public Audience/Testing page; tab3 should be retained for
continuation. No genuine beta AppUser has been enrolled and no actual callback/
session exchange is accepted yet. Do not import legacy users or enroll by email.

## Immediate continuation

Root owns cloud mutation. Complete/read-only review the provider metadata and
rollback-only qualification amendment, run its owned native checks with honest
limited-principal results, commit/push the exact source and build an immutable
new operator image. Bind the renderer to that actual revision/digest and existing
numeric secret refs. Do not create or execute stale8b bootstrap definitions.

Use fresh target/IAM/job-operation checks. Create reviewed private job definitions
without running them; verify effective specs/source/SA/network/refs, then actual
readback/rollback-only qualification before bootstrap→migrate→finalize→readback.
Every real stage requires safe source-bound output, successful task/job state
and physical operator/proxy exit evidence. No timeout/retry/reset counts as pass.
Actual provider privacy, limited-superuser/C23 function-owner and managed
migration behavior remain gates until demonstrated.

Complete the concrete hosting plan for one bounded beta frontend/API/privateSQL
proxy service, real OAuth config and enrolled current account, then LB/certmap/
childDNS/HTTPS/defaultURL and cookie/UI checks. API loopback listener stays private;
its source-bound regular config-file and actual startup/probe behavior must be
qualified, not invented. Queue/outbox/private invocation/retained worker
integrations must precede any research/experiment dispatch. Absent scientific
providers report unavailable; no source/data import or scientific approval is
inferred from GCP permission. All20original live release gates and P2 D26-07 remain;
release acceptance is false. Keep unrelated/scientific files unmodified and
excluded from staging. [Cloud checkpoint](../beta/continuation-20261102/cloud-checkpoint.json).
