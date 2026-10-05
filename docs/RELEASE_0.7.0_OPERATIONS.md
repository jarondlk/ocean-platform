# v0.7.0 operations

Prepared 2026-10-05 JST. **Release preparation in progress; production remains
v0.6.1.** The user explicitly authorized release/deployment of the software and
deferral of the six original real ANEMONE/SST demonstrations. Issue #89 remains
open; this authorization does not approve scientific registry or data decisions.

## Release scope and gates

Ship the reviewed registry, exact analysis/publication/API/Chat and visual/export
software. Defer the six real-data cases, full third-reference methods reading,
historical acquisition and representative real-cohort performance/coverage
qualification as part of the unmet scientific evidence preparation. No actual
classifications, sampling/SST registries or research publications will be applied
to manufacture a demo.

Final-source CI/image QA, residual OS advisory disposition, fresh production
backup/isolated restore, migration/count preservation, authenticated candidate
UI/history/access checks and production verification remain required. Prior
v0.6.1 viewer/researcher waivers are not inherited.

## Baseline and prepared procedure

- Project `data-infra-infobio`, region `asia-northeast1`, service `ocean-platform`,
  canonical origin `https://oceaninfobio.com`.
- Fresh October 5 read-only traffic inventory: 100% on
  `ocean-platform-v061-assay1002`; historical rollback tags remain.
- PR #99 is the implementation/release candidate. Final version declarations
  are prepared as 0.7.0; a tag/release has not yet been created.
- Build a clean Git export of the exact merged source using
  `deploy/gcp/cloudbuild-candidate-qa.yaml`. Retain every scan severity/unfixed
  finding and collect runtime security inventory from both images.
- Use a bounded temporary operator job with the existing `ocean-jobs` identity,
  Cloud SQL connection and database secret. First take a retained backup and
  restore-test it in an isolated database; then apply the additive migration,
  verify old table counts and registry state, and remove the temporary job.
- Derive zero-traffic canonical/QA revisions from the live production definition,
  changing only immutable images/source/revision metadata and the QA auth origin.
  Preserve serving IAM, secret references, mounted data and resource limits.
- Obtain action-time approval for any temporary Google OAuth callback addition
  in the browser. Complete supported candidate sign-in; never impersonate live
  viewer/researcher users or treat mock sessions as their acceptance.
- After acceptance, publish the exact-source v0.7.0 GitHub release and promote
  the canonical revision. Align changed manual job images without running their
  ingestion/embedding/evaluation commands. Verify production before cleanup.

## Runtime security disposition preparation

The stable Debian OS package advisories remain visible in full scans. The final
runtime build removes `infocmp`, `nsenter`, `mount`, `umount` and setuid/setgid
bits. The read-only inventory additionally requires absent `systemd-homed` and
Perl `Archive::Tar`, no configured fstab entries and no effective capabilities.
Application subprocess paths were inspected: they use fixed Git/Python/native
database commands, not these affected tools or privileged ACL operations.
These changes are prepared; final image evidence and scoped per-CVE dispositions
must be recorded before promotion. No scanner suppression or alert dismissal
is part of this procedure.

## Rollback

Before promotion, retain `ocean-platform-v061-assay1002` and record the five manual
job definitions/images. Roll back traffic to that known-good application while
retaining the additive schema. Restore prior manual-job images/metadata as needed.
Do not downgrade/restore production automatically or erase immutable evidence.
A destructive database restore would require a separately reviewed decision.
