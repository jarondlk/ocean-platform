# v0.4.4 release and deployment record

Status on 2026-09-11 JST: GitHub release published, production deployed, and
controlled eDNA rebuild verified. The user authorized commit, push,
GitHub release, and cloud rebuild, and completed GCP reauthentication.

## Release source and verification

- [PR #62](https://github.com/jarondlk/ocean-platform/pull/62) merged through
  protected `main` after all required checks passed.
- Release commit: `d3aa6a975e7405eaa291d53b50c33985e07f28ff`.
- [GitHub release v0.4.4](https://github.com/jarondlk/ocean-platform/releases/tag/v0.4.4).
- API/frontend version: `0.4.4`; schema remains `20260905_0011`.
- Local backend: 760 passed, 13 expected service-gated skips, 78.26% coverage.
  Focused taxonomy subset: 87 passed. Ruff and diff checks passed.
- Local frontend: 19 tests, typecheck, and 24-route production build passed.
- GitHub backend, frontend, PostgreSQL migration/metadata integration,
  dependency review, and CodeQL checks passed.
- Cloud Build: `bbff6249-7f41-4375-8ee8-97b5ce6c06a2`, submitted from an archive
  of the exact merged commit. The reference TSV is included for build tests
  and excluded from runtime images.

## Verified pre-deployment state

- Project `data-infra-infobio`, region `asia-northeast1`, service `ocean-platform`.
- Previous serving revision: `ocean-platform-v043-26094fc`, 100% traffic.
- Database backup execution: `ocean-pipeline-hhh2g`, successful.
- Archive: `gs://data-infra-infobio-ocean-data/backups/20260911T105725Z-v0.4.4-pre-deploy-ocean_platform.dump`.
- Archive SHA-256: `11ae758a8d493a22f9e3ab25afeeab83f4199d188f1ab90c6f34d5467a517790`.
- 27 tables restored and compared in an isolated temporary database; the
  temporary database was removed after successful verification.
- Read-only corpus audit: `ocean-pipeline-n72fj`, successful.
- One sample, one assay, 70 detections (35 per assignment method), four
  internal standards, and 325 embedded retrieval documents including two
  eDNA documents. Both methods retain 9,635 reads each.
- All 70 old derived assignments used rank `isolate`. Sample classification
  is `unknown`, `is_control=null`, with no approved classification review.
- Previous provenance pointer: `v040-provenance`, 325 documents/embeddings,
  SHA-256 `5d0f99a5ae5394560301d1aff5c94c10b41a44d4ca1f7edca981215d1802c7ed`.
- Previous eDNA retrieval generation:
  `45087d89cca6241d20d3693ce33e3cad1c51d6759767c3403df1d2cbba849740`.

## Deployment and rebuild

Cloud Build completed successfully. Immutable API digest:
`sha256:81a2a28212f9a037f7d1e3828774195f8856a29cc9c6e3837b9fbba08f08a045`;
frontend digest:
`sha256:52017fc620eb10c3b473e2c6cb1c2388549c0890b8503489f3ee786d54c2c46f`.

All five existing jobs were updated to the new API digest and release source
commit. Their commands, environment/secret settings, resources, and retry
limits were compared with pre-deployment exports and preserved.

- Schema check `ocean-migrate-6w4db`: ready, no missing tables/columns,
  pgvector present, 27 tables; no schema mutation.
- Candidate `ocean-platform-v044-d3aa6a9`: ready at zero production traffic.
  Service settings were preserved apart from images and source-commit values.
- Candidate `/login`, `/api/auth/session`, and `/manifest.webmanifest` returned
  200; protected health, eDNA, and provenance routes returned anonymous 401.
  No ERROR-level candidate logs were found.
- Normalization `ocean-anemone-process-jg5zm` and field comparison
  `ocean-anemone-process-dzbhb` passed. All 70 derived assignment names changed;
  every other source field and sample classification matched the retained
  previous bundle.
- New normalization: `9eb5f9ef4fa59e719e86f5d45f234f343aaa878f610972fb7aa852755fd489c3`.
- New normalized transport artifact:
  `a5fd95f4df17a479463469b6a8647ae5715e8707e7450b9e18c03e6c73e6f293`.

Production revision `ocean-platform-v044-d3aa6a9` receives 100% traffic.
The canonical domain smoke checks passed with the same expected 200/401
statuses as the candidate. GitHub production deployment `6391957212` is
recorded successful against the release commit. The initial production log
check found no ERROR-level or HTTP 5xx entries on the new revision.
Minimum zero/maximum one instance, concurrency 20, and existing CPU/memory
limits remain unchanged.

- Import validation `ocean-anemone-process-x8492` executed the exact merge and
  rolled back: 70 matched detections would update, no inserts or inactivations,
  and all other eDNA/source rows unchanged.
- Controlled rebuild `ocean-anemone-process-4nkr8` completed successfully. It
  committed the validated import, updated two retrieval documents, refreshed
  exactly two 768-dimensional Vertex embeddings, rebuilt the registered
  analysis, validated provenance, and published `v044-provenance`.
- New retrieval generation:
  `ac8391c48f24364ed8e8e6318f7fab50f9de4bb77bb47b3c3c6090106b33f21d`.
- New analysis: `2bcf4d4a7f74d379e1596f1415c9285e9638ccc159c67c5fdc269fa4b25dc985`;
  `edna-descriptive-v2`, current. Environmental-only composition/diversity
  remain empty, with 70 exclusions, because classification remains unknown.
- Historical analysis
  `947ddeca97b58076641bb5be35b480300ec95c1c3f5ecadfaf34c6172cfa86cf`
  remains registered, integrity-verifiable, and marked historical.
- Provenance pointer `v044-provenance`: 325 documents and 325 embeddings;
  SHA-256 `31b62fec72fdaa27d4550e44061fc9777967357c30c97aa88367cf4b26c741e6`.
- Final verification `ocean-anemone-process-fptkc` passed. Both eDNA document
  versions are 2, publication is ready, and the serving provenance reader
  resolves both exact document citation traces with source files and embeddings.
- Before/after checksums of source fields matched for samples, assays,
  detections, and internal standards. Detection identity, sequence, raw
  taxonomy, read counts, copies/mL, source locators, and classification were
  preserved. No reference TSV sample was ingested.

| Method | Before | Corrected rank counts | Total reads |
| --- | --- | --- | --- |
| QCauto | 35 isolate | 18 species, 14 genus, 3 subfamily | 9,635 |
| QCauto + 95%-3NN | 35 isolate | 27 species, 6 genus, 1 subfamily, 1 subspecies | 9,635 |

These are provider-label interpretations, not independently verified organism
identifications. The fixture supports the general policy for future files;
it does not restrict them to this sample's taxa.


Retain historical source, normalization, analysis, and provenance artifacts.
Before any application rollback, review compatibility with the new retrieval
publication. Do not overwrite later user/chat records or downgrade the schema.

## Verification limits and follow-up

The release and controlled rebuild gates are complete. Researcher-specific
browser acceptance of the scientific workflow, the historical suspension and
uninvited-account identity checks, owner Billing-console confirmation, and a
longer production observation window remain follow-ups. No classification
review was approved or applied, and no generation-model behavior was changed.

The deployed images and release tag remain pinned to the release source;
subsequent operations-documentation commits do not require another image build.
