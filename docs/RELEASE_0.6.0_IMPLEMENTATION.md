# v0.6.0 — Implementation and release gates

Updated 2026-10-01 JST. Implemented locally on `gcp-dev`, from baseline
`fecfa7d`. API and frontend package metadata now identify the candidate as
`0.6.0`. Production remains the recorded v0.5.0 deployment; this document does
not confirm a source release, remote CI run, merge or deployment.

The user authorized implementation of the [adopted plan](RELEASE_0.6.0_PLAN.md),
including the bounded issue #70 fixes and browser persistence per account.
The [readiness audit](V0.6.0_READINESS_AUDIT_2026-10-01.md) records the baseline.

## Changes

- Chat has independent CTD, metagenome, satellite SST and ANEMONE eDNA
  checkboxes, expandable source filters, source resets, Select all, Clear
  selection and Reset all. Advanced contains ranking, context and generation.
  The question shows the draft selection; the response ledger records the
  server-applied selection, including false and zero values.
- Categorical source filters now use selections from active chat evidence:
  CTD/metagenome bays, stations and samples; eDNA samples, providers, projects,
  runs, assignment methods, taxa, sample kinds and control status. Choices
  respect the other filters within that source and pinned eDNA member/method
  restrictions. Long lists support search beyond the first 100 choices.
  Dates and coordinate ranges retain their range inputs. A saved choice stays
  explicit when it no longer matches; it is never cleared automatically.
  Missing local eDNA data, empty matches, loading and retry states are visible.
- Source-owned filters constrain PostgreSQL vector and full-text candidates
  before ranking. Local search uses the same membership rules before ranks
  and top-K. Linked targets must satisfy their own source filters before the
  expansion limit. Global top-K, weights and reciprocal-rank fusion remain.
- Final prompt packing omits unchecked, mismatched or unverifiable evidence.
  Derived context must cover enabled families and fit wholly within the
  requested cohort. Unknown coverage is accepted only for unrestricted,
  all-source requests. Omission diagnostics and the supplied manifest are
  retained with chat history.
- Saved eDNA analyses resolve their recipe and member/method restrictions only
  into eDNA. Other selected sources remain independently eligible. Analysis
  context containing controls cannot claim environmental-only scope;
  cross-source context includes every contributing family, beyond featured
  rows. Incompatible or historical analysis links fail closed.
- Empty selection is valid at the API: deterministic abstention, no retrieval,
  aggregate, embedding or chat-provider call. The interface disables Ask and
  quick questions and explains how to select evidence.
- Exact eDNA aggregates honor eDNA's filters and require eDNA to be enabled.
  General mixed-source summaries do not silently become eDNA catalogue totals.
- Requested settings and effective scope/generation settings are separate in
  response options and history. `/chat/capabilities` uses `chat:use`, exposes
  the schema and provider controls, and works within the existing default-deny
  authorization boundary. Vertex no longer advertises or records repeat
  penalty/context window as effective controls.
- Validated browser storage uses the authenticated application user UUID and
  settings version. Ask waits for hydration and capabilities. Malformed saved
  scientific scope requires reset; unavailable storage allows current-session
  settings with a notice. Questions, responses and analysis IDs are not saved.
  Analysis deep-link selection overrides do not replace stored source defaults
  while the pin is active. The identity provider remounts on account changes.
- New labels and validation messages have English/Japanese support. Source
  settings are disabled during initial restore.

## API contract and compatibility

`POST /chat/filter-options` is a read-only `chat:use` endpoint. It accepts the
validated evidence scope, an optional source/selection field, and a bounded
search string. Each field returns at most 100 distinct choices plus a truncation
flag. It uses the active PostgreSQL retrieval corpus or the published local
JSONL fallback without invoking embeddings or the chat model. PostgreSQL taxa
come from all active canonical detection ranks, including terms outside the
featured retrieval text, and honor the remote publication generation guard.
Each field excludes its own current predicate so the user can replace a choice;
other predicates and pinned member/method restrictions remain effective.

`POST /chat` and `POST /retrieve` accept the versioned `evidence_scope` envelope.
All four sources, each with a strict enabled boolean and filter object, are
required. Unknown keys, versions, source families, unsupported filters,
invalid bounds and conflicting classifications are rejected. Disabled sources
retain filter values but provide no evidence.

Example scope, usable alongside `query`, `k` and generation/context options:

```json
{
  "version": 1,
  "sources": {
    "ctd": {"enabled": true, "filters": {"bay": "O", "station": "s1", "time_to": "2024-12-31"}},
    "metagenome": {"enabled": false, "filters": {}},
    "remote_sensing": {"enabled": true, "filters": {"time_from": "2024-06-01", "lat_min": 38, "lat_max": 39}},
    "edna_metabarcoding": {"enabled": false, "filters": {}}
  }
}
```

Legacy flat scientific fields remain supported when no envelope is supplied,
including known source aliases, `top_k` and eDNA-only inference. Scientific
fields such as `source_type`, `bay`, `taxon` and `analysis_id` cannot be mixed
with the new envelope. Ranking and generation fields remain top-level.
Satellite panels omit bay/station/sample controls because current SST documents
have no matching metadata. Coordinate filters select recorded point metadata;
they do not spatially recompute regional statistics.

The backend owns the scope schema. `scripts/export_chat_scope.py` generates
`frontend/lib/generated/chat-scope.ts`; CI checks it with `--check`. Regenerate
and review the generated file whenever the Python scope models change.

## Bounded answer-support fixes

Known summary paraphrases and a bounded Japanese catalogue count route to
exact SQL; interpretation questions about reads and fish remain ordinary RAG.
Exact answers lead with unresolved physical-sample identity, unknown-control
status or per-method reads when requested.

An explicit taxon/method filter supplements abbreviated assay prose with
immutable canonical aggregate evidence, including filters and scientific
limitations. The existing assay citation text is not rewritten. An unavailable
canonical verification produces abstention rather than an inferred absence.
Arrival/freshness questions about ANEMONE return an explicit limitation;
collection dates do not establish data arrival. The prompt also states these
scope and absence limits.

These fixes do not constitute a general natural-language scope parser or
validation of every scientific claim. The frozen-production rare-taxon case
(one occurrence, one QCauto assignment, 122 reads), repeated interpretation
questions and manual claim support still need authenticated candidate QA.
Issue #70 remains open until those live acceptance checks pass.

## Local verification

| Check | Result |
| --- | --- |
| Active Python Ruff lint and `git diff --check` | Passed |
| Generated contract check | Passed |
| Complete backend suite | 905 passed, 35 PostgreSQL checks skipped in the final release run; 79.24% coverage, above the 70% gate |
| Disposable PostgreSQL 16 / pgvector integration | Initial candidate: 34 passed in CI order, migrated from empty database to `20261001_0014`. Selection refinement: 1 additional test passed in a fresh isolated database/schema, verifying cascading choices, local/SQL agreement, canonical taxonomy, false controls, inactive rows, bound search and pinned membership. |
| Vector/FTS/local source subsets and independent filters | All 16 combinations; source values bound as SQL parameters; false controls, zero coordinates and day-inclusive dates tested |
| Linked evidence and migrated history reasons | Passed PostgreSQL checks |
| Canonical rare-taxon filtering and prompt supplement | Synthetic SQL/prompt tests passed, including evidence absent from featured assay prose |
| Backup and isolated restore | Passed; 28 tables, matching row counts, temporary restore database removed |
| Frontend tests | 48 passed |
| TypeScript and production Next.js build | Passed |
| Frontend production dependency audit | 0 vulnerabilities |
| Local browser | Empty selection, independent CTD/SST controls, invalid range blocking, valid restore after reload, source summaries, English/Japanese labels and absent Vertex-only unsupported controls checked. Selection refinement: live CTD station/sample cascade and search beyond the initial 100 samples verified. |
| Narrow viewport | No horizontal overflow at the tested 390 × 844 viewport override |

Backend warnings were existing Starlette/httpx and NumPy/netCDF/xarray
compatibility/deprecation notices; no test failed because of them. The
PostgreSQL fixtures require a fresh database and CI's file order: some tests
commit publication data. Alphabetical execution before pgvector initialization
and reuse of a previously populated test database are not the supported clean
integration setup. The final successful run used a fresh isolated database.
The local browser checks used development authentication disabled and made no
live model calls; they do not establish authenticated production acceptance.
For a compiled localhost preview, set `AUTH_TRUST_HOST=true` for that test host
along with the documented test environment. No production data was used or
modified by these checks.

## Migration and rollout

Apply `python -m alembic upgrade head` before routing traffic to the candidate.
New application revision `20261001_0014` extends only the chat-history
abstention-reason constraint with `no_sources_selected`, `source_disabled` and
`freshness_unavailable`. No new settings table, corpus migration, document
identity change or embedding rebuild is required.

Take a verified production backup before migration. The added constraint is
compatible with old application writes. A downgrade refuses to remove support
while history contains the new reasons; retain that history and its backup.
An application rollback can leave the expanded constraint in place.

Before publishing or deploying:

The user authorized GitHub release publication and manual GCP deployment on
2026-10-01. Execution and evidence are tracked in the
[v0.6.0 operations record](RELEASE_0.6.0_OPERATIONS.md); the gates below still
apply. Alembic now escapes ConfigParser percent interpolation, so standard
migration invocation preserves encoded Cloud SQL socket/password URLs.

1. Run remote CI/security checks against the committed candidate.
2. Renew GCP authentication and inspect current revisions, secrets, schema,
   publication generations, resources, recent errors and backup freshness.
3. Review the candidate through authenticated viewer/researcher/admin accounts,
   including account switching, inaccessible account state and storage denial.
4. Repeat the issue #70 and scientific claim-support matrix against the frozen
   catalogue; measure scoped retrieval/aggregate latency on production-sized
   data and verify history, citations, aggregate downloads and provenance.
5. Follow the plan's deployment/rollback gates, including the fresh backup and
   migration-before-traffic order.

These are release gates, not evidence that the local implementation or test
suite failed. Production/private-state verification is still limited by the
expired saved GCP session recorded in the readiness audit.
