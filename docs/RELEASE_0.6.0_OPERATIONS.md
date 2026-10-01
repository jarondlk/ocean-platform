# v0.6.0 release and deployment record

Started 2026-10-01 JST. The user authorized closing local previews, updating
documentation, publishing a new GitHub release and deploying through GCP.

**Status: GitHub v0.6.0 released; security-amended GCP candidate verified at zero traffic.**
Production still routes 100% to v0.5.0 at `ocean-platform-v050-prod0930`.
The final candidate is `ocean-platform-v060-sec1001`, built from runtime
amendment `6fd37eba2173ad86b704e775c6edba997082b4e8`. Authenticated browser
acceptance is blocked by unavailable browser controls; repeated issue #70
scientific-answer acceptance remains pending. No production cutover is claimed.

## Scope and source

Development branch: `gcp-dev`; integration branch: `main`.
The release includes independent chat source settings, available-data selection
controls, validated per-account browser persistence, scope enforcement,
provider-effective controls and bounded issue #70 fixes. See
[release notes](RELEASE_NOTES_0.6.0.md), [implementation](RELEASE_0.6.0_IMPLEMENTATION.md)
and the [adopted plan](RELEASE_0.6.0_PLAN.md).

An existing deployment pitfall is also repaired: Alembic's interpolating parser
now preserves percent-encoded Cloud SQL socket/password URLs. The standard
`python -m alembic upgrade head` no longer needs the v0.5.0 operator's raw-parser
workaround. The regression checks URL round-trip and absence from SQL output.

## Verified preparation

- Local API and frontend preview processes were stopped; no listener remained
  on port 3006. The browser panel was hidden and its visibility verified false.
  Individual tab closure remains blocked by the browser connection timeout.
- Final backend regression: 914 passed, 35 PostgreSQL-gated skips, 79.25%
  coverage (70% gate). Frontend: 48 tests, typecheck and production build
  passed. The source-contract export, Python lint, dependency consistency and
  single Alembic head `20261001_0014` passed.
- Initial candidate PostgreSQL integration: 34 passed in CI order. Selection
  refinement: the additional PostgreSQL test passed in a fresh disposable
  database, including local/SQL agreement, full canonical taxa, inactive rows,
  false controls, bound search, cascading choices and pinned membership.
- Local browser selection/cascade/search checks passed. The local preview has
  no ANEMONE corpus; this does not establish live production availability.
- GitHub credentials were verified for repository owner `jarondlk`. GCP
  authentication was renewed through the user-requested browser login.
- Live configuration confirms v0.5.0 still receives 100% traffic. Serving limits
  are unchanged: API 2 CPU/2 GiB, frontend 1 CPU/512 MiB, concurrency 20,
  minimum zero/maximum one instance. Cloud SQL is RUNNABLE on PostgreSQL 16,
  `db-custom-1-4096`, 10 GiB, with backups and PITR enabled. No v0.6.0 image or
  migration has been applied at this preparation step.

## Security and production precheck

PR [#78](https://github.com/jarondlk/ocean-platform/pull/78) initially exposed
CodeQL alert 27 (`py/polynomial-redos`) in the eDNA unknown-status answer
selection. The regular expression was replaced by a linear per-line scan.
Regression cases cover case-insensitive matching, line boundaries, Japanese
queries and 100,000 repeated `unknown` tokens, with and without a following
control label. The updated CodeQL security result and all remote CI checks passed before merge.

The user explicitly approved the bounded temporary `ocean-v060-readcheck` job
after automatic review requested specific approval for its identity/database
access. Execution `ocean-v060-readcheck-qm5mn` completed successfully, and the
job was deleted afterward. It made no database mutations. The live schema is
`20260925_0013`; active documents and matching embeddings are CTD 162,
metagenome 82, remote sensing 79 and eDNA 6,996. Canonical records are 3,498
source occurrences/assays, 349,638 assignment rows and 13,932 internal standards.
The ready eDNA publication matches the database generation/digest, and the
provenance snapshot remains `v050-production-provenance`. The database is about
1.21 GB. Production traffic remains on v0.5.0.

## Published source, build, backup and candidate

- Source PR [#78](https://github.com/jarondlk/ocean-platform/pull/78) merged
  after backend/frontend/PostgreSQL integration/dependency/CodeQL checks passed.
  GitHub [v0.6.0](https://github.com/jarondlk/ocean-platform/releases/tag/v0.6.0)
  pins `91d8567bfd0d13b8a6d1450cdeaccbfc2ce90f9e`.
- Cloud Build `956e81b6-9724-423f-a063-19d81ee52140` succeeded from a clean
  Git archive of that tag. Its Python and frontend checks and both image builds
  passed. Immutable API digest:
  `sha256:0b432b0b025038e0768660e3148063ad359450d18e495b2d627dcae7e19cf9c0`.
  Frontend digest:
  `sha256:5e08bf7d4a223b42b191c98ce4b4349e552000e91a99719716490c6ea77e3eeb`.
- Fresh backup execution `ocean-v060-backup-fbcfd` passed structural/digest
  verification and an isolated restore across all **28** tables, including
  160 chat interactions. SHA-256:
  `07ed4aa1c3e3ea97bcf00eab1bd90586f283852809186b70d8f9d1b0bce5557d`;
  size 207,959,925 bytes. The disposable restore database and backup job were
  removed; the archive and manifest are retained in the private operator record.
- The existing `ocean-migrate` job retained its standard bootstrap command,
  identity, secrets and limits while moving to the release API image. Execution
  `ocean-migrate-5h687` applied `20260925_0013 -> 20261001_0014` normally and
  verified all required tables/columns and the vector extension. No parser
  workaround was used. The additive constraint remains compatible with v0.5.0.
- Revision `ocean-platform-v060-cand1001` is Ready with tag `v060-candidate`
  and zero traffic. Its configuration was derived from the live service,
  retaining authentication, identity, secrets, data locations, concurrency 20,
  min zero/max one and container resource limits. All previous routes remain.
- Candidate HTTP smoke passed: login/session returned 200 and anonymous
  health/stats/capabilities/filter-options/chat requests returned 401.
  Authenticated browser verification is pending; those HTTP checks do not
  establish authenticated UI or model-answer acceptance.

## Live runtime acceptance

The user explicitly approved `ocean-v060-runtime-qa` after automatic review
required specific approval for its broader read-only script and access path.
Execution `ocean-v060-runtime-qa-68sk2` passed in 20.59 seconds and the job was
removed afterward. It wrote no chat history, canonical records or publications.

- All 16 source combinations had the expected live SQL membership.
- Every source reported available. eDNA choices included `anemone` and both
  supported assignment methods; canonical taxon search found
  `Ablabys taenianotus`. CTD station `s1` correctly narrowed sample choices.
- Exact catalogue/classification counts matched the frozen observation. The
  rare-taxon/method cohort had one occurrence, one assay, one assignment and
  122 reads. Summary/physical/unknown-count routing and English/Japanese
  freshness detection passed.
- Four source-only retrievals returned eligible documents: CTD 2,389 ms,
  metagenome 1,309 ms, SST 1,359 ms and scoped rare eDNA 3,132 ms. These are
  individual job measurements, not a concurrency or p95 claim.
- Vertex capabilities excluded unsupported context-window/repetition controls.
- No disposable restore database remained. The candidate had no recent
  ERROR-level logs at the check.

This job called runtime functions directly and made no chat-generation calls.
It does not establish authenticated browser behavior, persisted new-reason
history or repeated real-provider scientific claim support. Those remain
explicit cutover gates; issue #70 remains open.

## Provider smoke and dependency security amendment

Existing evaluation job execution `ocean-evaluation-rz4hd` ran only `ctd_01`
in `Full` mode with the initial v0.6.0 API image. Vertex embedding/generation
requests returned 200. The answer had eight valid citations, measured generation
latency 4.4 seconds and whole-run duration 7.4 seconds. Normal evaluation artifacts
were retained; this single question does not close issue #70 or semantic review.

GitHub's push notice prompted a fresh dependency review. All 16 active runtime
alerts concerned the pinned PyJWT 2.13.0 and urllib3 2.7.0 versions. The
[PyJWT advisory](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-ffc3-869f-jxw9)
requires mixed asymmetric/HMAC verification and a public PEM key; OCEAN uses
only `HS256` with a dedicated internal secret, so those prerequisites are absent.
The [urllib3 streaming advisory](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw)
and the remaining library advisories are addressed by updating the dependencies.

The runtime amendment pins PyJWT **2.15.1** and urllib3 **2.8.0**, regenerating
all four hash locks. A version comparison verified that no unrelated package
changed. The hash-locked development install and dependency consistency check
passed. Full backend regression remained 914 passed / 35 PostgreSQL-gated skips,
79.25% coverage. `pip-audit` reported no known vulnerabilities in the complete
amended runtime lock. The existing `v0.6.0` tag is retained; the separately
recorded tested amendment commit and immutable rebuild are required before
candidate promotion. PR [#80](https://github.com/jarondlk/ocean-platform/pull/80)
contains the dependency amendment and current operational documentation.

After amendment merge, the runtime manifest had zero open Dependabot alerts.
GitHub still listed 69 repository-wide alerts: 67 on four old root manifest
paths that are absent from the current Git tree, plus two medium GitPython
alerts in the optional archived Streamlit dependency input/lock. GitPython is
absent from the serving runtime lock. Those notices were not dismissed, and
this record does not claim the entire historical repository is alert-free.

## Final amended candidate verification

PR #80 merged after all remote checks passed at runtime source
`6fd37eba2173ad86b704e775c6edba997082b4e8`. Cloud Build
`e9f7f595-435c-483c-9b1d-8e164de73262` succeeded from its clean Git archive,
including Python/frontend checks and both image builds. Final immutable digests:

- API: `sha256:d1e779bf41cada9ff8aee00b3df62b98b89e99b748bff0de4cac0c029124741c`.
- Frontend: `sha256:82f9e240b245220b360f5aaad869f1d157248f142e99de7801465a8484ca9c36`.

Revision `ocean-platform-v060-sec1001` is Ready at zero traffic with the
`v060-candidate` tag. Configuration/resource/authentication preservation and
continued 100% traffic on `ocean-platform-v050-prod0930` were verified.
Login/session again returned 200; anonymous protected routes returned 401.
No recent ERROR-level candidate logs were found.

The unchanged, user-approved read-only QA script ran against the amended image
as `ocean-v060-runtime-qa-vzwlr` and passed in 22.16 seconds. It reverified schema
`20261001_0014`, all 16 source combinations, live available options/cascading,
exact catalogue and rare-taxon counts, freshness routing and provider controls.
Source-only retrieval latency was CTD 2,287 ms, metagenome 1,363 ms, SST 1,416 ms
and scoped rare eDNA 2,789 ms. It made no database/history/publication writes or
chat-generation calls, and its job was removed afterward.

All five existing manual jobs now use the amended API digest and source marker.
A before/after inventory verified unchanged normal commands, identities,
resources, timeouts and retry limits. Exactly those five jobs remain; no
additional ingestion, embedding refresh, migration execution or schedule was
started by this alignment.

The initial candidate/images above are historical build evidence and must not
be promoted. The expanded migration remains compatible with the current v0.5.0
runtime. Final cutover still requires the authenticated browser/history/citation
and repeated scientific claim-support gates below; the one CTD provider smoke
is not a substitute for those checks.

## Deployment order

1. Commit and review the exact candidate; pass required remote CI/security
   checks, merge to `main` and publish the immutable v0.6.0 source release.
2. Verify current service/job configuration, database schema, publication
   generations, budget/resource limits and recent errors after authentication.
3. Build immutable API/frontend images from an archive of the release commit.
4. Take a fresh production backup and verify an isolated restore before applying
   migration `20261001_0014` with the candidate image.
5. Prepare a zero-traffic candidate using existing production configuration and
   resource limits. Sharing production storage does not isolate test writes.
6. Verify active source choices, scoped retrieval/answers/history, known issue
   #70 cases, citations/downloads/provenance and authenticated UI before routing
   production traffic. Record measured latency and remaining limitations.
7. Switch traffic only after the applicable gates pass, verify the live revision
   and update this record, release status and current operating documentation.

No ingestion/reimport, embedding refresh, publication replacement, new IAM grant,
schedule or capacity increase is part of this settings release.

## Recovery

Record the previous compatible revision and immutable image digests before
mutation. The history constraint expansion is compatible with old application
writes and can remain during an application rollback. Never remove retained
new-reason history to force downgrade, overwrite later user activity with the
pre-release backup, or route an incompatible v0.4.x reader to the v0.5.0 corpus.
