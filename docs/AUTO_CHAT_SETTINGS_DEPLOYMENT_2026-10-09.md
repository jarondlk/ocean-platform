# AUTO settings deployment record — 2026-10-09 JST

Status: **deployed and verified** at <https://oceaninfobio.com>.
Project `data-infra-infobio`, region `asia-northeast1`, service `ocean-platform`.
Revision `ocean-platform-auto-settings1009c` has 100% production traffic and tag
`auto-settings-production`. The prior `ocean-platform-v075-patch1008` revision and
`v075-production` tag remain available for application rollback.

The user authorized deployment with usable CLI authentication, including backups
and resource creation. Authentication expired during preparation, so deployment
was deferred. After the user completed browser sign-in, validation and rollout
resumed. Failed, superseded and diagnostic attempts were not used as final-image
acceptance. No production database migration, restore or scientific publication
was performed.

## Source and images

Application source: `6083225e7d01872b6714c1a619af840b1ee26ce8`, branch `auto-setting`.
Cloud Build: `174b81d3-6992-48dd-8ce0-ffd55d0b579e`, all seven gates successful.
The build used a frozen clean Git archive; subsequent commits update documents.

- API: `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/api@sha256:adb67b5840eafa0c9d2b72329ce6939e75c79742d865705ceb3e162c55ae52c4`.
- Frontend: `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/frontend@sha256:474ebc02c4d5f8af3a8428a091924d01fade6e5d48e9ab5d1a228bbc9e26cac3`.

The unchanged frontend reuses the verified image from source
`07eb4588dadbe249a0cfd6822e745f13222ce028`, build
`da33d0dc-1ff4-4549-b00d-b7d6f4af1fd9`. Git comparison confirms the frontend tree
matches the final application source. Each container retains its actual source
in `SOURCE_COMMIT`; they are not labeled with the same commit artificially.

AUTO is opt-in per account in the chat settings toolbar. The independent planner
call precedes evidence retrieval and the answer flow. Confirmed analysis,
dataset and protocol choices remain pins. Supported routes are scoped RAG,
exact published workflows, published synthesis using verified result packets,
and deterministic SST coverage. Exact/coverage routes do not invoke the main
answer model. Planner and main model have independently configurable model IDs;
this rollout uses the existing Vertex `gemini-3.6-flash` for both calls.
Planner timeout is 30 seconds, output budget 1,600 tokens, and one attempt.
Main model and embedding configurations remain preserved.

## Validation

Final source gates passed lint, generated-scope freshness and **1,313 backend
tests**, with **49 optional tests skipped**. The latest focused local run passed
99 planner/runtime/source-scope tests. The frontend's verified 78-test suite,
typecheck, production build and audit were reused with its unchanged image.
Skipped tests are not counted as passing.

Container gates independently verified PostgreSQL 16 bootstrap/readiness and
isolated backup/restore, runtime imports, numeric fixtures and NetCDF support,
non-root execution, absence of installation tools, and authentication HTTP
behavior. Full unsuppressed API/frontend scan reports were collected and reviewed.

Exact-image live acceptance `ocean-auto-settings-qa1009-wdjct` passed all cases
against the real Vertex models and retained science data:

| Case | Applied route | Main model invoked | Total chat time |
| --- | --- | --- | --- |
| MUR SST Miyagi 2020–2023 coverage, gaps, resolution and limitations | `sst_coverage` | No | 40.03 s |
| Top 10 fish detection frequency, yearly and seasonal changes | `published_exact` | No | 32.45 s |
| High/low SST frequency comparison and representative series | `published_exact` | No | 33.87 s |
| Interpretation and limitations of published comparisons | `published_synthesis` | Yes | 34.20 s |
| CTD salinity in Onagawa during 2024 | `rag` | Yes | 26.53 s |

These are observed total handler durations, not planner-only latency guarantees.
The original three Miyagi questions used the selected MUR dataset, published
Miyagi 3NN analysis and MiSeq paired protocol as applicable. Coverage retained
1,455 supported days out of 1,461, with six gaps. All five responses were answered
with applied plans and zero invalid citations. The operator also checked
completed per-user history, requested/effective settings, source/prompt
fingerprints, preserved pins and manual all-off abstention.

The operator restored the verified backup into a disposable database before
application imports, then called the actual chat handler with unmodified
application logic. A wrapper only recorded planner output. It wrote no production
chat history; its temporary database was removed. The earlier patched-image
five-case diagnostic `ocean-auto-settings-qa1009-f6lpt` also passed and removed
its database, but was not substituted for final immutable-image acceptance.

Before and after promotion, candidate/canonical HTTP checks passed: login and
Google provider discovery return 200; protected analysis-options, stats and
research-registry-reviews return 401 anonymously. Mock login remains disabled.
Final service inspection verified 100% traffic, image/source pins and rollback
retention. Browser sign-in and cross-role browser flows were not evaluated.

## Live-data fixes

Preparation exposed and corrected:

- A missing-local-SST recovery path: only absence (404) falls back to verified
  retained days; other failures still propagate. The initial failed build was
  not accepted.
- An oversized production catalogue: published protocol membership filtering
  and compact descriptions reduced it from 41,118 to 19,757 characters. Full
  manual metadata, identities, recipes and scientific limitations remain.
- Vertex rejection of the full generation grammar: the smaller generation
  schema works while strict Python proposal/scope validation stays authoritative.
- Omitted confirmed pins: the server restores analysis/dataset/protocol pins,
  rejects conflicting IDs and records their provenance separately.
- Omitted literal calendar ranges: planner version `auto-settings-v5` preserves
  supported inclusive year ranges and explicit ISO dates from the question,
  rejecting conflicts. The helper does not infer relative, excluded, reversed
  or ambiguous periods.

Earlier builds passed on `4f061c5` (1,293 backend tests), `07eb458` (1,296), and
`346a9ff` (1,297), each with 49 optional skips. Superseded images and planner-only
preflights were diagnostic evidence. The `346a9ff` full live run stopped on the
omitted calendar range and removed its database; final source fixes that failure.

## Backup and preservation

Execution `ocean-auto-settings-backup1009-wkxf9` created a full private PostgreSQL
backup, restored it into a temporary database, verified it and removed the
restore database. Archive size: 209,773,369 bytes; SHA256:
`89033b38ad568dd6ce4c452cdf10a31fd8b510c7ee0b2c40d5d5a072bde7aab0`.
Backup, manifest, baseline and receipts are retained at:
`gs://data-infra-infobio-ocean-data/backups/auto-settings/deploy-20261009-0b4a33f/`.
Schema remains `20261005_0016`, 34 tables.

Post-promotion preservation execution `ocean-auto-settings-preserve1009-4f48m`
passed read-only comparisons of original accounts/roles, original terminal chat
history, corpus publications, retrieval/embedding provenance, retained scientific
artifacts and regional publication. No production restore or migration occurred.

The first preservation check required the account set to be exactly equal and
failed because a new account had appeared since the backup. Read-only diagnosis
found zero changed or missing original accounts, zero changed original terminal
history and no scientific differences. Counts changed only for one new account
and ordinary chat/audit/rate-limit activity. The corrected operator requires all
original account hashes to remain unchanged and reconciles account-count growth
exactly to new identities; it does not weaken original-record checks or rewrite
the baseline. The failed check was not counted as passing.

Secrets, IAM, read-only data mounts, Cloud SQL bindings, canonical auth/CORS
settings, and existing min0/max1/concurrency20 capacity were preserved. Five
existing manual runtime jobs were aligned to the accepted API image/source;
commands/settings stayed unchanged and none of their commands were executed.
Superseded acquisition job definitions and the paused follow-up remain intact.

## Scans and remaining limits

Final scans report no CRITICAL or language-package findings. Existing tracked
OS findings remain unsuppressed: API HIGH44/MEDIUM62/LOW82/UNKNOWN1; frontend
HIGH43/MEDIUM58/LOW60/UNKNOWN1. No new vulnerability/package/version tuple was
introduced relative to the reviewed preceding build. The scanner reclassified
`CVE-2026-107161` on two unchanged SASL packages from UNKNOWN to MEDIUM. Exact-image
live QA verified the DIGEST-MD5 plugin is absent; no corresponding application
path was found. Findings remain in the existing #104 runtime follow-up, without
an independent exploitability guarantee.

AUTO remains opt-in. Five English cases do not establish general planner quality
for Japanese, paraphrases, unsupported qualifiers or ambiguous publications.
Citation validity is not verification of every generated scientific claim.
Mixed raw/published hybrid routing and a general geographic resolver remain
outside the implemented scope. Budget read permission returned 403 during the
initial audit; actual budget headroom was not verified and no permanent capacity
increase was made.

## Cleanup and rollback

Temporary backup/QA/preservation jobs, the candidate tag, and the two superseded
zero-traffic revisions were removed. Private backups, acceptance reports, the
accepted production revision, prior production rollback and historical tags
remain. Final inspection retains the seven pre-existing manual/acquisition jobs.
No automatic retry or scheduled deployment was created.

For application rollback, return service traffic to
`ocean-platform-v075-patch1008` and restore manual job image/source pins from their
saved pre-rollout definitions if needed. Do not restore scientific data as an
application rollback. Private local operational scripts and configurations are
at `/private/tmp/ocean-auto-setting-deploy-20261009`; this temporary directory is
not durable storage and must not be committed. The cloud backup and
`deployment-receipt.json` beside it are durable recovery references. Build reports
are under
`gs://data-infra-infobio_cloudbuild/auto-settings-qa-20261009/174b81d3-6992-48dd-8ce0-ffd55d0b579e/`;
final QA reports are under
`gs://data-infra-infobio-ocean-data/auto-settings/qa/6083225e7d01872b6714c1a619af840b1ee26ce8/ocean-auto-settings-qa1009-wdjct/`.
