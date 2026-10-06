# Pre-deployment repository audit — 2026-10-06 JST

Requested before the next authenticated GCP deployment. Baseline was clean
`main` at `f00a500769a772f4f0da2dbb66df473fc7a5dc6c`. This audit inspects maintained
source/configuration, current docs, all script entrypoints and their callers,
tests, dependency locks and current GitHub issues/alerts. It fixes verified
readiness/documentation defects. It does not provision GCP, refresh credentials,
publish a new version, apply production migrations, or approve scientific data.

## Readiness conclusion

The repository passes fresh local source and isolated PostgreSQL checks after
the fixes below. It is ready for review and exact-source patch image preparation.
Production is the last verified v0.7.1 deployment; the merged source-map-js 1.2.2
fix and this audit's script changes are outside its immutable tag/images.
Do not treat a clear repository dependency scan as a patched production image.
A fresh authenticated cloud census, exact image verification and candidate
acceptance still precede any new deployment.

| State | Evidence / disposition |
| --- | --- |
| Published/last verified production | v0.7.1, runtime/tag `e157fb004871083df25d5d094852fed417a9c8c6`, revision `ocean-platform-v071-source1005`, schema `20261005_0016`; [operations](RELEASE_0.7.1_OPERATIONS.md). |
| Repository dependency fix | #111 merged source-map-js 1.2.2; #110 remains open for exact images and new patch deployment. Version declarations remain 0.7.1 until a separate release is prepared; tag unchanged. |
| Completed acceptance | #101 normal Google role/workflow QA and cleanup, #105 per-source retrieval/unsupported-overlap regression are closed. The isolated role alternative did not approve real scientific registries/results. |
| Remaining work | #89/#102/#103 scientific demos/provider evidence/historical SST; #104 OS maintenance; #107 explicitly deferred live mobile QA; #108 transient sign-out investigation; #110 image patch rollout. |
| Cloud inspection boundary | GCP CLI login expired after completed rollout. Last release receipts are dated evidence, not a new inventory of current IAM, resources, traffic, bill or SQL configuration. |

## Verified findings and fixes

| Finding | Resulting change |
| --- | --- |
| README, handoff, roadmap and documentation index still called v0.7.0 current; deployment guides still called v0.6.0 current. Some role QA remained described as deferred, and schema claims stopped at 0013/0014/0015. | Updated current status/pointers to v0.7.1/0016 and separate repository-only fix. Historical releases/plans retain their dated evidence. Testing now directs readers to current commands before historical counts. ANEMONE authentication/review/pilot runbooks distinguish passed role QA from unapproved real scientific decisions. |
| `bootstrap_database.py --check-only` omitted aggregate/research tables and never checked Alembic head. A structurally incomplete or 0015 database could report ready. | Derive required tables from both application/corpus model registries; require exact current migration heads and report actual/expected heads. Retain explicit required-column and vector checks. Regression checks reject each missing aggregate/research table, old and unversioned schemas. |
| Candidate container verification upgraded Alembic without full corpus bootstrap or independent readiness receipt. | Use combined bootstrap, then read-only readiness verification and save `schema-readiness.json` before isolated backup/restore. Exact Linux image execution remains a cloud gate. |
| Three active batch scripts ignored `--help` and invalid arguments. The audit CLI probe regenerated local artifacts instead of printing usage. | Add argument parsing before processing in document builder, pre-analysis and reliability scripts. Restore the audit-regenerated tracked artifacts to exact baseline bytes. Six regression cases require help/invalid arguments to exit before any processing. No production or provider data was modified. |
| Ordinary Cloud Build lacked the production npm audit enforced by GitHub CI. | Add the same moderate-or-higher production audit gate; retain existing tests/typecheck/build. |
| Candidate artifact path was hard-coded `v071-qa`. | Configurable `_QA_REPORT_PREFIX`, default `candidate-qa`; exact build-ID subdirectory retained. No existing cloud reports moved. |
| Five ignored local rendered YAML files pinned old v0.4.2 build `fd2a5970-692f-424e-a721-0144e1e2e005`. | Move them out of the deployment directory into private audit storage. Retain source templates; do not replay renders for routine patching. |
| No consolidated supported/legacy script inventory. | Add [complete entrypoint inventory](../scripts/README.md), including effects, manual tools, historical QA, initial provisioning and single-image helper limits. No tracked script is proven safe to delete. |
| README exploratory correlations/anomaly wording could be read as current scientific acceptance. | Label the local exploratory snapshot, unadjusted p-values and need for independent anomaly evidence; distinguish it from the unapproved ANEMONE/SST demos. |

## Script status and retirement decisions

All 35 Python and three shell entrypoints under `scripts/` are inventoried,
along with three GCP shell helpers, three Cloud Build configurations, standalone
QA modules and the archived Streamlit UI. Application stage callers were checked
in `api/main.py`, the pipeline/ANEMONE runners, CI and job templates. Operator-only
catalogue/research/retention tools are retained even where no UI/job calls them.
Underlying module coverage and documented workflow are evidence of intentional
support; an unreferenced filename alone is insufficient deletion evidence.

Legacy material: Phase 7 probe, version-specific question/claim probes, historical
plans, archive UI and older release records. They remain useful for replay/parity/
evidence, but do not authorize current deployment or satisfy current acceptance.
The single-image frontend build helper is not the current release gate.
Foundation/SQL/raw-seed scripts are initial provisioning tools and must not be
rerun for an image-only patch. ANEMONE sync has a template but no currently
deployed automatic sync job. Serving remains external-job mode.

The only confirmed unused deployment artifacts were the five stale ignored
renders. Migrations, historical bundle readers, scientific fixtures and retained
QA evidence were not deleted. No new schedules, real acquisition, approval,
corpus publication, embeddings or retention deletion ran.

## Fresh verification

- Backend CI coverage boundary: **1,066 passed, 39 service-gated skips, 79.26%**.
  The first sandbox run failed only where loopback HTTP fixture binding was
  denied; the permitted rerun passed. Final suite includes the readiness and
  safe-CLI regressions.
- Disposable PostgreSQL 16/pgvector: full bootstrap and independent read-only
  readiness passed at **0016**, **34 tables** including Alembic version;
  **39 integration tests passed**. Full synthetic backup and isolated restore
  passed, verified all 34 tables and removed the restore database. The audit
  container was removed and the local VM stopped; no production data was copied.
- Frontend: **64 tests**, TypeScript checking and production build passed using
  Node 22.14.0/npm 10.9.2. Local source-map-js resolves to 1.2.2.
- Repository Ruff, dependency consistency (`pip check`), generated Chat scope
  contract and single Alembic head (`20261005_0016`) passed.
- Fresh npm production audit: **zero findings**. Fresh OSV batch check: **zero
  matches** among **98 distinct exact Python name/version pairs** across maintained
  runtime (65), dev (72), analysis (73) and archive (90) locks. [OSV API](https://google.github.io/osv.dev/api/)
  and npm advisory checks are point-in-time database results, not proof of absence
  of unknown vulnerabilities or container OS findings.
- Fresh GitHub repository queries: **zero open PRs**, **zero open Dependabot
  alerts**, **zero open code-scanning alerts**, **seven open issues** listed above
  before the audit PR. CodeQL default setup is configured, and recent analyses
  match baseline `f00a500`; zero open alerts does not mean zero historical or
  previously dispositioned findings. The eight stale root-manifest Python notices were already
  reconciled; maintained locks use PyJWT 2.15.1/Mako 1.4.3. Root legacy locks are
  absent; production installs `requirements/runtime.txt` with hashes.
- Markdown relative file links and tracked diff whitespace checked. Historical
  anchors, external-link availability and scientific reference correctness are
  not certified by this filesystem link check.
- Current anonymous production HTTP checks passed: login/provider discovery 200;
  protected health/admin proxies 401. These verify public boundaries, not live
  image/version/schema or an authenticated workflow.
- Shell syntax and Python CLI inspection checked. Interactive mock-password
  generation was not invoked. Batch help was rerun after argument-safety repair.

Private fresh logs, dependency/query receipts, synthetic backup and quarantined
renders reside under `/tmp/ocean-v071-release/`; temporary filesystem retention
is not durable cloud release evidence. The PR/CI and this report retain the
reviewable result. Existing v0.7.1 backup/image receipts remain separately private
under their recorded release prefixes.

## Required before the next deployment

1. Review/merge audit changes, choose/prepare a new patch version and freeze the
   exact clean source. Preserve v0.7.1 tag and rollback. Use #110 for the patched
   image deployment; do not claim source changes have already shipped.
2. Refresh GCP CLI authentication. Read current serving revision/digests/traffic,
   job images/commands, identities/secrets/mounts, scale/pools, SQL schema/tier/
   backups/PITR, storage protections and cost headroom. Compare with retained
   receipts before proposing any changes; no automatic legacy resource deletion.
3. Run exact-source combined source gates and candidate image/runtime/security
   verification. Independently confirm source-map-js **1.2.2 in the final
   standalone image**, not just the lock. Collect unsuppressed full OS/package
   reports and reassess #104; its eight prior high CVEs are not cleared here.
4. Take/restore-test a fresh private production backup if touching schema/jobs,
   verify migration head and preservation, then derive a zero-traffic canonical
   revision from the fresh live definition. This audit adds no migration.
5. Verify ordinary authentication/session/sign-out, history/settings/source
   coverage and the SST/eDNA overlap guard on exact candidate images. Carry
   explicit #107/scientific deferrals without labelling them passed. Promote only
   after acceptance, verify canonical production, align affected jobs without
   executing manual batches, and remove only task-owned temporary access/resources.

This is a readiness audit, not an assurance that every code path, production
configuration, arbitrary scientific answer or provider workflow has been tested.
