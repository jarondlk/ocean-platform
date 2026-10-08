# v0.7.4 operations

Published and deployed on **2026-10-08 JST** at [oceaninfobio.com](https://oceaninfobio.com/chat).
Ready revision `ocean-platform-v074-patch1008` serves 100% of traffic.
Independent production preservation verification completed at **07:50:01 UTC**
(16:50 JST). This release exposes explicitly user-approved provisional Miyagi
2020–2023 research results; it does not establish independent researcher approval,
provider endorsement, confirmed physical sample identities or native coastal SST.

## Exact source, build and validation

[PR #119](https://github.com/jarondlk/ocean-platform/pull/119) merged as
`cf01f1986d131541c5291950915cbe9aeb784c54`. The immutable
[v0.7.4 tag](https://github.com/jarondlk/ocean-platform/releases/tag/v0.7.4) and
serving images pin tested source `f73d5fd8cdaa358f1b4d084843a64d0cefe35b02`,
which is in main's ancestry. Later documentation commits do not change that tag
or those images. All eight GitHub checks passed, including PostgreSQL integration,
backend/security tests, frontend build, dependency review and CodeQL.

Full local backend validation: 1,257 passed, 39 optional PostgreSQL tests skipped,
81.04% coverage; active Python lint passed. The final frontend change passed all
72 tests and typecheck. Final Cloud Build
`58b35a1d-9f7f-496f-8f47-cb524c82ba87` passed all eight steps at 06:04:58 UTC:
frontend tests/audit/typecheck/build, both images, runtime smoke/schema, standalone
dependencies and full unsuppressed scans. Backend runtime/science code was
unchanged from the preceding fully checked build; GitHub backend checks remained
required. All 574 source archive files matched the clean worktree. Archive SHA-256:
`afd09eb5e292eb97e9442d31e95eb7fb2e705938a8b85a4b31ee24497e6c336f`.
`.git` files/directories and private credentials were excluded.

Registry: `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform`.

| Container | Accepted/deployed digest |
| --- | --- |
| API | `sha256:854271cf47ee9d4fdaf6812a4ed666e9b8c7a4d774951cd002f178eb0ab2d805` |
| Frontend | `sha256:d0cc1743854f251e59cd6169823b4318950be20242e8aba4a567c79d0c58a44d` |

Standalone version 0.7.4, Next.js 15.5.27, source-map-js 1.2.2 and sharp 0.35.5
passed exact-image checks. Numeric/NetCDF imports and all 34 required tables at
schema `20261005_0016` passed. Full scans retain no CRITICAL or reported language
package findings. Counts: API HIGH 44 / MEDIUM 60 / LOW 82 / UNKNOWN 2; frontend
HIGH 43 / MEDIUM 58 / LOW 60 / UNKNOWN 2, counting finding records rather than distinct CVEs.
The only raw delta against v0.7.3 is liblzma5 deb13u1 → deb13u2 for an existing
UNKNOWN temporary finding; Debian's authoritative tracker marks deb13u2 fixed:
[TEMP-1147318-639065](https://security-tracker.debian.org/tracker/TEMP-1147318-639065).
Raw scanner reports were retained unchanged. #104 stays open for other OS findings.
Private reports: `gs://data-infra-infobio_cloudbuild/v074-qa-20261008/58b35a1d-9f7f-496f-8f47-cb524c82ba87/`.

## Provisional publication and scientific limits

Job `ocean-v074-demo-publication-t9wh5` completed at 05:47:15 UTC, publishing
and fully reading/recomputing two schema-three bundles under the private
`provisional-demos` namespace. Calculation source was
`b984771f9280f1480f6b3bcefd2b8bd5347e2b9e`; final f73d5fd differs only in
three frontend files and two documentation files. Runtime remains Python 3.12.14,
NumPy 2.5.3/SciPy 1.18.1. Publication inputs/receipt are retained under
`research-sst/issue103/demo/miyagi-2020-2023/preparation-fb88db6/` in the private bucket.

| Method | Immutable analysis ID |
| --- | --- |
| QCauto target | `2eb754de7d095a43c7bb6cea14fbb88a1a9d8dc42a90032e8a46d6d4a7683083` |
| QCauto 95%-3NN target | `9312a7e12211be66f58f17a1e57f2ce0f581da427d9074cada8787657af6d56b` |

Each bundle retains 104 singleton occurrence proxies and 104 regional SST matches
within 24h, split into protocol groups 9/56/39. Fourteen unresolved repeat occurrences
are excluded. Both assignment methods/protocols remain separate. Source hash is
`334a1f0ebb84085e5f0f1163a90a085a7e721d0c0202ee2ae69014efd8924458`.
All 12 frequency/temperature checks across methods/protocols passed; unsupported
spatial/taxon requests and disabled SST abstained. No canonical classification,
physical identity, account/role/IAM, formal review ledger or raw corpus was changed.

The processor used existing retained bytes only: 48 months, 1,455 final MUR 04.1
regional days, six explicit final-series gaps. SST is 0.05-degree grid-point
subsampling over 38–39N/141–142E, with accepted provisional QC/cosine weighting,
not native sample-area SST. All supported days retain the missing-ice-fraction
open-sea fallback warning. Relative thresholds use 2020–23 region/season days;
read sums are not abundance and temperature association is not causation.
Species-resolved Japanese sardine is unavailable; unidentified Sardinops is
not silently substituted. One rectangle cannot support spatial redistribution.
See [demo evidence/limits](MIYAGI_PROVISIONAL_DEMO_2026-10-08.md).

## Backup and preservation

Explicitly approved full private backup/restore execution
`ocean-v074-verification-ffrfc` completed at 05:48:45 UTC. Size 208,802,895 bytes;
SHA-256 `5d7db7b1ac1c4d2e7c0834064979aaabf1531c4e5932f3466e442fc86666aba6`.
It includes accounts/history, was restored only to a disposable database on the
same Cloud SQL instance, verified and removed. No production migration/restore.
Private prefix: `gs://data-infra-infobio-ocean-data/backups/v074/release-20261008/`.
The fresh b984 backup was reused only after verifying the final frontend/docs-only
diff; the original backup source receipt remains truthful.

Read-only candidate execution `ocean-v074-verification-cr4pb` and production
execution `ocean-v074-verification-dqk54` passed. They preserved all pre-backup
terminal history hashes, identities/roles, canonical publication IDs, retrieval
content, unaffected counts, scientific artifact bytes and Overview coverage.
Production verification used a post-promotion query time boundary, preventing
candidate history from satisfying it. Corpus remains 7,319 documents/embeddings,
3,498 ANEMONE occurrences/assays and79 raw SST days (2025-12-05–2026-02-27).
Historical demo results are published analysis artifacts, not a claim that the
raw SST source filter now covers 2017–23.

## Normal browser acceptance and cleanup

Normal invited Google admin sign-in passed at zero traffic and the production
session remained authenticated. Both domains answered top-fish frequency and
high/low SST with 3/4 valid citations respectively, zero invalid citations/audit
warnings, charts and explicit scientific limits. These audit warnings differ
from the retained scientific quality warnings described above. Candidate 3NN,
conflicting filters, disabled SST, sardine and spatial limitations were checked.
The Data CSV export was read back: 377 rows, every metric explicitly
`sequencing_read_sum_not_abundance`.

Candidate QA discovered a stale analysis binding after source-filter edits.
The fix passed regression tests and the repeated real browser sequence:
select analysis → edit filter → clear analysis → ordinary overlap question.
Both candidate and production ordinary overlap supplied 4 SST + 4 eDNA documents,
abstained with `overlap_unverified`, did not run the model and preserved the
exact saved evidence fingerprint/prompt hash. Seven anonymous auth/protected
endpoint checks passed on candidate, canonical-auth zero-traffic and production.
Fresh production logs had no ERROR entries. Fresh viewer/researcher/mobile
acceptance was not repeated; earlier dated role checks and user deferrals remain.

Temporary OAuth callback, both QA revisions, candidate/final tags and both
release jobs were removed. Restore database removed; private evidence retained.
Only two original OAuth origins/callbacks remain. Production tag is
`v074-production`; all preceding rollback tags remain. Five manual job image/source
pins were aligned with commands/configuration preserved and none executed.
The two superseded SST acquisition definitions/archives remain unchanged and
were not restarted. The acquisition follow-up stays paused; no new NASA/NOAA
provider download ran for this rollout. Resource limits, budget alerts, IAM,
identities/secrets, canonical auth and read-only serving mounts are unchanged.

Immediate compatible app rollback: `ocean-platform-v073-patch1007`
(`v073-production`). Retain schema 0016/newer history and private provisional
artifacts; older apps do not enumerate the separate provisional index. A database
restore is a separately reviewed recovery action, not routine image rollback.

#89/#102/#103 remain open for formal environmental/physical/area review,
latest-assay evidence, native/full-scope acquisition if needed, expansion beyond
Miyagi and the remaining four original spatial demonstrations. #104/#107/#108
retain their separate security/mobile/sign-out follow-ups.
