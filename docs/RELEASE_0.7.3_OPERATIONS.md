# v0.7.3 operations

Published and deployed on **2026-10-07 JST** at
[oceaninfobio.com](https://oceaninfobio.com). Revision
`ocean-platform-v073-patch1007` is Ready and serves 100% of traffic.
Independent post-promotion verification completed at **12:32:47 UTC**.
This is a software release; historical SST scientific publication remains pending.

## Immutable source and images

[v0.7.3](https://github.com/jarondlk/ocean-platform/releases/tag/v0.7.3)
pins runtime source `f65efdf0c90595ff129fbe66a193ffd231797bd5`.
Overview [#116](https://github.com/jarondlk/ocean-platform/pull/116), historical
SST tooling [#115](https://github.com/jarondlk/ocean-platform/pull/115), and
version/notes [#117](https://github.com/jarondlk/ocean-platform/pull/117) merged
with all eight PR checks passing. The combined implementation also passed 56
focused local tests. Later documentation commits do not change these images or tag.

Cloud Build `61c0513f-10ac-459b-b68c-b7e9d37005aa` completed successfully at
12:13:27 UTC. All nine source, build, synthetic PostgreSQL migration/restore,
runtime and unsuppressed scan steps passed. The exact source archive was
22,118,195 bytes, SHA-256
`c5bfd9d253d5d0047bdfc7397352cca19e08665c8f94491e1a81aa515a4fcabd`.

Registry: `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform`.

| Container | Accepted and deployed digest |
| --- | --- |
| API | `sha256:d94548fb5411cf0a43d1030aab07fd4b1657e2a058bf32f0e1065abcc79ffb57` |
| Frontend | `sha256:5dc9c2c12018b50dbb73edb3181148fd78c82e3a6e46c7187a584f0e31d39667` |

Standalone application version is 0.7.3, source-map-js 1.2.2 and sharp 0.35.5.
Numeric/NetCDF imports, all 34 required tables and schema head `20261005_0016`
passed. Runtime UIDs are 999/1000 with zero effective capabilities; installation
tools and unused affected CLI/setuid paths are absent.

Full scans have no critical or reported Python/Node findings. There are **no
added or removed finding tuples compared with the preceding deployed Overview
images**. API retains HIGH 44 / MEDIUM 60 / LOW 82 / UNKNOWN 2 finding records;
frontend retains HIGH 43 / MEDIUM 58 / LOW 60 / UNKNOWN 2. These are finding
records, not distinct CVE counts. #104 remains open; this is not a clean-image
claim. Image-bound runtime and scan reports are retained privately at
`gs://data-infra-infobio_cloudbuild/v073-qa-20261007/61c0513f-10ac-459b-b68c-b7e9d37005aa/`.

## Backup, inventory and preservation

Fresh CLI/Console inventory verified project `data-infra-infobio`, region
`asia-northeast1`, Cloud SQL `ocean-postgres` / `ocean_platform`, billing, private
storage and existing identities. Displayed Cloud Run spend was about JPY 197.66;
configured alerts remained Cloud Run JPY 2,250, SQL JPY 4,000 and project JPY
10,000. Billing can lag; alerts are not spending caps. SQL allocated disk remains
15 GiB with a 20 GiB growth limit; pre-rollout used bytes were 2,559,082,496.
No IAM, budget, capacity, identity or secret change accompanied this rollout.

With explicit user approval, temporary job `ocean-v073-verification` used the
existing `ocean-jobs` identity/database secret: one task, no retries, CPU 1,
memory 2 GiB, 15-minute limit and read-only scientific-data mount. Its non-serving
CLI validation used a test environment without the frontend signing secret;
serving authentication remained required throughout.

Backup execution `ocean-v073-verification-2xd6h` passed at 12:26:28 UTC. The full
private backup includes account records and Chat history and was restored only
into a disposable database on the same instance, verified and removed. No
production restore or migration ran. Backup size **208,771,709 bytes**, SHA-256
`ce4e7d00501e4bc7096144a0aa23a451a5792aab433bf0799f5711b3c0fcf8df`.
Private prefix: `gs://data-infra-infobio-ocean-data/backups/v073/release-20261007/`.
It also retains baseline, retrieval and candidate/production verification receipts.

Independent read-only checks preserved all original completed/failed Chat history
hashes, accounts/roles, publication identifiers, retrieval content, table counts,
scientific artifact bytes and Overview coverage. Corpus remains 7,319 documents
and embeddings, including 6,996 eDNA, 162 CTD and 79 SST documents. ANEMONE remains
3,498 source occurrences/assays, 349,638 assignments and 13,932 standard records.
No scientific cohort, SST panel or historical publication was created.

## Candidate and production acceptance

Normal invited Google admin/internal sign-in passed on zero-traffic
`ocean-platform-v073-qa1007`, using the explicitly approved temporary callback.
Existing admin feedback/history rendered; no feedback was added or edited.
Candidate history/preservation execution `ocean-v073-verification-vc9wx` passed
at 12:28:50 UTC. Candidate sign-out was attempted after its traffic tag had been
retired and is not counted as a valid sign-out acceptance check.

Read-only retrieval execution `ocean-v073-verification-tbf2c` passed at 12:27:46
UTC: all 16 source selections, bounded budgets, future-empty scopes and populated
filter choices. Six paired samples are bounded diagnostics, not an SLA estimate.
The actual browser overlap question supplied **four SST and four eDNA documents**,
abstained with `overlap_unverified` and did not invoke the model. The SST-only
February 2026 question generated an answer with 25 valid citation references,
zero invalid references and zero warnings, explicitly treating the unavailable
station mean as missing and limiting other-date claims to retrieved evidence.
Citation checks do not verify arbitrary scientific claims.

Overview reported healthy API/database/model runtime and expected counts:
CTD 162 casts, metagenome 82 samples, eDNA 3,498 source occurrences and SST 79 days.
All-source shared-month coverage is empty; disabling eDNA yields three shared
months. Refresh, checkbox selection and keyboard month selection worked.
The February 2026 SST detail identifies six missing dates, February 14–19.
Shared months do not establish matched samples or spatial overlap.

The canonical-auth revision was checked separately at zero traffic, then
promoted after acceptance. Protected endpoints, including Overview coverage,
returned 401 anonymously. Normal canonical Google admin sign-out, protected-route
redirect and re-login passed. The production overlap question again supplied
four records per source and safely abstained without generation. Independent
execution `ocean-v073-verification-f5kvt` verified its saved history, exact evidence
fingerprint, prompt v5/hash and preservation baseline. Its query time boundary
was after promotion, so candidate records could not satisfy this production gate.
Fresh inventory reported no ERROR entries for the new serving revision.

Fresh viewer/researcher role changes or mobile workflow acceptance were not part
of this software rollout. Prior isolated role acceptance remains dated v0.7.1
evidence; #107 remains explicitly user-deferred. Successful production sign-out
does not close the intermittent cause investigation in #108.

## Cleanup and compatible rollback

Temporary OAuth callback, verifier job, QA revision and restore database were
removed. Only the original canonical/fallback OAuth callbacks remain. The
temporary final tag was replaced by `v073-production`; all original rollback
tags remain. Private backups, build/scan receipts and historical archives remain.

Five existing manual jobs use the accepted API image/source metadata with
commands, identities, secrets, mounts, limits and retry settings preserved;
none was executed. All six original jobs remain. The superseded
`ocean-sst103-historical-acquire` definition/archive was left unchanged and was
not executed. Historical local acquisition was not restarted.

Immediate compatible application rollback is `ocean-platform-overview1007b`
(`overview-production`), with earlier versioned rollback tags retained. Reassign
traffic to a verified compatible revision; do not downgrade schema 0016 or
restore production merely to undo an application image update. Restore is a
separately reviewed recovery operation and must preserve newer history.

## Remaining scientific work

#103 stays open. The private NASA context acquisition retained 2,554 files:
2,521 final and 33 interim, with 35 explicit unsupported final-series dates
including the two excluded February 2021 dates. Coarse 0.05-degree grid-point
subsampling is not native sample-area evidence. Native patches await qualified
provider recovery. Final-only review staging is implemented and was tested to
reject unapproved input before a database write; it is not scientific publication.

#102 environmental eligibility, physical sample/assay identity and area evidence,
and #103 product/generation, masks/uncertainty/QC, spatial weighting and time
acceptance require actual researcher review/admin application. Controlled
normalization, linkage/publication, historical Chat acceptance and the six real
demonstrations in #89 remain pending. See
[the integration handoff](HISTORICAL_SST_CONTEXT_INTEGRATION_2026-10-07.md).
