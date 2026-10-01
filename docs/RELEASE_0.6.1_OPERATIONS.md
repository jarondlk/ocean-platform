# v0.6.1 operations

**Prepared 2026-10-02 JST. Source PR, candidate build, release and rollout pending.**

The authorized sequence is recorded in [the patch plan](RELEASE_0.6.1_PLAN.md).
Japanese-specific work/acceptance is explicitly deferred; other acceptance gates
remain in force. No production schema/publication mutation is planned.

## Refreshed baseline

Cloud Run inventory on 2026-10-02 confirmed `ocean-platform-v060-sec1001` still
receives 100% traffic, with the `v060-production` tag. The v0.5.0 production,
staging and maintenance tags remain at zero traffic. Project `data-infra-infobio`,
region `asia-northeast1`, canonical site `https://oceaninfobio.com`.

Current serving image digests and resource/security settings are retained in the
private refreshed service inventory. Candidate preparation will derive from
that live definition rather than replacing it with a stale template. Serving
limits and identities will be preserved. Cloud login currently works.

The source/package candidate version is `0.6.1`; it is not yet a published Git tag.
The compatible v0.6.0 rollback revision and schema head `20261001_0014` remain.

## Release gates still pending

- Exact final source CI/CodeQL, dependency and generated-contract checks.
- Immutable exact-source images and zero-traffic candidate.
- Candidate authenticated admin/history/source checks; live viewer/researcher
  sessions and mobile acceptance remain pending.
- Repeated English scientific matrix and manual claim-to-evidence dispositions.
- GitHub tag/release only after candidate acceptance or an explicit recorded
  user deferral; traffic promotion and post-cutover checks afterward.

## Temporary local resources

A task-owned PostgreSQL 16 container `ocean-v061-pg` on loopback port 55461 holds
isolated fixture/corpus data. Its backup/restore passed with 28 tables and the
restore database was removed. Local preview ports 3006/8006/11436 serve required
mock-role fixtures with test-only credentials. Stop/remove these task resources
when acceptance completes; existing user containers are unrelated.
