# Repository maintenance execution — 2026-10-02

This follows the [approved audit and execution plan](REPOSITORY_MAINTENANCE_AUDIT_2026-10-02.md).
Repository maintenance is separate from the published v0.6.1 deployment. Release
tags and production services, traffic, workload configuration, database and data
publications remain unchanged.

## Completed dependency work

- [PR #82](https://github.com/jarondlk/ocean-platform/pull/82): GitPython 3.1.62
  in the optional archive input and hash-verified lock, plus an enforced security
  floor and the audit record. Merge `0f7c007`; eight current CI/security checks
  passed at `a597b16145f9bb4ac0a922930a7740643ab517f1`. Archive resolution verified
  package hashes; local backend verification passed 947 tests, with 36 PostgreSQL
  integration tests skipped locally and separately passing in CI; coverage 78.32%.
- [PR #81](https://github.com/jarondlk/ocean-platform/pull/81): closed as a duplicate
  after #82 merged; both obsolete GitPython PR heads were subsequently removed
  automatically upstream.
- [PR #86](https://github.com/jarondlk/ocean-platform/pull/86): refreshed frontend
  maintenance, including Next/jose patches and matched React/renderer 19.3.0.
  Merge `564fc2e`; all eight current CI/security checks passed. Local production
  and development dependency audit reported zero vulnerabilities; 52 tests,
  TypeScript checking and production build passed.
- [PR #84](https://github.com/jarondlk/ocean-platform/pull/84): reconstructed as
  compatible Python maintenance, keeping SQLAlchemy 2.0.52 / psycopg2. Hash locks
  were regenerated for all four inherited sets. The greenlet regression now
  verifies an explicit supported floor and agreement across every lock. A new
  SDK transport regression checks actual serialized generation controls, output
  caps and the generation meter without real provider calls. Merge `85fdd1c`;
  all eight current CI/security checks passed at `06df562`. A separate Python
  3.12 environment passed 948 backend tests (36 local integration skips), 78.29%
  coverage, lint, package consistency and hash-verified archive resolution.

SQLAlchemy 2.1 remains intentional follow-up work. Its plain `postgresql://`
DBAPI default changes to psycopg 3; this repository retains psycopg2. Before an
upgrade, either make the existing dialect explicit across every entry point or
migrate drivers and validate PostgreSQL/pgvector migrations, retrieval,
transactions, history and backup/restore. See the
[upstream migration notes](https://docs.sqlalchemy.org/en/21/changelog/migration_21.html#default-postgresql-driver-changed-to-psycopg-psycopg-3).

## New PR opened during maintenance

[PR #96](https://github.com/jarondlk/ocean-platform/pull/96) was opened by
Dependabot while the original work was being merged. Against `c8c032b`, its
remaining changes are SQLAlchemy 2.0.52 → 2.1.1, cftime 1.6.5 → 1.6.6,
google-auth 2.58.1 → 2.59.0 and googleapis-common-protos 1.75.2 → 1.75.4 across
the inherited locks. Retain it and its branch for separate review; the known
SQLAlchemy driver transition is excluded from this maintenance.

The Dependabot configuration now puts SQLAlchemy routine updates in a separate
`python-sqlalchemy` group before the broad catch-all. This keeps patch updates
eligible and prevents minor driver transitions from blocking unrelated routine
updates. The existing `python-security` group is unchanged, and SQLAlchemy
security alerts/updates are not disabled. Group ordering follows
[GitHub's documented first-matching-group behavior](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference#groups).
A subsequent bot refresh may replace #96 with separate routine/SQLAlchemy PRs;
preserve genuine remaining updates rather than treating them as a duplicate.

## Branch cleanup

All 11 local/remote branch names listed in the audit were rechecked for ancestry,
unchanged tips, open PR references and active worktrees. Remote deletions used
exact-tip leases in one atomic push; local deletion used Git's merged-branch
check. Their commits remain in main. Main, gcp-dev and release tags were retained.

## Security notice dispositions

The initial 69 open notices became zero: two current archive GitPython notices
were fixed automatically by #82; 67 deleted-path notices were individually
marked inaccurate. Each live alert's path, advisory and affected range was
checked immediately before disposition. For each advisory, every current
canonical lock containing the package was verified outside its affected range.
Comments retain the deleted manifest, current source `85fdd1c`, package version
and advisory range. No current-manifest finding was dismissed, and alerting was
not disabled.

| Package / deleted manifest | Individual notices marked inaccurate |
| --- | ---: |
| gitpython / `requirements-archive.txt` | 3 |
| pyjwt / `requirements-analysis.txt` | 13 |
| pyjwt / `requirements-archive.txt` | 13 |
| pyjwt / `requirements-dev.txt` | 13 |
| pyjwt / `requirements.txt` | 13 |
| urllib3 / `requirements-analysis.txt` | 3 |
| urllib3 / `requirements-archive.txt` | 3 |
| urllib3 / `requirements-dev.txt` | 3 |
| urllib3 / `requirements.txt` | 3 |

A final repository API check returned zero open Dependabot, code-scanning and
secret-scanning notices. These are repository alert counts, not proof of no
vulnerabilities: the image scans below found inherited OS/tooling findings.
The browser was signed out and the Mac locked, so the supported menu refresh
could not be invoked. Default-branch updates automatically reconciled the two
real archive notices; the obsolete graph records still need their originating
process identified. Manual dispositions address the notices without claiming
that the exported SBOM has been repaired.


## Container verification and disposition

Cloud Build `2dabe62f-30db-45f7-bc0e-204f226315a3` succeeded with all eight
build/verification/scan steps. It used isolated build containers and an ephemeral
PostgreSQL database, without production secrets or data. Both images are
Linux/amd64 and run as non-root (`app` / `node`). Checks passed for migrations,
isolated backup/restore, API/frontend startup, public liveness/login/provider
routes and anonymous protected-route denial. This was a maintenance verification
build, not an exact-tag release candidate or a production rollout.

Scans used the pinned Trivy 0.73.0 image resolved to
`sha256:7cced7cae583819fc7806d4cbc0dbbc7cad18b99f7d3e235192e6da8c091045c`;
[the upstream release is immutable](https://github.com/aquasecurity/trivy/releases/tag/v0.73.0).
All severities and unfixed findings were retained. Scan command success means
analysis completed; it does not mean the scanner found no vulnerabilities.

| Image | Critical | High | Medium | Low | Unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| Current production API | 3 | 68 | 110 | 106 | 2 |
| Maintenance API | 0 | 55 | 87 | 87 | 2 |
| Current production frontend | 5 | 68 | 113 | 76 | 4 |
| Maintenance frontend | 4 | 63 | 107 | 76 | 2 |

Counts are package/advisory instances reported by the scanner, not confirmed
exploitable application paths. Candidate scans introduce no new high/critical
package/advisory identities compared with the respective deployed image, and
remove 16 API / six frontend high/critical identities. This supports merging the
bounded digest improvements; residual findings remain active hardening work.

Verified artifacts (not deployed):

- API: `sha256:4b923700610ed380f778e31d33422c25c167f62b272c12367753ffa24d68b248`.
- Frontend: `sha256:5481cfd834da476f29d3c0bf0ca46e1b4f8c57083fdf5f855d38ac8cab9296bc`.
- Full scan/startup/image reports:
  `gs://data-infra-infobio_cloudbuild/maintenance/2dabe62f-30db-45f7-bc0e-204f226315a3/`.

### Container hardening follow-up

1. Address inherited frontend bookworm Perl findings:
   `CVE-2026-13221`, `CVE-2026-42496`, `CVE-2026-8376`. The scanner reports no
   bookworm patched version. Investigate supported base/distro updates or
   removing unused affected components, then rerun actual startup/auth checks.
2. Keep `CVE-2023-45853` visible in the raw frontend result. Debian
   [documents](https://security-tracker.debian.org/tracker/CVE-2023-45853)
   that the affected contributed MiniZip code is not built into bookworm's zlib
   binaries. Verify exact binary/component applicability before using that as
   an image-specific inaccurate finding; do not broadly suppress critical scans.
3. Remove unused global npm/npx from the standalone frontend runner after
   verifying that startup and all runtime paths only use `node server.js`.
   Existing high findings in brace-expansion, pacote, sigstore and related
   packages point to the base image's global npm tree, rather than the audited
   application dependency lock.
4. Verify Python SBOM-only tool/vendor records before remediation. The scanner
   reports msgpack 1.1.2, setuptools 70.3.0 and urllib3 2.7.0 as `AnalyzedBy: sbom`
   records without file paths, alongside the installed urllib3 2.8.0 metadata.
   Trace the originating bundled inventory. Update/remove unused installation
   tooling after dependency installation and verify all API/job imports and
   commands; do not weaken the canonical urllib3 lock or assume all such records
   are false positives.
5. Apply available OS security fixes during image construction and assess
   remaining unfixed library findings explicitly. Preserve PostgreSQL 16 client
   compatibility, non-root execution and backup/restore. Rebuild and rescan before
   a production release; preserve complete baseline and rejected results.

[PR #73](https://github.com/jarondlk/ocean-platform/pull/73) merged as
`c674762`, after eight current checks passed at
`df964cefdac03cddb101b888b6cd76152a10870f`.
[PR #74](https://github.com/jarondlk/ocean-platform/pull/74) merged as
`c8c032b`, after the required-check rerun passed all eight checks at
`a53bc234dfeb374be6dc76bf225312885c49a589`. Application/dependency/container source at
merged `c8c032b` matches the scanned maintenance checkout; later documentation
changes are separate. All six original PRs are merged or closed.

The optional title/description update for #82 was rejected by automatic approval
review for unclear metadata-edit authorization and validation wording. The
completed checks are recorded here; that metadata edit has not been retried.


## Remaining boundaries

- The repository's automatic Artifact Registry image scanning was disabled
  because its API is not enabled. This maintenance does not change that project
  configuration; the verification build performs separate full image scans.
- Live GitHub browser graph refresh requires sign-in. Deleted-path records may
  remain in exported dependency metadata after evidence-backed alert disposition;
  reconcile the originating detector/submission once browser access is available.
- SQLAlchemy 2.1 driver work is tracked above; it is excluded from the compatible
  maintenance patch.
- The earlier user-deferred live viewer/researcher and Japanese acceptance checks
  remain deferred. This maintenance does not claim to have completed them.
- No new release or production rollout is part of this maintenance. A deployment
  should use the usual exact-source build, release and acceptance gates.
