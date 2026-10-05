# v0.7.0 operations

Updated 2026-10-05 JST. **v0.7.0 is published and deployed at 100% traffic.** The user explicitly authorized release/deployment of the software and
deferral of the six original real ANEMONE/SST demonstrations. Issue #89 remains
open; this authorization does not approve scientific registry or data decisions.

## Release scope and gates

Ship the reviewed registry, exact analysis/publication/API/Chat and visual/export
software. Defer the six real-data cases, full third-reference methods reading,
historical acquisition and representative real-cohort performance/coverage
qualification as part of the unmet scientific evidence preparation. No actual
classifications, sampling/SST registries or research publications will be applied
to manufacture a demo.

Final-source CI/image QA, scoped residual OS dispositions, fresh production
backup/isolated restore, migration/count preservation, actual admin candidate
UI/history/access and production verification passed. Live viewer/researcher QA
was separately user-deferred on 2026-10-05 JST; no prior waiver was inherited.

## Historical baseline and prepared procedure

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

## Historical runtime disposition preparation

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

## Verified execution checkpoint — 2026-10-05 JST

PR [#99](https://github.com/jarondlk/ocean-platform/pull/99) is merged at
`6167949177e437843b3390ca6fbc9ec9ab705bfc`. Final PR CI run 328 and merged-source
CI run 329 passed. Fresh repository Dependabot/code-scanning open-alert queries
returned zero; these are separate from the retained OS image findings.

Exact merged-source Cloud Build `2aa26d29-c08d-415c-a81c-863ff495cf00` passed all
six steps. API digest is
`sha256:363cf5674796e0051cc6a0901b88144fb4267e80b1ef55228fb8bc9c3e36d862`;
frontend is
`sha256:e89fa409630b2a29fa5519a454749ceec66cac1b4602090fa0e34754b698e9ef`.
Final runtime inventory and scoped eight-CVE dispositions are in
[V0.7.0_CONTAINER_QA_2026-10-05.md](V0.7.0_CONTAINER_QA_2026-10-05.md).

The separate bounded `ocean-v070-release-ops` job used the existing jobs identity,
Cloud SQL connection and DB secret, with one task, no retries and a 15-minute
limit. Its backup execution `ocean-v070-release-ops-6c8l8` succeeded: 208,065,119
bytes, SHA-256
`a243183a06f0a42a593bff2b00d9efe34779cbade3a18a72b9667f664863121b`.
The isolated restore verified counts and removed its temporary database. The
private backup and sanitized receipts are retained under
`gs://data-infra-infobio-ocean-data/backups/v070/software-20261005/`; bucket IAM
contained no public principals and public-access prevention is enforced.

Migration execution `ocean-v070-release-ops-df95v` successfully advanced production
from `20261001_0014` to additive `20261004_0015`. All prior table counts,
source-publication references, retrieval/embedding counts, user identity/role
hashes and completed history hashes were preserved. The six new registry tables
remain empty. Counts included 3,498 eDNA occurrences/assays, 349,638 assignment
rows, 13,932 standards and 7,319 retrieval documents. The application rollback
remains v0.6.1 with this compatible additive schema retained.

Canonical `ocean-platform-v070-software1005` and normal-auth QA
`ocean-platform-v070-softwareqa1005` are deployed at **zero production traffic**.
Both were derived from the actual serving revision, preserving identities,
secrets, read-only mounted data, resources and auth enforcement. The temporary
`v070-candidate` callback was explicitly approved and saved in the existing
Google OAuth client, with existing callbacks unchanged.

Real Google admin sign-in succeeded. Research reviews rendered zero records
with the expected role separation; existing admin feedback/history rendered.
Source checkboxes and actual eDNA filter choices loaded. Clearing all sources
disabled Ask. eDNA-only scope persisted across page navigation. One real Vertex
request returned only eDNA citations and explained that overall detection
frequency was unavailable; it was a legacy scoped retrieval answer, not a
published research result. An exact catalogue request returned 3,498 occurrences,
343 controls and 3,155 unresolved-control records without invoking the model.
Candidate preferences were restored to all four sources with no filters.
Anonymous review/analysis/history proxy requests returned 401; login/provider
discovery returned 200.

Read-only execution `ocean-v070-release-ops-mgvg7` verified both newly generated
admin Chat records: completed status, owner role, eDNA-only scope, evidence
fingerprint, prompt hash and zero invalid citations. Baseline completed histories
and all corpus/publication/user hashes remained intact; the chat count advanced
from 183 to 185. New audit/history/aggregate records are normal QA effects;
ephemeral rate-limit bucket counts are observed, not treated as immutable corpus.

**Awaiting separate user disposition:** live viewer/researcher sign-in sessions
are unavailable. Their isolated role tests passed, but no prior waiver is
inherited. The six scientific demos are already explicitly deferred. The GitHub
release is an unpublished draft; v0.7.0 has not been tagged or promoted. Production
still serves v0.6.1. Manual-job alignment, final verification, temporary callback/
QA route/operator cleanup and publication remain pending that live-role decision.

Private reviewable operator scripts, service definitions, image metadata and
receipts are under `/tmp/ocean-v070-release/`. Preserve the draft's exact source
and digests; do not rebuild or retag a different source merely for operational
documentation. The prepared promotion definition restores the canonical auth
origin as the latest service template, retains prior rollback tags, and removes
temporary QA tags.

## Published rollout and cleanup — 2026-10-05 JST

The user explicitly instructed: “Proceed; defer live viewer/researcher QA.” The
six real-data demos remain separately deferred. Both dispositions are recorded
in the published [v0.7.0 release](https://github.com/jarondlk/ocean-platform/releases/tag/v0.7.0).
The annotated tag pins exact built source `6167949177e437843b3390ca6fbc9ec9ab705bfc`;
operational documentation follows in PR #100 without retagging the runtime.

`ocean-platform-v070-software1005` now serves **100% production traffic** with
`v070-production` tag. The latest service template is the canonical revision and
`AUTH_URL=https://oceaninfobio.com`; all historical rollback tags remain. The
compatible v0.6.1 rollback revision is `ocean-platform-v061-assay1002`, retained
with the additive 0015 schema. Temporary `v070-final` / `v070-candidate` tags were
removed during promotion. The temporary callback was removed and re-opening
Google client settings verified exactly the original two callbacks/origins.

Canonical Google admin sign-in passed. Overview showed 7,319 retrieval documents,
162 CTD casts, 79 SST days and healthy API/database/model/publication signals.
An eDNA-only exact query again returned 3,498 source occurrences / matching assays,
343 controls and 3,155 unknown-control records without the model, with 7 valid
citations and none invalid. Preferences were restored to all four sources/no
filters. Anonymous research/analysis/history proxy requests remained 401;
login/provider discovery were 200. A bounded 20-minute query for HTTP 5xx errors
on the new serving revision returned zero records; this is a deployment-window
check, not ongoing monitoring or arbitrary scientific-answer acceptance.

All five existing manual jobs (`ocean-anemone-process`, `ocean-embedding`,
`ocean-evaluation`, `ocean-migrate`, `ocean-pipeline`) now pin the exact verified
API digest and release source metadata. New shared research/database/runtime
modules justify backend alignment. Each functional job definition was compared
before/after: command/args, identity, secret refs, mounts, resource/task/timeout/
retry settings were retained. Only image/source metadata and CLI-generated nonce
changed. No ingestion, embedding, evaluation or other manual batch command ran.
Original job definitions remain in the private release records for rollback.

Final read-only execution `ocean-v070-release-ops-n4bl9` passed with schema 0015:
old corpus/publications/user roles/completed history hashes are preserved, all
six new registry tables are empty, and Chat count is 186 (baseline 183 plus three
actual UI QA records). The post-promotion record preserved admin ownership,
eDNA-only scope, evidence fingerprint/prompt hash and zero invalid citations.
The private `verify-verification.json` receipt is retained with the backup.
Temporary `ocean-v070-release-ops` was deleted; exactly the five original manual
jobs remain. Task-owned OAuth/QA browser tabs are closed after evidence capture.

Remaining follow-up is explicit: live viewer/researcher sign-in and role checks
before real research approval use; all six real ANEMONE/SST demos and their
scientific preparation; stable OS advisory maintenance. Issue #89 remains open.
The older checkpoint above records the pre-promotion state and is superseded by
this section for current operating state.
