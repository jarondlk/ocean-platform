# OCEAN v1.0.0 release preparation

Prepared on `overhaul`, starting at `a69eb57`, after accepted C26 software
`afe9cb2`. Local release preparation is complete and verified. **Not ready to deploy.**
`v1.0.0-rc.1` is a document label; no Git tag, GitHub release, image or hosted
revision has been created.

The candidate binds the exact C26 application/configuration sources and their
passing hosted run. C27 adds operator artifacts and disposable rehearsals; it
does not convert the static frontend, fake queue or local execution harness
into production hosting or a worker service.

| Artifact | Purpose |
|---|---|
| [Readiness audit](C27_READINESS_AUDIT_2026-11-01.md) | Formal prerequisite, source and receipt reconciliation |
| [Release manifest](evidence/C27/release-manifest.json) | Candidate, migration head, v1-only target worksheet and evidence identities |
| [Requirement evidence](evidence/C27/requirement-evidence.json) | Every C26 R01–R33/G0–G9 row, plus separate C27 local acceptance |
| [Release gates](evidence/C27/release-gates.json) | All 20 original pending operational gates and the open P2 |
| [Operator runbook](evidence/C27/operator-runbook.md) | Preflight, ordered activation, abort, drain and recovery criteria |
| [Approved-data procedure](evidence/C27/data-transfer-runbook.md) | Explicit eligible copies, quarantine, provenance and withdrawal |
| [Migration rehearsal](evidence/C27/migrations-20261101/receipt.json) | Exact offline SQL and disposable native PostgreSQL observations |
| [Rollback rehearsal](evidence/C27/rollback-20261101/accepted/result.json) | Actual local flag/service behavior and retained-history observations |
| [C26 defects](C26_DEFECT_REGISTER_2026-10-30.md) | Open P2 first-history latency and historical CI qualifications |

C27's completion concerns the release-preparation package. It cannot pass a
live release gate merely by adding a local rehearsal. The proposed public origin
is `https://beta.oceaninfobio.com`; the whole-site project, resources, image
digests, identities, secret references, operations policy and live authorization
are still missing. `browser.cookie_domain=null` deliberately requires host-only
cookies and is not missing configuration.

The accepted rollback is to disable v1 entry points/dispatch while retaining
v1 data, or to restore this same candidate after repair. No earlier v1 revision
is asserted compatible with populated v1 tables. The legacy site/database is
never a rollback destination.

Original C26 reports, browser observations and C23 physical evidence retain
their original identities. New C27 observations are separate receipts. No real
data transfer, provider call, GCP operation, DNS change, deployment, release
publication or scheduler change is performed by this package.
