# C01/C02 repository delivery audit

Date: 2026-10-14 JST
Base: overhaul at c7ea5f4c4243d1c1a0657a0a01c075f5f738219d
Delivery branch: codex/c01-c02-audit-20261014
Disposition: local checks pass; PR CI must pass before merge into overhaul.

The user requested repository verification, then a new branch, commit/push and
merge into overhaul. This delivery contains C01/C02, their evidence/handoffs,
the audit corrections below and CI coverage for overhaul and frontend-v1.
Older root README, audit and benchmark work is preserved outside the commit.
No deployment, scientific publication, provider/model call, production database
access or real-data regeneration is part of this delivery.

## Review and corrections

Reviewed the C01 shared publication-scope contract and independent planning/
execution consumers, C02 reliability/full-abundance/spatial methods, frozen input
and output receipts, transitive dependencies, history/invalidation and API/prompt
consumers. This is a focused source audit plus complete repository regression
validation, not a certification of every line or production scientific behavior.

Two additional defects were found and fixed before delivery:

- Unavailable derived computations can legitimately produce empty frames without
  sort columns. The analysis API now orders only existing columns and returns
  inspectable HTTP 200 results with ineligible receipts and null scientific
  summaries. Two regressions cover empty outputs and actual legacy-correlation
  rejection by the predictor.
- Missing sequencing_method metadata was stringified into an instrument alias
  named None. Only nonempty retained string attributes now supply protocol aliases;
  missing values cannot satisfy a requested instrument. Ten regressions cover
  missing/empty values, model-ready exact/synthesis proposals and retained valid
  names, including rejection of a null pinned protocol when another real textual
  alias happens to be None.

The API retrieval fixture now supplies an explicitly reviewed synthetic receipt
for its reliability context; it cannot authorize raw legacy context. The bundled
artifact Explore test distinguishes unavailable legacy rows from actual paired
checks. No production eligibility decision is manufactured.

The previous CI workflow omitted overhaul and the v1 prototype. It now runs on
overhaul pushes and PRs and adds v1 tests, typecheck, static build and production
dependency advisory checks. Existing backend, legacy frontend and disposable
PostgreSQL jobs remain. No deployment workflow was introduced.

## Final local verification

| Check | Result |
|---|---|
| Clean candidate full backend suite | 1,642 passed; 39 PostgreSQL-gated skips; 95.06 seconds |
| Clean candidate coverage | 82.17%; required minimum 70% |
| Final scope/planner/derived audit regressions | 253 passed |
| Legacy frontend | 81 tests; typecheck and production build pass |
| Accepted v1 prototype | 27 tests; typecheck and static build pass |
| Active Python Ruff | Pass |
| Generated chat-scope contract | Current |
| pip check | No broken requirements |
| Both frontend production npm advisory queries | Zero reported vulnerabilities on this audit date |
| Workflow structure, planning links, diff whitespace | Pass |
| Selected source/evidence secret-pattern scan | No matches, including the synthetic ZIP |
| Accepted P00 receipt | All 36 source files unchanged |
| Seven affected local real artifacts | Exact C02 inventory hashes unchanged |
| Earlier unrelated local work | 30 saved file hashes unchanged |

The authoritative backend run used a clean Git-baseline export plus exactly the
selected delivery files, excluding the older uncommitted benchmark code/tests.
Its 24 Python/workflow hashes match the final workspace. Tests use synthetic
fixtures and read-only bundled artifact checks. The PostgreSQL service remains
disabled locally; the CI integration job must validate those 39 cases before
merge. Initial sandbox-only failures were caused by denied loopback fixture-server
binding; the complete suite was rerun with local fixture access. Existing
FastAPI/httpx, NumPy/netCDF4 and xarray/pandas warnings remain visible in logs.

The original C01/C02 acceptance receipts remain historical. The audit deliberately
changes api/main.py, publication_scope.py and the corresponding regression files;
the final source hashes and receipt drift are recorded in
[delivery verification](evidence/delivery-2026-10-14/verification.json).
Frontend-v1 application source is unchanged from the accepted P00 revision.

## Remaining boundaries

This is ready for the overhaul integration branch after CI, not for production
release. Previously recorded retention races, authentication responsiveness,
embedding/document-field consistency, runtime termination and CSV formula safety
remain planned C03–C07 work. No new component is started by this audit.
Affected legacy derived artifacts still require separately authorized regeneration
and established eligibility review; the gap interpolation method remains
unvalidated. C13 catalogue integration, operational authorization, full v1
acceptance and release/isolation checks remain future gates.

Keep old acceptance receipts, generation tombstones and consumer eligibility
guards during rollback. Do not reauthorize historical outputs by copying them
back into current paths. Merge only this selected branch into overhaul; preserve
main, production and the unrelated local files. The PR and hosted checks provide
the subsequent merge record.
