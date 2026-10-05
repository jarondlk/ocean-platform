# v0.7.1 operations

Prepared 2026-10-05 JST. v0.7.1 is not published or promoted. Production remains
100% on `ocean-platform-v070-software1005`, schema `20261004_0015`.

## Accepted candidate evidence

Runtime source `e157fb004871083df25d5d094852fed417a9c8c6`, Cloud Build
`edac2319-6969-4553-9505-182e25a0b017`, is deployed at zero traffic as
`ocean-platform-v071-sourceqa1005b`. Exact digests, CI and unsuppressed security
dispositions are in [container QA](V0.7.1_CONTAINER_QA_2026-10-05.md).
Later documentation commits do not change that runtime source or its images.

Normal Google admin, viewer and researcher checks passed using the explicitly
approved isolated-role alternative. Read-only final audit verified every original
QA identity/role restored, old histories and scientific content preserved, and no
synthetic review in production. [Live acceptance](V0.7.1_LIVE_QA.md) records actual
403/404/409 enforcement, feedback/history and synthetic review transitions.
No real scientific registry or result was approved.

The remaining live responsive check requires a narrower rendered browser; the
viewport override did not change document width. Do not infer a mobile pass.
One transient sign-out error recovered on reload/retry; its cause is unresolved.
Vertex embedding 429s produced safe degraded limitations; retrieval subsequently
recovered without permission, quota or model changes.

## Prepared release procedure

1. Complete or explicitly dispose of the remaining live responsive check. Keep
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
