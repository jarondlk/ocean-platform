# AUTO fresh-selection correction — 2026-10-09 JST

This is a historical accepted AUTO rollout record. The later
[v0.7.6 operations](RELEASE_0.7.6_OPERATIONS.md) supersede its production-traffic
and immediate-rollback statements; recorded source, receipts and tests remain.

Status: **deployed and verified** at <https://oceaninfobio.com>.
Revision `ocean-platform-auto-settings1009e` serves 100% of production traffic.

## Corrected behavior

A fresh question could leave the published analysis, workflow and assay controls
empty. The initial acceptance run used manually pinned choices, which did not
exercise this failure. Unpinned planning treated both Miyagi assignment variants
and the available assays as unresolved choices.

Planner version `auto-settings-v6` now resolves supported complete workflow
questions against the verified published catalogue. For the exact question
“Show the top 10 fish by detection frequency, with yearly and seasonal changes”,
it selects the current MUR v4.1 Miyagi 2020–2023 `qcauto_95pct_3nn_target` analysis,
`fish_frequency` workflow and the first listed eligible assay. In the current
publication that assay is **12S rRNA · NextSeq500 · paired**. An explicit
**MiSeq paired** request selects that protocol instead. Existing user pins and
requested instrument/layout/gene constraints take priority. Protocol results
remain separate; the default does not pool assays.

The assignment default applies only to method variants with the same verified
publication ID, region/cohort scope and period. Different publications or cohorts
still require clarification. Unsupported explicit assay choices, conflicting
pins, changed fixed species panels and incompatible dates are rejected.

The high/low SST comparison selects its workflow, the same publication and its
linked MUR dataset. The original MUR coverage question resolves to the verified
SST catalogue even when raw-data filter facets are absent. A dataset outside that
catalogue is rejected. Complete known aliases have a validated catalogue mapping;
other wording continues through structured planning and validation. Provider
errors and malformed planner output remain visible failures.

The existing frontend already renders effective settings returned by the API.
A new mounted regression test verifies all three native select values, keeps
manual settings separate, and checks that a subsequent AUTO request does not
silently pin the previous automatic choices.

## Build and validation

Final application source: `49950fba07a67535f5a0de95d04837296c1f5497`, branch
`auto-setting`. Cloud Build: `2315acac-9eec-40ff-8e14-bd17ffbe454a`; all seven
gates passed. Backend: **1,337 passed, 49 optional skips**. Frontend: **79 tests
passed**, including the new mounted controls test; TypeScript check passed.
Lint and generated-scope freshness passed. Container gates verified runtime
imports, PostgreSQL 16 bootstrap and isolated backup/restore, NetCDF fixtures,
non-root execution, installation-tool absence and authentication behavior.

API image: `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/api@sha256:59738ba7b69d861f500a053ecc7d8a27c0773f14c171381dd5c7fd4d7f8d07db`.
Frontend image: `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/frontend@sha256:474ebc02c4d5f8af3a8428a091924d01fade6e5d48e9ab5d1a228bbc9e26cac3`.
The frontend runtime tree is unchanged from source `07eb4588dadbe249a0cfd6822e745f13222ce028`;
only a test file differs. Its actual source pin remains unchanged. Subsequent
documentation commits do not change the deployed application source.

Full unsuppressed scans introduced no new finding tuple relative to the reviewed
preceding images: no CRITICAL or language-package findings. Existing OS counts
remain API HIGH44/MEDIUM62/LOW82/UNKNOWN1 and frontend
HIGH43/MEDIUM58/LOW60/UNKNOWN1. These remain tracked runtime findings; passing the
scan review is not a guarantee of absence of vulnerabilities.

An initial v6 full-answer run exposed an unpinned MUR dataset constraint failure.
The correction also verified dataset identity against the publication catalogue
rather than requiring a raw-data facet. The intermediate coverage build was
cancelled after its local regression failed; neither attempt was promoted.
An independent read-only real-model preflight passed five planning paths,
including the exact fresh question, explicit MiSeq, high/low SST, interpretation
and CTD. It does not replace final-image full-answer acceptance.

## Final-image live acceptance

Execution `ocean-auto-settings-v6-qa1009-wggvt` passed the actual chat handler
against the real Vertex planner/main models and a disposable restored database.
It uses unmodified application logic; an observer only records planner output.
No production chat history was written. All eight cases were answered with
applied plans, expected choices/routes and zero invalid citations:

| Case | Applied route | Main model invoked | Total handler time |
| --- | --- | --- | --- |
| Fresh MUR coverage, all sources off | `sst_coverage` | No | 33.52 s |
| Exact reported fish question, no analysis/workflow/assay pins | `published_exact` | No | 32.35 s |
| Fresh high/low SST comparison, all sources off | `published_exact` | No | 29.77 s |
| Fresh fish question explicitly requesting MiSeq paired | `published_exact` | No | 30.23 s |
| Fresh interpretation of published SST comparisons | `published_synthesis` | Yes | 34.13 s |
| Fresh CTD salinity in Onagawa during 2024 | `rag` | Yes | 31.41 s |
| Fish question with manually pinned Miyagi/MiSeq/MUR | `published_exact` | No | 30.00 s |
| High/low SST with the same manual pins | `published_exact` | No | 30.43 s |

The reported fish question's manual snapshot enabled all sources but contained
no published selection pins. Fresh high/low and coverage snapshots had all
sources off. Offline tests also cover the fish question with all sources off.
Coverage retained 1,455 supported days of 1,461 and six final-series gaps.
Completed per-user history, scope immutability, prompt/source fingerprints and
protocol/default metadata were checked. Explicit MiSeq uses its own result rows.

Three additional requests correctly abstained without main-model generation:
a changed top-five panel, unavailable NovaSeq protocol, and incompatible 2024
period. The manual all-off request also abstained without invoking the planner.
The disposable database was removed and its acceptance receipt retained privately.
Exact-image QA verified the SASL DIGEST-MD5 plugin is absent; this is a bounded
runtime check, not a general exploitability assurance.

## Rollout and preservation

The accepted immutable API was deployed without production traffic, verified,
then promoted after final-image acceptance passed. Candidate and canonical HTTP
checks passed: login/Google discovery return 200; protected analysis-options,
stats and research-review endpoints return 401 anonymously. Mock login remains
disabled. Image/source pins and 100% traffic were inspected after promotion.

Read-only preservation execution `ocean-auto-settings-v6-preserve1009-vffbb`
passed. Original accounts/roles/history, corpus publications, retrieval provenance
and retained scientific artifacts match the pre-rollout baseline. No new accounts
appeared during this rollout. Production schema, secrets/IAM, auth/CORS, mounted
data, model settings and min0/max1/concurrency20 capacity were preserved.
Five existing manual jobs were aligned to the final API image/source; full
configuration comparison confirms their commands and settings were preserved.
None of those commands was executed. Acquisition jobs remain unchanged.

The prior `ocean-platform-auto-settings1009c` revision is retained under
`auto-settings-previous`; the original `ocean-platform-v075-patch1008` and
`v075-production` tag are also retained for application rollback. Private backups
and validation reports remain available for recovery/audit. Final inspection
verified removal of all four temporary jobs, the candidate tag and the superseded
zero-traffic `1009d` revision. Durable `deployment-receipt.json` is retained beside
the v6 backup. Production and rollback revisions remain intact.

## Backup

A new full private PostgreSQL backup was restored and verified before candidate
validation; the disposable restore database was removed. Archive: 209,983,471
bytes, SHA256 `f92d0baa240165e1338947f43b892c7021a76eb7d9233bd5d4321589af54fe52`.
Backup/manifest/baseline receipts are retained under
`gs://data-infra-infobio-ocean-data/backups/auto-settings/deploy-20261009-v6/`.
The production database was not restored or migrated. Schema remains
`20261005_0016`, 34 tables.

Broader free-form English/Japanese wording and browser role flows remain outside
this bounded evaluation. AUTO remains opt-in. All reported timings are observed
handler durations, not latency guarantees.
