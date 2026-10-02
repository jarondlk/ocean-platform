# v0.6.1 operations

**Updated 2026-10-02 JST. Source merged; candidate acceptance, release and rollout pending.**

The authorized sequence is recorded in [the patch plan](RELEASE_0.6.1_PLAN.md).
Japanese-specific work/acceptance is explicitly deferred; other acceptance gates
remain in force. No production schema/publication mutation is planned.

## Refreshed baseline

Cloud Run inventory on 2026-10-02 confirmed `ocean-platform-v060-sec1001` still
receives 100% traffic, with the `v060-production` tag. The v0.5.0 production,
staging and maintenance tags remain at zero traffic. Project `data-infra-infobio`,
region `asia-northeast1`, canonical site `https://oceaninfobio.com`.

Current serving image digests and resource/security settings are retained in the
private refreshed service inventory. The candidate was derived from that live
definition. Serving limits and identities were preserved. Cloud login currently
works.

The source/package candidate version is `0.6.1`; it is not yet a published Git tag.
The compatible v0.6.0 rollback revision and schema head `20261001_0014` remain.

## Release gates still pending

- Live viewer/researcher account checks or an explicit user disposition; current-admin, mobile/keyboard and history checks passed below.
- The bounded English scientific matrix is accepted; retain earlier rejected attempts and recorded limits.
- GitHub tag/release only after candidate acceptance or an explicit recorded
  user deferral; traffic promotion and post-cutover checks afterward.
- Align the evaluation job after acceptance/promotion; retain other unchanged
  manual job runtimes and complete development-branch synchronization.

## Source and build

[PR #85](https://github.com/jarondlk/ocean-platform/pull/85) merged as
`7e2d31235a75ecd79cdebb7b54c8cb75fd948811`. All eight required GitHub checks
passed on patch head `c7117c2`; the merged source has the identical tree.
Cloud Build `bc71a737-d1a4-4906-955f-448331cd79de` was submitted from that
exported source. Its Python/frontend verification and both image builds passed;
image publication and final build status succeeded. That first candidate is
superseded by the acceptance follow-up below.

The five normal manual jobs currently retain their v0.6.0 images. The
follow-up changes the shared answer prompt, so `ocean-evaluation` needs image
alignment only after candidate acceptance/promotion. Ingestion, migration,
embedding and eDNA-processing runtime paths and the serving dependency lock
are unchanged. No ingestion or embedding job is run for QA.

## Acceptance follow-up

The first build succeeded and its revision `ocean-platform-v061-patch1002`
was ready at zero traffic. All 48 deterministic runs passed structural/numeric
checks, but manual review found a classification-exclusion wording gap.
The model execution stopped on its 14th answer after an invented `Scope`
citation. The first attempt meter was not wired to the API runtime and six
large stdout exports were truncated; its zero-call report is invalid.
See [scientific dispositions](RELEASE_0.6.1_SCIENTIFIC_QA.md).

[PR #87](https://github.com/jarondlk/ocean-platform/pull/87) merged as
`5f68c34017827e042749ef87432022c750fd6b91`, with an identical tree to final
head `511a21b`. All eight required checks passed on that head. It fixes the
wording/prompt boundaries and operator metering/evidence capture; backend
validation is 939 passed, 36 integration skips, 78.30% coverage.

Replacement Cloud Build `a36d7ad7-5f0a-4ebb-ad5b-af9223a9dc7e` succeeded from
that exact exported source. The later user instruction authorized resolving QA and access, then publishing
and deploying. Subsequent bounded corrective runs are recorded below. No tag,
release or traffic promotion has occurred.

## Earlier replacement candidate

Revision `ocean-platform-v061-patch1002b` was Ready with tag `v061-candidate`
and zero traffic before the later candidate-access correction. `ocean-platform-v060-sec1001` retains 100% traffic. Existing
v0.5.0 staging/maintenance/production and v0.6.0 production tags are retained.
Serving identities, secrets, auth, mounts and limits match the refreshed live
definition; only revision name, image digests, source commit and candidate tag
changed.

| Artifact | Immutable value |
| --- | --- |
| Built source | `5f68c34017827e042749ef87432022c750fd6b91` |
| Exported Git archive SHA-256 | `69d61f70bb7a323ef31aa1b82308a03a3afb092945fc3f5c63e9899be4b09fda` |
| API image digest | `sha256:b16e83fa5b9b241ae6ccccb59aebc046f5a414fbe95cd4f4f9fc2423b5c1fbe0` |
| Frontend image digest | `sha256:e6b84a85100da2335427005e3678e95156de5d53dbc26b22695660dc01c2ba39` |

Images use `asia-northeast1-docker.pkg.dev/data-infra-infobio/ocean-platform`.
The exported Git archive identifies the source tree; Cloud Build deliberately
excludes files covered by the repository's normal `.gcloudignore`.

Execution `ocean-v061-acceptance-nrcrz` passed all 48 deterministic runs on
this image, with zero actual generation calls under the corrected meter and
no chat-history writes. Both environmental-filter repeats verified the new
boundary statement; other answer strings match the first batch. Schema and
publication IDs stayed unchanged. Anonymous frontend-proxy requests to chat,
capabilities and filter choices returned 401.

Normal browser navigation to the final tagged chat URL ended at canonical
production login. This preserved auth boundary blocks positive candidate
UI/history acceptance through that tag. Mobile and live viewer/researcher
acceptance remain pending. The first model batch's failure is not waived;
the fresh capped batch awaits explicit approval.

After that earlier verification, the temporary `ocean-v061-acceptance` job was deleted.
That earlier inventory contained the five original manual jobs, with their
specifications unchanged. The bounded serving-log check found no ERROR entries
since 2026-10-01 19:20 UTC; this does not establish a load-performance result.
A newly authorized scientific batch will recreate the same bounded job with
the recorded replacement image.

## Final corrective candidate and access

Normal Google candidate sign-in now succeeds. After the user approved the exact
change, one temporary redirect URI was added to the existing OAuth client:
`https://v061-candidate---ocean-platform-6jsvoc67ra-an.a.run.app/api/auth/callback/google`.
The two existing callbacks and authorized origins were retained. A separate QA
revision sets `AUTH_URL` to that candidate origin; the production-ready revision
retains `https://oceaninfobio.com`. No roles, IAM permissions or authentication
bypasses were added. Remove the temporary callback and QA route after acceptance.

Fresh model execution `ocean-v061-acceptance-sw88n` completed 31 actual generations
with full evidence captures, but manual review rejected invented multiword
citations and an unknown sample called environmental. [PR #90](https://github.com/jarondlk/ocean-platform/pull/90)
merged after all eight required checks. Backend validation: 945 passed, 36 skips,
78.31% coverage. The new source/build passed both Python and frontend build gates.

| Artifact | Immutable value |
| --- | --- |
| Built source | `26739772d2bebd9fcdaeccef440b382aa4632e34` |
| Cloud Build | `28706155-20bc-4f7c-90ce-b805fff0b5ce` |
| Git archive SHA-256 | `e1e759aa2b82ef79abd12d67008e3f45d47e6a11c8cf5001fefab89acdaabf55` |
| API digest | `sha256:2d0984189610080d6f7807fec588f8f2dbf34016017e130c23ab5fdc72983f29` |
| Frontend digest | `sha256:4a9a636c0df0c8b7e8efa6d5ad5029e404453c0e5b032b5a3221081be5d8a238` |
| Canonical candidate | `ocean-platform-v061-final1002`, tag `v061-final`, zero traffic |
| Authenticated QA candidate | `ocean-platform-v061-finalqa1002`, tag `v061-candidate`, zero traffic |

Fresh service inventory confirms v0.6.0 still receives 100% traffic. Final candidate
anonymous chat/capability/filter endpoints return 401. All serving identities,
secrets, mounts and limits remain retained; both final revisions use the same
images/source. The temporary operator job now uses the final API image, one task,
no retries and its existing 33-actual-attempt bound. Execution
`ocean-v061-acceptance-n9vfp` completed all 31 calls; manual findings required PR #91 and superseded these candidates.

The real admin's earlier candidate UI interactions independently passed readback
in `ocean-v061-acceptance-9kgtq`: seven specified IDs, same owner, expected outcomes,
scopes/generation controls, evidence hashes, prompt metadata, audits and timestamps.
This verification was read-only. Real chat QA itself created normal history and
immutable aggregate evidence. Mobile/keyboard/all-off reload/reset checks passed.
Final-image representative UI/history/evidence checks and live viewer/researcher
account availability remain pending. See [the scientific QA record](RELEASE_0.6.1_SCIENTIFIC_QA.md).

## Temporary local resources

A task-owned PostgreSQL 16 container `ocean-v061-pg` on loopback port 55461 held
isolated fixture/corpus data. Its backup/restore passed with 28 tables and the
restore database was removed. The fixture container is removed and the Podman
VM is restored to its original stopped state. Local preview listeners on
3006/8006/11436 are stopped; the task-created preview tab is closed. Closing
the older stale preview tab failed debugger synchronization twice, so its UI
closure is not claimed. Existing user containers are unrelated and retained.

## Current response-bounds candidate

PR #91 merged as `27e821cf7a0634aab1d744708788ff8f6efa8584` after all eight required
checks passed. Cloud Build `3bd02481-153e-49fe-8732-96621759e54a` succeeded from that
source; archive SHA-256 `b8675e4c8284be4033a944d4565cec49495427f98236fb5cd5672e32a05ed4ad`.

| Artifact | Immutable value |
| --- | --- |
| API digest | `sha256:274a16a603a49035655c174dff3700bf0fd46e9619fba58bea02aa79245b1da4` |
| Frontend digest | `sha256:e54e8bd2214d6b4e9156e104745f9fb979f08f867b67fcf5f13e21fd28bfca16` |
| Canonical candidate | `ocean-platform-v061-bounds1002`, tag `v061-final`, zero traffic |
| Authenticated QA candidate | `ocean-platform-v061-boundsqa1002`, tag `v061-candidate`, zero traffic |

Both revisions are Ready. Production still routes 100% to v0.6.0. Normal admin
sign-in and settings hydration work on the final QA image. The existing temporary
QA job is executing the 26 affected eDNA/metagenome repetitions as
`ocean-v061-acceptance-hzjd5`, completed 26 actual SDK attempts; five reviewed
CTD/SST repetitions have byte-identical prompts and are retained. Manual
acceptance failed on concentration/identity/method explanations; PR #92 is
merged as `009ab8e97052f5d5bb2e958630d0371561792c5c`, all eight checks passed,
and the new immutable build is pending. The same historical aggregate downloaded through
the chat citation panel and its payload matches its original SHA-256.

## Current metric/identity correction build

Source `009ab8e97052f5d5bb2e958630d0371561792c5c` passed all eight required
GitHub checks. Cloud Build `2a56297c-ee3c-4be5-a0c6-39386dd0c47a` succeeded;
archive SHA-256 `878a20bad8d6d0cc8b5301053a36e8cf7cbbcd1ec356201ae02f99c14bb76e9d`.

| Artifact | Immutable value |
| --- | --- |
| API digest | `sha256:733f6ff782df8a0e3b0f0875c396881cd790bc2fe0e048144bdfe43f12199c1f` |
| Frontend digest | `sha256:5b5308123f1ccb4bc928af5a9a91c3779951a5aa6be3800e861e0687d3fd069f` |
| Canonical revision | `ocean-platform-v061-metrics1002` |
| QA-origin revision | `ocean-platform-v061-metricsqa1002` |

Zero-traffic deployment and affected scientific acceptance are in progress.
Execution `ocean-v061-acceptance-ftbrz` uses 26 planned repetitions, a 33 actual
SDK-attempt cap, one task/no retries, the existing identity/secret/read-only
data mount and no chat-history persistence. Production remains v0.6.0 at 100%.
Read-only execution `ocean-v061-acceptance-rtjt5` verified the ninth admin UI
interaction in 18 seconds. No schema/publication migration or corpus rewrite
has occurred. Live viewer/researcher disposition remains pending.

## Current assay-citation correction

PR #93 merged source `fd7dd4175eebb87b20450fe67d2bfac1cff3f8a2`, with all eight
required CI checks passed and 947 local backend tests passed. Its exact-source
Cloud Build `2415f393-6608-4f91-988a-324ce2640d1c` succeeded. Only the six
rare-taxon prompts change; 25 manually reviewed model results are retained.
The preceding model run stopped on a correctly rejected unrecognized citation
after 24 SDK calls; three bounded remaining calls completed, for 27 total
attempts within the 33-call allowance. Manual review also found an aggregate
used as the citation for assay-only metadata, requiring this final correction.
No candidate scientific quality pass or promotion is claimed yet.

The tenth normal admin UI interaction passed independent read-only history
verification in `ocean-v061-acceptance-g2tdc`. Live viewer/researcher account
availability or explicit user disposition remains pending. Production still
serves v0.6.0 at 100%; no v0.6.1 tag or release exists.

## Final built candidate artifacts

| Artifact | Immutable value |
| --- | --- |
| Built source | `fd7dd4175eebb87b20450fe67d2bfac1cff3f8a2` |
| Git archive SHA-256 | `8aedc7e19ed0adc9dc8f2ecc445eea4f07a5b765f1cd557f647094863cf3d3ad` |
| API digest | `sha256:5e783f9abfe436b05c0443658a4b1e8c6f231220d9721c542e20eaea8549c3d1` |
| Frontend digest | `sha256:fcb1db7345163a1f38f7cfacf0b0c516a706142f1432601926c49116de904293` |
| Canonical candidate | `ocean-platform-v061-assay1002`, tag `v061-final`, zero traffic |
| QA-origin candidate | `ocean-platform-v061-assayqa1002`, tag `v061-candidate`, zero traffic |

Both final candidates are Ready at zero traffic. Scientific execution
`ocean-v061-acceptance-5mtgn` passed six changed rare-taxon repetitions with
six actual SDK calls and complete manual claim/citation review. All 25 retained
model prompts are unchanged; the 31-case bounded English matrix is accepted.
Anonymous final chat/filter/capability requests return 401. The final-source
browser count reproduction and its eleventh saved record passed independent
read-only scope/fingerprint/prompt/audit verification in
`ocean-v061-acceptance-wqp7g`.
Live viewer/researcher disposition remains pending; no tag/release/promotion.
