# v0.7.1 operations

Updated 2026-10-06 JST. **v0.7.1 was published and deployed at 100% traffic
on 2026-10-05 JST.**
Production revision is `ocean-platform-v071-source1005`, schema `20261005_0016`.
The user explicitly deferred live mobile QA; normal role/workflow acceptance passed.

## Accepted candidate evidence

Runtime source `e157fb004871083df25d5d094852fed417a9c8c6`, Cloud Build
`edac2319-6969-4553-9505-182e25a0b017`, was accepted at zero traffic as
`ocean-platform-v071-sourceqa1005b`; that QA revision was removed after rollout. Exact digests, CI and unsuppressed security
dispositions are in [container QA](V0.7.1_CONTAINER_QA_2026-10-05.md).
Later documentation commits do not change that runtime source or its images.

Normal Google admin, viewer and researcher checks passed using the explicitly
approved isolated-role alternative. Read-only final audit verified every original
QA identity/role restored, old histories and scientific content preserved, and no
synthetic review in production. [Live acceptance](V0.7.1_LIVE_QA.md) records actual
403/404/409 enforcement, feedback/history and synthetic review transitions.
No real scientific registry or result was approved.

The user explicitly deferred the remaining live responsive check on 2026-10-05
JST; the viewport override did not change document width. No mobile pass is
claimed. This disposition permits release after the other verified gates.
One transient sign-out error recovered on reload/retry; its cause is unresolved.
Vertex embedding 429s produced safe degraded limitations; retrieval subsequently
recovered without permission, quota or model changes.

## Executed release procedure (retained sequence)

1. The live responsive check is explicitly deferred. Keep
   exact-source CI, image dispositions and candidate acceptance tied to the
   published source; do not label documentation-only commits as the old build.
2. Take a fresh private native production backup into
   `backups/v071/release-20261005` in the existing private data bucket and
   restore-test it in isolation. Remove the restore-test database. Never restore
   into production or copy QA role/review changes into production.
3. Apply only additive reason migration `20261005_0016`; independently verify
   schema, old history hashes, identity/role hashes and scientific corpus/publication
   hashes. A bounded job uses the existing jobs identity, Cloud SQL attachment and
   database secret. Its prepared script is held privately with release records.
4. Derive a zero-traffic canonical revision from the serving production definition.
   Use verified immutable images, normal production database/startup and
   `AUTH_URL=https://oceaninfobio.com`. Preserve IAM, secrets, read-only data mounts,
   external job mode, resources and rollback tags. Do not deploy the QA database
   rewrite as the production startup.
5. Publish/tag the exact tested source after review/CI acceptance and promote the
   verified canonical revision. Check the original question with SST/eDNA, final
   coverage, saved history, anonymous denial and operational health in production.
6. Align affected existing shared API jobs without running manual ingestion,
   embedding, evaluation or research batches. Retain their previous definitions.
7. Remove only the temporary v071 callback, candidate tag/routes, task-owned QA
   jobs and disposable QA database. Preserve private backups under normal retention.
   Close #105 after production regression and #101 after its checks and cleanup.

## Rollback and remaining scope

Retain `ocean-platform-v070-software1005` and original manual-job definitions.
Application rollback keeps additive 0016; do not downgrade by erasing histories
or restore production as a routine rollback.

#104 retains unresolved OS maintenance. #102/#103/#89 retain scientific evidence,
historical SST and six real-data demos. Japanese QA remains outside scope.

## Verified publication, rollout and cleanup

[PR #106](https://github.com/jarondlk/ocean-platform/pull/106) merged as
`7f93fea5390bb0efd1bb0fbca27a0f01dd2e4b8a`. Final branch CI
[37310978832](https://github.com/jarondlk/ocean-platform/actions/runs/37310978832)
passed. Only documentation differs between the merged source and exact runtime
source `e157fb004871083df25d5d094852fed417a9c8c6`; the annotated
[v0.7.1 tag/release](https://github.com/jarondlk/ocean-platform/releases/tag/v0.7.1)
pins that exact built and live-tested source. Operational documentation follows
without retagging or pretending the images were built from the later doc commits.
Final repository Dependabot/code-scanning open-alert queries returned zero; this
is separate from the retained container OS findings in #104.

Fresh backup execution `ocean-v071-preparation-4jpxn` created a 208,268,918-byte
private native backup, SHA-256
`1ec036207a8000a7811effb3abc16db7ac1230405790d50213761c8172ea96b4`.
The isolated restore verified the backup and removed its temporary database.
Backup, manifest and immutable receipts are retained privately under
`gs://data-infra-infobio-ocean-data/backups/v071/release-20261005/`.
No production restore was performed.

Migration execution `ocean-v071-preparation-h4qd5` advanced production from 0015
to additive 0016. Old history hashes, all identity/role hashes, publication bindings
and retrieval corpus hashes were preserved. No synthetic QA review was copied
into production. Canonical revision `ocean-platform-v071-source1005` uses the
verified digests in container QA, normal production startup/database and canonical
auth origin. It served zero traffic before promotion and now serves 100% with
`v071-production` tag. All historical rollback tags remain; temporary
`v071-final` and `v071-candidate` routes were removed.

Normal authenticated canonical Chat repeated the exact reported question with
SST/eDNA selected and no source filters: four SST plus four eDNA final documents,
`overlap_unverified`, abstained, model not run, all eight retained. Post-promotion
read-only execution `ocean-v071-preparation-qlcgj` independently verified the new
normal-admin history record's scope, exact snapshot fingerprint, prompt hash/version,
final coverage and guard/model flags. Original histories, roles, scientific
corpus/publications and absence of synthetic production reviews were verified.
Legacy feedback/history UI also rendered normally. Overview showed 7,319
retrieval documents, 162 CTD casts, 79 SST days and healthy API/database/model
signals with eDNA publication ready. Saving an additional marked
production QA feedback entry was rejected by automatic approval review as an
unapproved persistent production write; no retry or workaround was used. The
read-only history audit supplied verification.

Anonymous protected health/admin/review proxies returned 401; login and provider
discovery returned 200. A bounded deployment-window query for revision HTTP 5xx
returned zero records, not an ongoing availability/SLA guarantee. All five existing
manual jobs pin the verified API digest/source; command, arguments, identity,
secrets, mounts, resource/retry/timeout settings were compared and preserved. No
manual ingestion, embedding, evaluation or research batch was executed. Original
job definitions are retained privately for application rollback.

Cleanup execution `ocean-v071-preparation-l67mm` reverified original QA roles
restored and removed only `ocean_v071_role_qa_1005`; production database and
private backups remain. The three task-owned QA/operator jobs and two untagged QA
revisions were removed. Only the five original manual jobs remain. The temporary
OAuth callback was removed through normal client settings; re-opening verified
exactly the original two callbacks and two origins. Task-owned QA browser tabs
are closed; the canonical app is the user-facing result.

#105's production regression is complete; #101's normal role/workflow checks and
cleanup are complete. Deferred mobile acceptance is tracked independently in
[#107](https://github.com/jarondlk/ocean-platform/issues/107); the transient sign-out
observation remains unresolved in [#108](https://github.com/jarondlk/ocean-platform/issues/108).
#104/#102/#103/#89 remain open for their distinct OS/scientific work. Embedding
429 capacity and representative cohort/load qualification remain limitations; the
observed safe degraded path and later recovery do not prove future availability.

## Post-release dependency audit — 2026-10-06

The final documentation PR's current npm audit flags transitive `source-map-js`
1.2.1 via PostCSS, [GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q)
/ CVE-2026-93749. This later registry result does not rewrite the release-time
CI/image reports or prove an exploited request path. Dependabot's open-alert
query remained empty; npm audit is still enforced.

[PR #111](https://github.com/jarondlk/ocean-platform/pull/111) merged the
maintainer-supported 1.2.2 pin with unrelated lockfile metadata preserved. Clean
install/audit (zero production dependency findings), all 64 existing frontend
tests, typecheck and build passed. Its required CI and merged-source status are
recorded in that PR. This is a separate post-release runtime dependency change,
not part of v0.7.1's immutable tag/images. [#110](https://github.com/jarondlk/ocean-platform/issues/110)
stays open until exact patched images are verified and deployed under a new
patch release. The CLI login expired after the completed v0.7.1 rollout and must
be refreshed before further cloud work. The final documentation PR is rebased
after the security fix so its required audit can pass without suppression.

The [2026-10-06 pre-deployment audit](PRE_DEPLOYMENT_AUDIT_2026-10-06.md) updates
current operating indexes and reviews maintained versus historical scripts. Its
readiness/CLI/build fixes belong to the next patch; they do not alter the v0.7.1
release source or images.
