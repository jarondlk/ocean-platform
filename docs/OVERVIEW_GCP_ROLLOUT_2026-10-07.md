# Overview coverage — GCP rollout, 2026-10-07 JST

The Overview timeline is live at [oceaninfobio.com](https://oceaninfobio.com/).
Revision `ocean-platform-overview1007b` serves 100% of traffic. This is an
application patch ahead of the next tagged release; the published `v0.7.2` tag
and application version remain unchanged. [Next release notes](RELEASE_NOTES_NEXT.md)
record the feature for inclusion in that release.

## Exact source and images

- Frozen source: `ad60f2eac6083b1e5b95df70b11117494a4fb08a` on `codex/overview-gcp-patch`.
- Source archive SHA-256: `0dc2f35c73859cdb6a43e8cb7a322759feb939cec0acf2a5734c6253d4a30800`.
- Accepted [Cloud Build](https://console.cloud.google.com/cloud-build/builds/9727c7b9-67ac-427d-90c9-7f2165d022d5?project=data-infra-infobio): `9727c7b9-67ac-427d-90c9-7f2165d022d5`.
- API: `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/api@sha256:1f006433f791751376156f71123a6cbba6b3a957064b583dbdb660dc5f51f1c7`.
- Frontend: `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform/frontend@sha256:1a6d6a6fac9001c53d1b4445542ae6d82e2469c1606b5716ea870e94bedb1d1d`.

The build starts from exact v0.7.2 production source `03638e6`, adds Overview
coverage, sharp 0.35.5 and the previously verified TCP readiness probe. Newer
SST acquisition tooling is excluded. A one-line correction avoids crowded
year labels when the chart begins immediately before January. Subsequent
integration of existing deployment documentation and these receipts does not
change the frozen build source or immutable images.

## Acceptance and preservation

The production-based source passed 1,099 backend tests, 39 service/data skips
and 79.44% coverage locally. Exact-source Cloud Build passed Python tests/Ruff,
the generated chat-contract check, 70 frontend tests, TypeScript, production
build, production dependency audit, container imports/numeric/NetCDF checks,
non-root/security checks, anonymous access checks and a disposable PostgreSQL
backup/isolated restore. The standalone image independently verifies
source-map-js 1.2.2 and sharp 0.35.5. No production migration or restore ran.

Both candidates started at zero traffic. Their login/provider endpoints
returned 200; anonymous Overview coverage and chat options returned 401.
Final live read-only acceptance and post-cutover verification passed in
`ocean-overview-verify-1007-wgb8z` and `ocean-overview-verify-1007-vvxdf`.
The verifier used one task, no retries, a 300-second limit and an existing job
identity. Every production SQL transaction was repeatable-read and read-only;
scientific storage was mounted read-only.

| Source | Unit and count | Observed range |
| --- | --- | --- |
| CTD | 162 casts | 2024-01-18–2026-03-02 |
| Metagenome | 82 samples | 2024-04–2026-02 |
| ANEMONE eDNA | 3,498 provider occurrences | 2017-12-18–2023-12-16 |
| Current satellite SST | 79 usable days | 2025-12-05–2026-02-27 |

SST lacks February 14–19, 2026. CTD/metagenome/SST share December 2025–February
2026; all four sources have no shared populated month. ANEMONE counts retain
343 controls and 3,155 unknown/other classifications. These are temporal
co-presence and occurrence counts, without spatial, physical-sample or
analysis-eligibility approval. Historical MUR acquisition/publication and
scientific approvals remain separate.

Normal Google admin sign-in and the authenticated production Overview passed.
Refresh, selection, SST day details, arrow-key navigation, readable year labels
and runtime health were checked. A 390px viewport had no document overflow;
the full timeline scrolled inside its panel. Existing English/Japanese/theme
checks are retained in the implementation record. This is panel-specific mobile
acceptance; it does not close the broader #107 workflow. Real viewer/researcher
sessions were not newly exercised; Overview permission/mutation restrictions
are covered by source tests and prior role acceptance remains dated evidence.

Final comparison with the pre-rollout baseline verified unchanged schema
`20261005_0016`, existing completed/failed history hashes, identity/role hashes,
publication bindings, retrieval content/embedding metadata, table counts and
CTD/metagenome/SST artifact hashes. Auth/CORS origins, signing/database secret
references, service identities, mounts, resource limits, min zero/max one and
concurrency 20 are identical apart from images/source identity/revision traffic.
All six original job specifications/images are unchanged, including
`ocean-sst103-historical-acquire`; none was executed by this rollout.

The original SST checkout remains on `codex/issue-103-historical-sst`, HEAD
`df1c23622fc81f4b6438899f0df6d0d6c0cc6cde`. Its existing untracked planning
file still has SHA-1 `82cf717ac3730c467cb8178e6557e122bc1bd73d`; no checkout,
downloader operation or working-file change occurred there.

## Security, cost, retained receipts and rollback

Full unsuppressed scans add no finding relative to the serving v0.7.2 receipts;
one medium finding is no longer reported by the scanner in each image. This is
not evidence that an OS package was fixed. Residual counts are API 44 high/60
medium/82 low/2 unknown and frontend 43 high/58 medium/60 low/2 unknown, with
no critical findings. Existing OS dispositions/mitigations remain tracked in
#104; the scans are not a vulnerability-free claim.

Authenticated Console verification before paid execution found Cloud Run at
about JPY 196.54 of its configured JPY 2,250 monthly spend cap; SQL/project
alerts remained JPY 4,000/10,000, showing zero after savings. Billing can lag
24 hours. No budget, IAM, SQL capacity or recurring resource limit changed.
Only bounded builds and temporary verifier executions were added.

Full image QA is retained privately under
`gs://data-infra-infobio_cloudbuild/overview-qa-20261007/9727c7b9-67ac-427d-90c9-7f2165d022d5/`.
Read-only baseline/final receipts are privately retained under
`gs://data-infra-infobio-ocean-data/backups/overview-20261007/9a296151-8dd3-4d03-96dd-880d47e62303/`;
these are verification snapshots, not a new database dump. Production receipt
UTC time is `2026-10-07T09:54:26.026279+00:00`. Local operator receipts and final
screenshot are in `/private/tmp/ocean-overview-deploy/`.

Build `9a296151` stopped at an operator assertion that tried Sharp's unexported
package.json subpath. The assertion was corrected to read the installed file;
source/container behavior had passed. Build `4eebe064` produced the accepted
initial timeline revision. Final build `9727c7b9-67ac-427d-90c9-7f2165d022d5` includes the visual spacing
correction. Failed QA and later documentation edits did not update serving
images; only accepted traffic promotions changed production.

The task-owned verifier and `overview-candidate` tag are removed. The
`overview-production` tag points to the final revision. Every original rollback
tag remains, including `v072-production` on `ocean-platform-v072-patch1006`.
Application rollback is:

```sh
gcloud run services update-traffic ocean-platform --project=data-infra-infobio --region=asia-northeast1 --to-revisions=ocean-platform-v072-patch1006=100
```

Keep schema 0016 and later history. Existing jobs keep their original images;
application rollback requires no migration, production restore or job change.
