# v0.7.2 operations

Prepared 2026-10-06 JST for a separately versioned source release, followed by
authenticated GCP image acceptance and rollout. The user requested resolving
open PRs and the release before GCP deployment. Do not retag v0.7.1 or describe
v0.7.2 as deployed before promotion and post-cutover verification.

## Source and PR disposition

The sole open PR at the initial check was
[#112](https://github.com/jarondlk/ocean-platform/pull/112). No reviews or inline
feedback remained unresolved; the exact head passed all four required CI jobs
and CodeQL. It merged as `9946dcb54f4a8a5817e7039fe809deca2aee2249`.
It includes the readiness/CLI/build fixes and refreshed operating docs from
[the pre-deployment audit](PRE_DEPLOYMENT_AUDIT_2026-10-06.md).

The source-map-js 1.2.2 fix was already merged in
[#111](https://github.com/jarondlk/ocean-platform/pull/111). The v0.7.2 metadata
aligns FastAPI, frontend package and lock root versions without changing other
dependency lock entries. [Release notes](RELEASE_NOTES_0.7.2.md) describe the
bounded patch and outstanding acceptance. The GitHub annotated tag/release must
pin the exact merged, passing source, not an unverified later commit.

## Last verified production and pending cloud work

Production remains v0.7.1, revision `ocean-platform-v071-source1005`, exact
tag/runtime source `e157fb004871083df25d5d094852fed417a9c8c6`, schema 0016.
See [v0.7.1 operations](RELEASE_0.7.1_OPERATIONS.md) for retained build/digests,
private backup, roles/history/corpus preservation, job alignment and cleanup.
No new migration is required for v0.7.2; live schema still needs independent
verification after refreshed CLI authentication.

Cloud work is pending, with no v0.7.2 image digests or rollout claimed here:

1. Refresh CLI sign-in and compare the fresh live service/jobs/SQL/storage/IAM
   inventory and cost headroom against retained receipts. Preserve identities,
   secrets, canonical auth, external job mode, mounts, limits and rollback tags.
2. Build from the exact published tag/source. Run combined source gates and
   `deploy/gcp/cloudbuild-candidate-qa.yaml` with `_QA_REPORT_PREFIX=v072-qa`.
   Collect full unsuppressed scans and independently verify source-map-js 1.2.2
   in the actual standalone image. Reassess stable OS fixes/residuals in #104.
3. Take/restore-test a fresh private production backup before changing shared
   API jobs, verify schema/readiness and original history/identity/publication
   bindings, and remove the disposable restore database.
4. Derive a zero-traffic canonical revision from the fresh live definition.
   Verify exact images, authentication/session/sign-out, scoped source coverage,
   overlap abstention and history. Preserve explicit mobile/scientific deferrals.
5. Promote after acceptance, verify canonical production and align the affected
   existing API jobs without running manual batches. Retain old job definitions
   and v0.7.1 application rollback; keep schema 0016.
6. Remove only task-owned temporary resources/access. Record exact source/build/
   digests/traffic, verification and cleanup; close #110 only after its deployed
   image checks pass. Source publication alone does not resolve it.

Real data and scientific approvals remain #89/#102/#103; mobile is #107 and
sign-out is #108. Existing repository advisory dispositions and dated v0.7.1
image mitigations are evidence for their dates, not new runtime clearance.
