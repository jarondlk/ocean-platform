# v0.4.4 release and deployment record

Status on 2026-09-11 JST: release preparation. The user authorized commit,
push, GitHub release, and a cloud rebuild. Release and deployment outcomes
will be recorded here after verification.

## Candidate

- Scope: ANEMONE taxonomy interpretation and the user-approved reference TSV.
- API/frontend version: `0.4.4`.
- Database schema remains at `20260905_0011`; no new migration.
- Local backend: 760 passed, 13 expected service-gated skips, 78.26% coverage.
- Focused taxonomy/integration subset: 87 passed; Ruff and diff checks passed.
- Existing pilot classification must remain `unknown`, `is_control=null`.

## Release gates

Pending: protected-branch CI and PostgreSQL checks, merged release commit,
GitHub release, verified backup/restore, immutable Cloud Build, candidate
revision checks, controlled eDNA republication, and production traffic switch.

The retained v0.4.3 deployment is the rollback reference. Keep historical source,
normalized, analysis, and provenance artifacts; review corpus compatibility
before reverting an application revision.
