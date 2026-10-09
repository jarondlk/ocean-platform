# GCP health and security audit — 2026-10-09 JST

Project `data-infra-infobio`, region `asia-northeast1`. This is a dated audit;
[release operations](RELEASE_0.7.6_OPERATIONS.md) records the accepted rollout.

## Verified live state

The pre-release read-only operator passed at 15:06 JST after TLS enforcement.
Database/model runtime available; schema `20261005_0016`, 34 tables; 8,774 supplied
evidence documents and 1,534 SST days. Managed SQL is RUNNABLE with deletion
protection, seven successful recent managed backups and seven days of PITR.
No public authorized SQL networks are configured. Serving scale remains
min0/max1, concurrency20; no HA/capacity upgrade was applied. The final post-release
read-only health operator also passed on application 0.7.6 with the same schema,
tables, evidence counts, publication and valid catalogue identifiers. Original
accounts/roles/history, corpus and scientific artifacts passed preservation.

The private scientific-data bucket enforces public-access prevention, uniform
bucket-level access, versioning and seven-day soft delete. No public bucket IAM
binding or user-managed key for either runtime identity was found. The public
Cloud Run invoker is intentional for the authenticated frontend; API dependency
and data endpoints remain protected by application authorization.

Cloud SQL previously allowed unencrypted/encrypted connections. It now enforces
`ENCRYPTED_ONLY`; new-instance bootstrap uses the same policy. Serving and manual
jobs use managed Cloud SQL connectors, which already encrypt transport and
validate identities. A new process successfully connected after the change.
Backups, network lists, roles, IAM and certificates were preserved; no production
restore or schema migration occurred. [Google's SSL guidance](https://cloud.google.com/sql/docs/postgres/configure-ssl-instance)
describes connector compatibility and the policy's effect on new connections.

The preceding 24-hour request sample contained 1,349 2xx, 177 3xx, 86 4xx and one
5xx. Both ERROR log entries correspond to one already corrected v0.7.5 QA-revision
500 from October 8, not the accepted AUTO production revision. Current production
had no matching ERROR entry in the sampled window. In the sampled hour, SQL CPU
peaked at 100% during validation and was 13.7% at the latest point; memory peaked
at 61.2%, disk at 32.8% and latest disk utilization was 25.6%. These are observed
samples with monitoring latency, not an availability or performance guarantee.
Budget headroom was not verified; existing capacity remains unchanged.

A fresh native PostgreSQL release backup passed isolated restore through the new
TLS policy. The temporary restore database was removed. Private backup/manifest/
baseline receipts: `gs://data-infra-infobio-ocean-data/backups/v076/release-20261009/`.
Size 210,083,130 bytes; SHA256
`a6526a5de78a5ec2ca49df4964e48da2112524700f4b6ed834b80d2c3fdc8311`.

## Source and dependency security

Fresh GitHub reads found zero open Dependabot and secret-scanning alerts. The
production Node audit reported zero vulnerabilities. PR #127 exposed two new
high-severity polynomial-regex findings: overlapping optional whitespace in
3NN/protocol matching. The patch uses unambiguous delimiter matching and tests
long whitespace while preserving requested analysis/protocol constraints.

Eight existing high-severity path-flow alerts targeted the local immutable bundle
reader. The patch reuses the bounded artifact reader's resolved-path containment,
rejects symlinks and nonregular files before opening, bounds manifest/aggregate
bytes and preserves checksum/verified-byte semantics. Traversal, root/bundle/
manifest/result symlinks, directories, FIFOs and byte limits are tested. This is
filesystem hardening; the alerts are not proof that every flagged path was
exploitable under the existing identifier/file-contract checks.

All eight GitHub checks passed on source `784cd5c129b587e046bbcf68abf7d8e92d9a6db9`,
including CodeQL, backend/coverage, frontend, dependency review and PostgreSQL
integration. Alerts are not dismissed or queries suppressed. A fresh merged-main
read shows zero open CodeQL alerts; all ten findings were fixed in source.

## Remaining OS findings

Full unsuppressed release scans and exact runtime inventory are retained in the
operations record. The eight previously reported unique high CVEs still have no
fixed version in the current Debian trixie release as of this audit. Supported
stable repositories are used; testing/unstable packages are not mixed into the
runtime. Non-root execution, zero effective capabilities, stripped privilege bits
and removal of unused affected tools/daemons/modules remain verified mitigations.
They do not replace a supported package fix. Continue maintenance in #104.

| Advisory | Scope and current disposition |
| --- | --- |
| [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720) | ncurses `infocmp`; tool removed, package finding retained. |
| [CVE-2026-16742](https://security-tracker.debian.org/tracker/CVE-2026-16742) | systemd-homed; daemon absent, findings retained on shared package records. |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369) | ACL library; retained conditional privileged-library risk. |
| [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642) | util-linux mount hooks; affected tools/privilege bits and fstab entries absent. |
| [CVE-2026-78408](https://security-tracker.debian.org/tracker/CVE-2026-78408) | privileged `nsenter`; tool removed. |
| [CVE-2026-78409](https://security-tracker.debian.org/tracker/CVE-2026-78409) | mount subdirectory path; affected tools/fstab entries absent. |
| [CVE-2026-78410](https://security-tracker.debian.org/tracker/CVE-2026-78410) | mount option path; affected tools/fstab entries absent. |
| [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538) | Perl Archive::Tar; module absent. |

The separately reported [SASL DIGEST-MD5 issue](https://security-tracker.debian.org/tracker/CVE-2026-107161)
remains in package metadata; exact-image checks verify that plugin is absent.
Full scans, dated applicability review and continuing package maintenance are
required for future builds. No claim of general exploitability clearance is made.

## Documentation and identifier audit

The initial 118 tracked Markdown documents had no broken local file/heading
links. The final 121-document audit also passes; all 54 referenced repository
issue/PR IDs resolve. Apparent IDs 283/300
are genuine historical GitPython Dependabot alerts, both fixed; their labels
now explicitly distinguish them from issues. Current README, handoff, deployment,
GCP runbook, roadmap, security guidance, documentation index and release notes are
refreshed. Historical release/scan/publication IDs retain their dated meaning.

The operator validated all four registered analysis IDs and their hashes,
protocol memberships and published catalogue bindings. Two retained descriptive
analyses are marked `current_state_unavailable`; they are valid immutable
registrations, not current selectable research cohorts. Both operational Miyagi
analyses are current with three separate protocols each. The verified regional
publication remains `d34da58bbb39bb3675d0d0654d56ab13de46b078605df0fe52cb8f8ade698952`.
No artifact/identifier is rewritten or deleted to hide unavailability.

The separate uncommitted Himawari downloader is preserved outside the released
archive. Broader scientific, browser/mobile and language evaluation remain bounded
follow-ups; no acquisition is restarted by this maintenance work.
