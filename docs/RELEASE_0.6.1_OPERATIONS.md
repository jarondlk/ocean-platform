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

- Candidate authenticated admin/history/source checks; live viewer/researcher
  sessions and mobile acceptance remain pending.
- Repeated English scientific matrix and manual claim-to-evidence dispositions.
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
that exact exported source. No further model calls are made while explicit
authorization for a fresh capped batch is pending. No tag, release or traffic
promotion has occurred.

## Current replacement candidate

Revision `ocean-platform-v061-patch1002b` is Ready with tag `v061-candidate`
and zero traffic. `ocean-platform-v060-sec1001` retains 100% traffic. Existing
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

After verification, the temporary `ocean-v061-acceptance` job was deleted.
The final inventory contains the five original manual jobs, with their
specifications unchanged. The bounded serving-log check found no ERROR entries
since 2026-10-01 19:20 UTC; this does not establish a load-performance result.
A newly authorized scientific batch will recreate the same bounded job with
the recorded replacement image.

## Temporary local resources

A task-owned PostgreSQL 16 container `ocean-v061-pg` on loopback port 55461 held
isolated fixture/corpus data. Its backup/restore passed with 28 tables and the
restore database was removed. The fixture container is removed and the Podman
VM is restored to its original stopped state. Local preview listeners on
3006/8006/11436 are stopped; the task-created preview tab is closed. Closing
the older stale preview tab failed debugger synchronization twice, so its UI
closure is not claimed. Existing user containers are unrelated and retained.
