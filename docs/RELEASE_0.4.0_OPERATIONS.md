# v0.4.0 deployment record

Verified 2026-09-03 JST. Classification remains unknown by explicit user
decision. This records operational verification, not researcher acceptance.

[GitHub release v0.4.0](https://github.com/jarondlk/ocean-platform/releases/tag/v0.4.0)
was published at 2026-09-03 13:41:04 UTC, targeting the source commit below.

## Source and deployment

- Source: `a63885a573b18eb92c184fb88fdb85b5aae3cb09`, merged through
  [PR #51](https://github.com/jarondlk/ocean-platform/pull/51). Both `main`
  and `gcp-dev` were retained and synchronized. Subsequent release-record
  documentation commits do not change the deployed application.
- Build: `76b31adb-28d6-4daa-a9cc-f114d36bd753`, all test/build steps successful.
  The superseded pre-security-fix build was cancelled, not deployed.
- API digest: `sha256:33e610b9c5b8aea6e14c5ef9cde2177a427ba7dbef13c5fe356f04c107f7532f`.
- Frontend digest: `sha256:52f3b0ac8fd85d1a45257c662aa5a996f9339e441d73be505ceb40c2c3678973`.
- Cloud Run: `ocean-platform-v040-a63885a`, Ready, 100% traffic.
  [Live application](https://ocean-platform-469489188516.asia-northeast1.run.app).
- Previous revision retained: `ocean-platform-v030-1bb38b8`. No schema downgrade
  or production restore was performed. Review corpus/publication compatibility
  before an application rollback; never overwrite later user/chat records.
- Migration `ocean-migrate-6r7gn`: head `20260903_0008`, 23 tables ready,
  vector extension available, no missing tables or columns.
- Existing migration/pipeline/embedding/evaluation jobs now use the API digest
  above. Manual defaults and resource limits remain unchanged. The new manual
  `ocean-anemone-process` job uses the existing processing identity, read-only
  legacy data mount, local staging and an offline-plan default. No acquisition
  credentials, new IAM grants, scheduler or archive-wide download were added.

## Backup and preservation

All archives are in `gs://data-infra-infobio-ocean-data/backups/`.
Each isolated restore matched every table count and removed its disposable DB.

| Check | Execution | Archive | SHA-256 |
| --- | --- | --- | --- |
| Before migration | `ocean-pipeline-tc6h6` | `20260903T090248Z-v040-pre-release-ocean_platform.dump` | `5ccb21ce4609afdd6462787b4f44855f650dfc27a351d258c53d3286ed652813` |
| After migration | `ocean-pipeline-tpk9z` | `20260903T132406Z-v040-post-migration-ocean_platform.dump` | `05aff3472488fd8b6a07a9a2ecbc684edab7a35c90d290dcb7e49e78181ae6eb` |
| After pilot publication | `ocean-pipeline-z9njq` | `20260903T133356Z-v040-release-ocean_platform.dump` | `44d2c1221e279d49a45fbe4e029fbcaa154087d2568158689e6a49d296a64e4a` |

Final backup: 23 tables, 2,739,102 bytes. Legacy counts remained users 3,
invitations 6, chats 53, feedback 8, audit 20, anchors 286, links 496, CTD profiles
10,955, CTD summaries 162, metagenome samples 82, SST summaries 79 and SST points
1,848. This backup precedes the live chat smoke tests; later chat/rate-limit
changes are expected user activity, not data loss.

## Retained pilot

The sample and raw-source history are recorded in
[the local canary](ANEMONE_PILOT_2026-09-03.md). No new download was needed.

| Artifact | Identity |
| --- | --- |
| Raw snapshot | `c57c669f0e87953cbbac70a0053f895bc8f6d391bc89ef9f14aa4b34c5ea5432` |
| Normalization | `141838ca49b84b2dc9521d3cc6004ce8136e8b4932a3424c6626b642b8dd9bc0` |
| Normalized transport | `fc33313938d494865fac1b0d6d1216fd26e568f2fcbc1e1b4d882cd85ebd88f5` |
| Retrieval generation | `45087d89cca6241d20d3693ce33e3cad1c51d6759767c3403df1d2cbba849740` |
| Analysis | `947ddeca97b58076641bb5be35b480300ec95c1c3f5ecadfaf34c6172cfa86cf` |

Completed processing executions: normalization `94r5m`, rollback-only import
`lndkw`, committed import `xbcqc`, materialization `sf8nr`, analysis `rlbfn`,
provenance validation `rfgw4` and publication `82vkx` (all have the
`ocean-anemone-process-` prefix). Credential-free operation reports are retained
in the registered `edna/operations` namespace.

Canonical records: 1 unknown sample, 1 assay, 70 detections, 4 internal standards,
13 source-file metadata records and 1 snapshot. No classification review was
applied. Two method-separated retrieval documents were inserted; no existing
document was inactivated or had its embedding invalidated.

Embedding dry-run `ocean-embedding-59ngx` found exactly 2 candidates. Bounded
execution `ocean-embedding-nk8mx` updated exactly 2 with `gemini-embedding-001`,
768 dimensions. Snapshot comparison retained all 323 legacy embedding records;
the only metadata differences are newly exposed provider and original embedded
timestamp fields, not regenerated embeddings.

Environmental-only genus analysis: 0 composition/diversity rows, 70 exclusions,
no environmental links. Descriptive method comparison: 35 shared sequences,
25 exact and 10 conflicting assignments. These counts do not establish
taxonomic accuracy or environmental eligibility.

Published provenance: `v040-provenance`, 325 documents / 325 embedded,
SHA-256 `5d0f99a5ae5394560301d1aff5c94c10b41a44d4ca1f7edca981215d1802c7ed`.
The snapshot includes legacy sources and the registered analysis. Its bytes
were checksum-verified. Prior snapshot `provenance-20260824T064300Z` is retained.

## Verification and limitations

- 638 backend tests passed, 9 PostgreSQL-gated local skips, 77.11% coverage;
  PostgreSQL integration passed in CI. 14 frontend tests, typecheck, production
  build, Ruff and dependency checks passed. Final PR/merge CodeQL passed after
  the local-artifact path-containment fix; no alert was dismissed to release.
  Existing assessed NLTK advisories remain documented in `SECURITY.md`.
- Live authenticated admin: Overview 325 documents / 162 CTD casts / 79 SST
  days, API/database/model available. eDNA catalog: 1 sample / 1 assay / 70
  detections, unknown sample/control status, 35 records per method.
- Live analysis UI: current method summary 35 shared / 25 exact / 10 conflicting;
  environmental-only diversity correctly has 0 rows.
- Live source-only chat at the existing 1,600-token limit retrieved both pilot
  documents and reported unknown sample/control classification. Both citation
  occurrences resolved, with 0 invalid citations and 0 audit warnings. The
  evidence panel and exact provenance trace resolved to the normalized records,
  source row locators/hashes and captured embedding. Citation validity is not
  scientific acceptance.
- Anonymous live eDNA catalog access returned 401; existing application auth
  and service IAM were preserved. Researcher/viewer role checks have automated
  local/CI evidence; no live role impersonation was performed.
- Known limitation: `/stats` briefly returned 500 while publication was pending;
  it recovered after materialization. Preserve fail-closed publication checks
  but improve the loading state in the next patch.
- Known limitation: with environmental-only filtering and analysis context
  disabled, zero evidence reached the model, which invented a negative-control
  sample and counts. The audit flagged all 5 citation occurrences invalid.
  Deterministic no-evidence abstention and visible recipe filters are next-patch
  work. This failed answer is not an accepted result.
- An additional source-only request at a reduced 700-token limit failed with
  `MAX_TOKENS`; the API rejected the incomplete output. The subsequent bounded
  source-only test at the normal 1,600-token limit passed as described above.
- Full six-case scientific/model-answer acceptance and the classification
  workflow remain deferred to [the next patch](ANEMONE_NEXT_PATCH.md).

## Cost and access controls

Min 0 / max 1 service instance (service and revision), concurrency 20, existing
container sizes, database tier, identities and secret references were retained.
User ceiling: JPY 20,000/month total. Existing project JPY 10,000 and SQL JPY 4,000
alerts and Cloud Run JPY 2,250 spend cap were not raised.

Read-only billing refresh at approximately 13:34 UTC still covered September 1
posted usage only: approximately JPY 276 gross, JPY 0 net after credits/savings
(SQL 253, Vertex 20, Run 3, Storage rounded 0). Trial credits showed JPY 45,586
remaining. This is delayed billing data, not a real-time cost or cap guarantee.
