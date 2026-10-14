# C05 readiness and C03/C04 delivery audit

Audited 2026-10-15 JST on overhaul. **Ready to begin C05 locally.** C05's only
formal prerequisite is P00; all 36 accepted P00 source hashes and its aggregate
match. C03 and C04 are committed and pushed, and the complete hosted source CI
passes. No missing prerequisite or tooling blocker was found. This request asks
for readiness; C05 implementation remains Not started.

## Delivered foundation

- `9a2d225`: C03 retention repair, deterministic tests, PostgreSQL evidence and
  the earlier readiness audit.
- `6587069`: C04 complete-operation thread offload, cancellation/security tests
  and the component handoff. The four application/test hashes match its accepted
  local receipt; later document metadata is explicitly historical.
- `276540f`: C03 CI fixture identity repair. The hosted service reports its Docker
  bridge address even when the client URL is loopback. The fixture now accepts
  only loopback or the exact job-owned, Docker-inspected RFC1918 address in GitHub
  Actions. Loopback client URL, dedicated ocean_c03_* database, observed database,
  Read Committed and per-test schema checks remain mandatory. Eighteen offline
  allow/deny guard cases pass; all 12 actual local PostgreSQL cases pass again,
  with zero schemas remaining and the owned server stopped.

[Hosted CI for the repaired source](https://github.com/jarondlk/ocean-platform/actions/runs/38589445905)
passes backend, legacy frontend, accepted v1 prototype and PostgreSQL integration.
The PostgreSQL job passes the 39 existing cases, all 12 C03 cases on PostgreSQL
16.15, idempotent loading and backup/isolated restore. Dependency review is skipped
on this push by its existing pull-request condition. The initial hosted C03
identity failure is retained rather than represented as successful acceptance.

The 30 older unrelated README/audit/benchmark files are excluded from these
commits and retain their saved hashes. No main merge, deployment, production
database operation, provider call or live reindex occurred.

## C05 baseline and intended repair

The four existing required suites pass **59 tests**, with one existing deprecation
warning. This is a baseline, not acceptance for the known retrieval defects.
Read-only emitted-SQL probes confirm both PostgreSQL vector entry points omit
provider/model/dimension identity predicates. The actual metagenome producer
merges Kraken into _x and MetaEuk into _y; its synthetic output loses Kraken in
the document builder while retaining MetaEuk. Generated document metadata has
no explicit source/mapping version bindings. These reproduce F06 and F08 and
confirm C05 is the appropriate next component.

C05 should add independent provider/model/dimension mismatch cases, including
same-dimensional different models and missing identities, while retaining active,
source and authorization filters plus full-text fallback. Update named producer
fields and affected consumers together: document_builder, scripts/load_db,
ingestion/lineage and the metagenome API views. Preserve old layouts through a
named tested adapter. Add mapping/source versions, deterministic document hashes
and explicit deferred rebuild instructions without reactivating stale vectors.

The proposed metagenome contract suite is appropriately absent before C05 starts.
Existing PostgreSQL/pgvector integration suites and CI's disposable PostgreSQL 16
service are available; local PostgreSQL 18 and pgvector are installed. Future C05
acceptance must test actual incompatible-vector results on an explicitly verified
disposable store. SQL inspection and the C03 concurrency harness do not establish
vector correctness. Production regeneration, reindexing and paid embedding calls
remain outside component selection.

Commands, source/evidence hashes, synthetic probes, review and exact hosted source
identity are retained in [the verification receipt](evidence/c05-readiness-2026-10-15/verification.json).
The follow-up commit containing this audit is documentation/evidence only; its
application, tests and workflow sources match the successful hosted source.
