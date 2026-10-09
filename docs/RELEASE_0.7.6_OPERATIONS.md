# v0.7.6 operations — 2026-10-09 JST

[Release](https://github.com/jarondlk/ocean-platform/releases/tag/v0.7.6) ·
[Release notes](RELEASE_NOTES_0.7.6.md) ·
[Health/security audit](GCP_HEALTH_SECURITY_2026-10-09.md)

## Source, images and release identity

PR [#127](https://github.com/jarondlk/ocean-platform/pull/127) merges AUTO planning,
fresh published defaults, API/frontend 0.7.6 metadata, TLS bootstrap, the `gcp`
CI trigger and bundle/regex security hardening. The merge is `1c0ca1d`.

Both images were built from exact application source
`784cd5c129b587e046bbcf68abf7d8e92d9a6db9`, using a clean Git archive. Its archive
SHA256 is `ca4851e695e051baf27e09b612e029c9109693dc7323fc2fc9f13a3108b15a52`.
Cloud Build `90655463-e299-4f39-9e53-0fe0206404f0` completed SUCCESS. The earlier
superseded build was cancelled and never promoted. Uncommitted user files were
excluded from both images and the release.

| Container | Artifact Registry digest |
| --- | --- |
| API | `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/api@sha256:9802db4a1146f0ea88ef688f13f917f01ae29085c4108a893dd9c2b4faf3f755` |
| Frontend | `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/frontend@sha256:78205ef4b923ca3f144d9268ed55440100b3b333538de6172bad82b7259e5149` |

The release tag points to final merged `main`, including this documentation.
The difference from the immutable application source contains only Markdown;
runtime code, dependencies and version metadata are identical. `SOURCE_COMMIT`
continues to identify the actual built application source rather than the later
release-documentation commit. GitHub release/tag receipts record both identities.

## Validation

All eight source PR checks passed: CodeQL, three language analyses, backend tests
and coverage, frontend typecheck/build, PostgreSQL integration and dependency
review. Merged-main checks passed, with dependency review appropriately skipped
on a push. Full final cloud gates passed: lint, generated contract freshness,
**1,360 backend tests / 49 optional skips**, **79 frontend tests**, typecheck,
production build, non-root runtime imports, PostgreSQL bootstrap/readiness,
synthetic backup/restore, scientific libraries and unsuppressed image scans.

Final scans add no finding relative to the accepted AUTO images. API: 44 HIGH,
62 MEDIUM, 82 LOW, one UNKNOWN; frontend: 43 HIGH, 58 MEDIUM, 60 LOW, one UNKNOWN.
Both have zero CRITICAL or language-package findings. Ten source CodeQL findings
were fixed without dismissal/suppression; fresh default-branch open count is zero.
The OS findings remain documented in #104; these counts are package findings,
not eight new distinct CVEs or evidence of general exploitability clearance.
Exact runtime checks retain removal of unused affected tools, modules, privilege
bits and the SASL DIGEST-MD5 plugin. See the dated security audit for applicability
and upstream stable-package limits.

Full runtime and scan reports are private:
`gs://data-infra-infobio_cloudbuild/v076-qa-20261009/90655463-e299-4f39-9e53-0fe0206404f0/`.

## Live AUTO acceptance

The first execution `ocean-v076-qa1009-lxmt8` passed cases 1–5, then failed its
unchanged gate when the CTD planner call returned `unavailable` after 24.88s.
The app abstained before main-model invocation, production stayed on the prior
revision and the isolated database was removed. That failed receipt is retained.
A fresh full execution repeats the same assertions with private provider-error
diagnostics in the operator harness; no application retry, timeout or constraint
was changed to obtain a pass.

Execution `ocean-v076-qa1009-pdx95` completed successfully; all eight answers,
three unsupported-constraint rejections and manual all-off abstention passed.
The isolated database was removed. Live provider was Vertex AI; both configured
models were `gemini-3.6-flash`, used in separate planner/answer calls.

| Case | Route / setting behavior | Elapsed seconds |
| --- | --- | --- |
| Fresh MUR coverage, no pins | `sst_coverage`; deterministic answer | 36.1 |
| Exact reported top-10 fish question, no pins | `published_exact`; deterministic answer | 32.95 |
| Fresh high/low SST comparison, no pins | `published_exact`; deterministic answer | 41.3 |
| Explicit MiSeq paired request | `published_exact`; deterministic answer | 34.23 |
| Published comparison interpretation | `published_synthesis`; main model invoked | 41.28 |
| CTD Onagawa 2024 RAG | `rag`; main model invoked | 36.07 |
| Pinned MiSeq fish-frequency workflow | `published_exact`; deterministic answer | 32.8 |
| Pinned MiSeq high/low workflow | `published_exact`; deterministic answer | 32.66 |

Fresh published choices resolve same-publication 3NN, matching workflow and first
eligible NextSeq 500 paired protocol. Explicit MiSeq/pins are honored. MUR coverage
returns 1,455 of 1,461 expected historical days with six final gaps. High/low
workflows also select the linked MUR dataset. Published interpretation and RAG
invoke the main model; exact statistics/coverage do not. Top-5 replacement panels,
NovaSeq and incompatible 2024 qualifiers abstain before main-model generation.
All supplied citation IDs and per-user history bindings passed validation.

Private complete receipts:
`releases/v076/qa/784cd5c129b587e046bbcf68abf7d8e92d9a6db9/ocean-v076-qa1009-pdx95/`
in the private scientific-data bucket.

The matrix uses a disposable native PostgreSQL restore and synthetic researcher;
application calls, planner proposals, answers, history and citations use that
isolated database. Production chat/history is not written by the acceptance job.
Broader free-form English/Japanese, live browser/mobile and scientific/provider
acceptance are not claimed. Exact workflow/protocol/cohort limits remain visible.

## Production, health and preservation

Accepted Ready revision `ocean-platform-v076-patch1009` serves **100%** at
[the canonical site](https://oceaninfobio.com/chat). API/frontend pins match the
built images; serving configuration, auth/secret bindings, IAM, read-only data
mount and min0/max1/concurrency20 limits are preserved. Canonical login/provider
responses pass; anonymous analysis-options, stats and review endpoints return
401 as required.

Read-only health execution `ocean-v076-health1009-hrq5w` passed: application
0.7.6, database/model available, schema `20261005_0016`, 34 tables, 8,774 evidence
documents and 1,534 SST days. All four analysis identities, content hashes and
protocol memberships are valid; two legacy descriptive analyses remain explicitly
unavailable. Regional publication remains
`d34da58bbb39bb3675d0d0654d56ab13de46b078605df0fe52cb8f8ade698952`.

Preservation execution `ocean-v076-preserve1009-l7ssb` passed. Original accounts,
roles, completed history, canonical retrieval content/embeddings, corpus and
regional publications and scientific artifact hashes match the fresh baseline.
No new accounts were observed. Production was not restored or migrated.

Cloud SQL `ocean-postgres` now enforces `ENCRYPTED_ONLY`; existing managed bindings
remain compatible. The instance is RUNNABLE, deletion protected, with seven recent
successful managed backups and seven-day PITR. No public authorized SQL networks
or user-managed runtime keys were found. Private bucket IAM/access prevention,
versioning/soft delete and application auth remain intact. No capacity, IAM, role,
secret, schema or scientific acquisition changes were made.

## Backup, rollback and resource cleanup

Before rollout, execution `ocean-v076-backup1009-f4blg` created a native PostgreSQL
backup and passed isolated restore through the enforced TLS policy. Its temporary
database was removed; production was not restored or migrated. Private receipts:
`gs://data-infra-infobio-ocean-data/backups/v076/release-20261009/`.
Archive size **210,083,130 bytes**, SHA256
`a6526a5de78a5ec2ca49df4964e48da2112524700f4b6ed834b80d2c3fdc8311`.

Immediate compatible rollback is retained as `v076-previous` pointing to
`ocean-platform-auto-settings1009e`. The earlier AUTO revision and v0.7.5 plus
other historical version tags are also retained. `v076-production` and
`auto-settings-production` point to the accepted v0.7.6 revision. The temporary
`v076-candidate` tag and four completed release operator jobs were removed;
accepted/rollback revisions and private evidence remain.

Five existing manual jobs (`ocean-anemone-process`, `ocean-embedding`,
`ocean-evaluation`, `ocean-migrate`, `ocean-pipeline`) are aligned to the accepted
API digest/source without executing their commands. Their complete configuration
apart from these two pins is unchanged. Both SST acquisition jobs remain
unchanged and paused. No database restore, acquisition or migration was launched
against production.

## Documentation and branch archive

Current README, handoff, deployment/runbook, roadmap, security, documentation
index and release notes are updated. Final audit: **121 Markdown files**, no
broken local files/heading links; **54 referenced repository issue/PR IDs**, all
resolve. Historical Dependabot alert IDs 283/300 are explicitly labelled and both
fixed. Dated release, acquisition and scientific IDs retain their original meaning.

Final branches are `main` and `gcp`, aligned at the final release commit locally
and on origin. AUTO was merged through #127. `gcp-dev` had no unique commits and its
branch protection was transferred to `gcp`. The obsolete branch alone was
then allowed to be deleted; `main` rules and `gcp` force-push/deletion protections
remain unchanged. Merged `auto-setting` and `gcp-dev` were deleted after
verification. A verified local Git bundle preserves the pre-cleanup refs/tags,
including both deleted branch tips:
`.git/branch-archive/before-v076-final-cleanup-20261009.bundle`.
A private durable copy is retained as `before-branch-cleanup.bundle` in the
release backup prefix above.
The separate uncommitted Himawari script and `scripts/README.md` edit are preserved
outside this release. Scientific scope issues #89/#102/#103, OS #104, mobile #107
and sign-out #108 remain open.
