# v0.7.2 operations

Published and deployed on 2026-10-06 JST at [oceaninfobio.com](https://oceaninfobio.com).
Production was confirmed at 100% on `ocean-platform-v072-patch1006` at
05:54:28 UTC. Post-cutover preservation/history verification completed at
05:56:38 UTC; final resource/configuration/cleanup checks passed.

## Immutable source and images

The published [v0.7.2 tag](https://github.com/jarondlk/ocean-platform/releases/tag/v0.7.2)
pins runtime source `03638e653f998902545b2ca19f902f1253718de8`.
The annotated tag object is `001cf67541ca372c4e51c36f96cc4edbe5ee66a7`.
PRs [#111](https://github.com/jarondlk/ocean-platform/pull/111),
[#112](https://github.com/jarondlk/ocean-platform/pull/112) and
[#113](https://github.com/jarondlk/ocean-platform/pull/113) merged with passing
required CI and CodeQL before publication. Neither v0.7.1 nor v0.7.2 was retagged.
Subsequent operating-document/verifier commits do not change deployed images.

The unchanged `git archive` source was 22,004,289 bytes, SHA-256
`e682c4e71881c85fedc7f218a3600e10cdd9ae1f628e7c9e689c9aea638f9e62`.
Cloud Build `304a2a15-50d4-40e8-868e-2ed9dc80dcb7` passed source gates;
`c1cd93e0-571e-414a-a15c-8c103ddac103` passed all seven build/runtime/scan steps.
An earlier submission was canceled to correct its timeout to 40 minutes.
The first combined build hit a PostgreSQL socket-readiness race before app
validation; the successful retry used TCP readiness in the verification step
only. See [complete container QA](V0.7.2_CONTAINER_QA_2026-10-06.md).

Registry prefix: `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform`.

| Container | Accepted and deployed digest |
| --- | --- |
| API | `sha256:0807a4229f52719d53bb9fc5c2b838ecb451e71e67e0cc7331b33f982331522a` |
| Frontend | `sha256:4ce4ba1c71fa9cb9672b4f51c171aa3ea02ee1a5396d580aea63f8b324c526ee` |

Installed standalone frontend source-map-js independently reports **1.2.2** and
application version 0.7.2. Full scan/image-configuration bindings were verified;
no Python/Node vulnerability groups were reported. OS finding tuples are
unchanged from v0.7.1, including eight distinct high CVEs. #104 stays open for
supported stable fixes and remaining medium/low/unknown review; this is not a
clean-image claim. The full reports remain private in the QA prefix in that record.

## Fresh inventory, private backup and preservation

Fresh CLI/Console checks confirmed project `data-infra-infobio`, region
`asia-northeast1`, active Cloud Run/SQL, private bucket protections and billing.
Console budget alerts remained Cloud Run JPY 2,250, SQL JPY 4,000 and project
JPY 10,000; displayed month-to-date Cloud Run spend was about JPY 61.89 and
SQL/project after-savings totals were zero. Billing can lag; alerts are not
spending caps. SQL disk had automatically grown to 15 GiB (20 GiB growth limit),
with about 2.56 GB used and 15.74 GB quota reported before the restore test.
No budget, IAM, capacity, identity or secret changes were made by this rollout.

With explicit user approval, temporary job `ocean-v072-verification` used the
existing jobs identity/database secret, one task, no retries, CPU 1/memory 2 GiB,
15-minute limit and read-only scientific-data mount. Its non-serving CLI runtime
used test environment validation without receiving the frontend signing secret;
serving authentication remained production/required throughout.

Execution `ocean-v072-verification-9b5lw` completed at 05:42:04 UTC. The full
private native backup includes account/history data and was restored only into
a disposable same-instance database, independently checked and removed. No
production restore or migration ran. Retained backup prefix:
`gs://data-infra-infobio-ocean-data/backups/v072/release-20261006/`.
Backup size **208,284,556 bytes**, SHA-256
`5325af9d012ab12ef091646363d28925f5819815caeda992de5fec60cd7cea38`.
The private prefix also retains baseline and candidate/production receipts.

Independent checks passed with all 34 required tables, vector extension,
no missing required columns and actual/expected head `20261005_0016`.
Original completed/failed history hashes, identities/roles, publications,
retrieval content, immutable counts and embeddings were preserved. Corpus:
7,319 documents/embeddings, including 6,996 eDNA, 162 CTD and 79 SST documents;
3,498 ANEMONE occurrences/assays, 349,638 assignments and 13,932 standards.

## Candidate and production acceptance

Read-only corpus execution `ocean-v072-verification-t5xdd` passed all 16 source
selections, source-aware budgets and future-empty scopes. The two-source pooled
probe supplied SST only; per-source retrieval supplied four SST and four eDNA
records and reported `overlap_unverified`. Six latency probes were single
samples, not an SLA or benchmark. ANEMONE filter choices were populated from
PostgreSQL, with bounded/searchable sample and taxon choices. Real analysis
choices remain unavailable without approved publications.

Normal Google admin/internal sign-in and sign-out passed on zero-traffic
`ocean-platform-v072-qa1006`, using the explicitly approved temporary callback.
Existing admin feedback/history records rendered, including a legacy v2 prompt
record. No QA feedback was added or edited. Candidate history audit execution
`ocean-v072-verification-q8wpm` passed.

The canonical revision was separately checked at zero traffic, then promoted.
Normal canonical Google admin sign-in, sign-out and re-login passed. Overview
reported API/database/model runtime healthy and eDNA publication ready. Source
selection remained SST/eDNA on return. The reported question, “Where do ANEMONE
sampling dates and locations overlap with available SST observations?”, supplied
four documents per source, abstained with `overlap_unverified` and ran no model.
Execution `ocean-v072-verification-r2zss` independently verified the post-cutover
saved interaction, exact evidence fingerprint and v5 prompt hash, scope, outcome,
model-not-invoked metadata and preservation baseline. No new scientific cohort
or real overlap/non-overlap result was approved. This patch did not repeat fresh
viewer/researcher QA; prior v0.7.1 isolated normal role acceptance is retained.

Six anonymous checks passed on candidate, canonical zero-traffic revision and
production: login/providers 200; protected health/admin/review/analysis routes
401. Final log query returned no Cloud Run ERROR records over its 24-hour window;
that bounded query does not establish absence of all possible failures.

## Job alignment, cleanup and rollback

All five existing manual jobs (`ocean-anemone-process`, `ocean-embedding`,
`ocean-evaluation`, `ocean-migrate`, `ocean-pipeline`) now pin the accepted API
digest and runtime source 03638e6. Independent comparisons confirmed commands,
arguments, identities, secret references, mounts, retry/time/resource limits
and other settings unchanged. No original batch job was executed.

Final serving configuration matches the fresh original definition except images,
source metadata and revision name. Canonical AUTH_URL/CORS, required auth,
read-only API mount, external job mode, min zero/max one, concurrency 20 and
original CPU/memory limits are preserved. Project IAM matches the before receipt.

Cleanup removed only the v072 candidate/final tags, QA revision, temporary
verification job and disposable restore database. The approved temporary OAuth
callback was removed; reopening the client confirmed its original two origins
and two callbacks. Secrets/accounts/roles were unchanged. Temporary browser
previews were closed; the canonical user tab remains available. Private backups
and complete QA reports are retained. `v072-production` and every prior rollback
tag remain.

Compatible application rollback is `ocean-platform-v071-source1005`, with its
original job definitions retained privately. Keep additive schema 0016 and later
history; do not restore production or downgrade populated migrations for a
routine image rollback. [v0.7.1 operations](RELEASE_0.7.1_OPERATIONS.md) retains
its immutable image/configuration evidence.

## Remaining work

#110 is resolved by the verified source-map-js 1.2.2 production rollout.
#104 remains open for OS maintenance; #108's sign-out cause is unresolved despite
fresh passing checks. Live mobile QA stays explicitly user-deferred (#107).
Scientific/provider evidence (#102), approved historical SST (#103) and the six
real research demos (#89) remain open. Their prior deferrals are unchanged.
