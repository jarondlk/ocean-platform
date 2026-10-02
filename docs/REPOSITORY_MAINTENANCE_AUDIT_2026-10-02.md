# Repository maintenance audit — 2026-10-02

Prepared against `main` / `gcp-dev` commit
`a0caf5569d43289ed484770616225c745fd7cf36`, following the v0.6.1 rollout.
This is a preparation record. No branch deletion, PR merge/closure, alert
refresh/dismissal, dependency installation or production change was performed.
`git fetch --prune` removed two remote-tracking references for branches already
deleted upstream; it did not delete a local or remote branch.

## Findings

| Area | Verified state | Recommended disposition |
| --- | --- | --- |
| Branches | 11 completed `codex/` branches exist locally and remotely; every tip is an ancestor of current main with zero unmerged commits | Delete these after a fresh reference/PR/worktree check; retain main, gcp-dev and the six open-PR heads |
| Open PRs | Six Dependabot PRs; all predate current main | Refresh their bases and run current gates; prioritize the narrow archive security fix |
| Dependabot | 69 open notices: 4 critical, 30 high, 35 medium; 19 distinct advisories across three packages | 67 notices reference deleted paths; two are current archive GitPython findings |
| Code scanning | Zero open alerts returned by the repository API | Keep enabled; old PR heads show neutral CodeQL results and lack current complete analysis coverage |
| Secret scanning | Zero open alerts returned by the repository API | Keep enabled; do not expose secret values in audit artifacts |

## Branch cleanup candidates

The following names are fully merged on both local and remote references:

- `codex/v060-deployment-record`
- `codex/v060-final-candidate-record`
- `codex/v061-acceptance-fixes`
- `codex/v061-answer-guards`
- `codex/v061-assay-citation-bounds`
- `codex/v061-candidate-record`
- `codex/v061-chat-patch`
- `codex/v061-deployment-record`
- `codex/v061-edna-answer-bounds`
- `codex/v061-metric-boundaries`
- `codex/v061-release-acceptance`

Both tips of `codex/v060-deployment-record` are preserved in main despite their
different local/remote hashes: local `6fd37eb`, remote `0175bc7`. Their difference
is not lost work. There is one checkout, currently on `gcp-dev`; none of the
cleanup candidates is checked out in another worktree. No unmerged branch exists
outside the six live Dependabot PRs. `main` and `gcp-dev` are synchronized.

Before deletion, refresh origin and re-read open PRs, verify each expected tip
still matches this audit and remains an ancestor of main, and check worktrees
and the working tree again. Delete only the listed branch references, preserve
release tags and commit history, and prune tracking references afterward. The
six Dependabot branch tips have one unique commit each and must be retained
until their PR disposition is complete.

## Open pull requests

The historical heads have four successful ordinary CI checks except PR #84;
CodeQL is neutral on all six. These results do not establish compatibility with
the current v0.6.1 source or a complete current security check.

| PR | Change | Behind current main | Observed checks | Proposed action |
| --- | --- | ---: | --- | --- |
| [#82](https://github.com/jarondlk/ocean-platform/pull/82) | GitPython 3.1.61 → 3.1.62 in archive input/lock | 27 commits | Four ordinary gates passed; CodeQL neutral | Preferred narrow patch: smaller generated-lock diff than #81; refresh, verify hashes/archive resolution, raise advisory-floor regression and run current gates |
| [#81](https://github.com/jarondlk/ocean-platform/pull/81) | Same GitPython version and hashes as #82, with wider lock-comment churn | 27 | Four ordinary gates passed; CodeQL neutral | Keep until the selected fix merges; then close as duplicate and delete its head |
| [#73](https://github.com/jarondlk/ocean-platform/pull/73) | Python 3.12-slim digest refresh | 37 | Four ordinary gates passed; CodeQL neutral | Verify digest/platform provenance, build and scan the actual API image, then assess a separate rollout |
| [#74](https://github.com/jarondlk/ocean-platform/pull/74) | Node 22-slim digest refresh in all three stages | 37 | Four ordinary gates passed; CodeQL neutral | Verify digest/platform provenance, build and scan the actual frontend image; validate auth/proxy and runtime startup |
| [#86](https://github.com/jarondlk/ocean-platform/pull/86) | Next/jose patch updates; React/renderer/types 19.3 updates and transitive changes | 20 | Four ordinary gates passed; CodeQL neutral | Refresh and review as frontend maintenance; retain renderer/version compatibility and run settings/auth/UI regressions |
| [#84](https://github.com/jarondlk/ocean-platform/pull/84) | Broad Python group across all eight inputs/locks, including SQLAlchemy 2.1.1 | 27 | Backend tests and migration step failed | Hold the group; separate its compatible updates from the driver migration and security fix |

### Confirmed #84 failures

The actual backend log fails
`test_linux_sqlalchemy_greenlet_dependency_is_explicitly_locked`, because it
hard-codes `greenlet==3.5.5` while the PR upgrades to 3.5.6. Keep the meaningful
Linux lock invariant; validate explicit presence and agreement across input and
locks, together with an intentional supported floor, rather than freezing an
unrelated exact release in the test.

The PostgreSQL job fails during application migrations with
`ModuleNotFoundError: No module named 'psycopg'`; the trace imports
`sqlalchemy.dialects.postgresql.psycopg`. SQLAlchemy 2.1 changes the default for
plain `postgresql://` URLs to psycopg 3, while this repository installs
`psycopg2-binary`. This is documented in the
[SQLAlchemy 2.1 migration notes](https://docs.sqlalchemy.org/en/21/changelog/migration_21.html#default-postgresql-driver-changed-to-psycopg-psycopg-3).

Keep the existing SQLAlchemy 2.0 line for the first bounded maintenance patch.
Handle SQLAlchemy 2.1 as explicit compatibility work: either keep psycopg2 with
an explicitly selected dialect throughout application/migration entry points,
or intentionally migrate to psycopg 3. Test PG16/pgvector migrations, retrieval,
transactions, metadata/history and backup/restore under the selected driver.
Changing only a CI environment variable would leave the production URL issue
unresolved. Do not merge the failing group or disable its checks.

## Security notice triage

The four critical notices are repetitions of the same
[PyJWT PEM/HMAC advisory](https://github.com/advisories/GHSA-ffc3-869f-jxw9)
against deleted root-level manifests. The affected version reported by the graph
is 2.13.0. Current runtime/dev/analysis/archive locks all contain PyJWT 2.15.1
and urllib3 2.8.0, outside the vulnerable ranges in these open PyJWT/urllib3
notices. The container copies `requirements/runtime.txt` into its image-local
`requirements.txt`; it does not install the removed repository-root file.
GitPython is absent from the serving runtime/dev/analysis sets.

| Alert group | Open notices | Current source disposition |
| --- | ---: | --- |
| PyJWT | 52 | All against four removed root requirement files; patched current locks |
| urllib3 | 12 | All against the removed root files; current locks use the reported patched floor 2.8.0 |
| GitPython, deleted root archive path | 3 | Old 3.1.57 record; path removed and archived replacement already above the older 3.1.60 fixes |
| GitPython, current archive input/lock | 2 (#283/#300) | Real current 3.1.61 pin; update to 3.1.62 |

The two current findings share
[GHSA-59cr-6r3x-644w](https://github.com/advisories/GHSA-59cr-6r3x-644w):
submodule path traversal, medium severity, patched in 3.1.62. The optional
Streamlit archive is separate from deployed Next/FastAPI. Update its dependency
rather than dismissing a current vulnerable pin. The existing archive security
regression still permits 3.1.59 and needs the new floor.

GitHub's fresh SBOM export still contains both obsolete PyJWT 2.13.0/urllib3
2.7.0 records and current patched versions. The four old manifest paths are
absent from tracked main, not merely unused by convention. A similar stale-path
incident was documented in [SECURITY.md](SECURITY.md#stale-dependabot-alert-closure--2026-09-11).
The exact detector retaining these obsolete records was not identified by the
SBOM export, so graph-refresh behavior must be observed before deciding which
alerts need manual disposition.

GitHub documents **Refresh Dependabot alerts** in the repository's Dependabot
menu; it rescans manifests and is limited to once per hour. Submitted build-time
snapshots require refreshing their originating process separately. See
[dependency graph troubleshooting](https://docs.github.com/en/code-security/reference/supply-chain-security/troubleshoot-dependabot/dependency-graph-errors)
and [submission precedence](https://docs.github.com/en/rest/dependency-graph/dependency-submission).

First refresh the graph, then re-query alert paths/versions and the exported
SBOM. If deleted-path notices persist, identify any stale submission/detector
and repair its input. Only close notices as inaccurate when their individual
manifest/range is proven obsolete, retaining the evidence and reason; do not
bulk-dismiss by severity. The expected source-backed split is 67 obsolete-path
notices and two real archive notices. It is not a promise that all GitHub alerts
will disappear immediately.

## Ordered execution plan

1. **Security metadata reconciliation:** trigger the supported graph refresh;
   capture before/after notice IDs, paths, ranges and SBOM. Resolve obsolete
   records with documented evidence, while preserving current findings.
2. **Narrow archive security patch:** refresh #82, GitPython 3.1.62 input/hashed
   lock and security-floor regression; validate archive dependency resolution,
   dependency consistency and current CI/security checks. Keep runtime locks
   unchanged. After merge, close duplicate #81; re-check #84's overlapping fix.
   This archive-only dependency change does not require a serving redeployment.
3. **Completed branch cleanup:** remove the 11 verified merged local/remote
   branches after revalidation. Retain main/gcp-dev, release tags and every
   unresolved PR head.
4. **Container maintenance:** assess #73/#74 with actual container builds,
   digest/platform checks and image vulnerability scans. Run the relevant runtime
   and auth/database smoke checks. A production rollout is a separate action.
5. **Frontend routine maintenance:** refresh #86; check production and development
   dependency audits, matched React/renderer versions, tests/typecheck/build,
   source settings lifecycle and normal sign-in/proxy boundaries.
6. **Python maintenance:** split or reconstruct #84 after the security patch;
   retain SQLAlchemy 2.0 initially, repair the lock-invariant test, regenerate
   inherited locks and test package consistency/full backend/PG integration.
   Keep SDK changes visible: provider-effective controls and actual-generation
   metering need validation if google-genai changes. Plan the SQLAlchemy 2.1
   driver work separately; close #84 only when its replacements are concretely
   tracked or merged.

These checks assessed repository alerts, tracked manifests and existing CI
logs. No new deployed-image/OS vulnerability scan or independent penetration
test was performed. Counts are alert instances, not demonstrated exploit counts.

Private API snapshots and CI logs are retained under `/tmp/ocean-v061-release`;
no credentials, identities or raw secret values are included in this document.
