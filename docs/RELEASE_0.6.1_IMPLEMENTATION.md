# v0.6.1 implementation and acceptance

Implementation started 2026-10-02 JST on `codex/v061-chat-patch`, based on
`e6244b7`. The user explicitly deferred Japanese-specific work/acceptance.
Existing Japanese support and automated regressions remain unchanged.

## Changes

- Exact-count routing accepts the two production rare-taxon count paraphrases.
  Neutral count vocabulary is bounded; unrecognized qualifiers still fail
  closed. Unsupported wording and conflicting methods/classifications receive
  distinct explanations while retaining the selected filters. The persisted
  abstention reason stays `aggregate_scope_required`; the UI labels it as
  clarification, rather than incorrectly asserting that filters are absent.
- Deterministic answers lead with the requested standards, classification,
  concentration, community-table or assignment metric. Multiple requested
  occurrence/assay/assignment/read metrics appear together. Alternative methods
  remain separate; physical identity, abundance, calibration and missing-value
  caveats remain explicit. Historical aggregate payloads/IDs are unchanged. Containment wording without
  an explicit taxon filter remains blocked, and rejected method combinations
  cannot partially mutate inferred filters. Empty cohorts state zero recorded
  reads rather than leaving the requested metric blank.
- Settings hydration is tied to the account that was actually loaded. Before
  hydration, a different account cannot see, submit or persist the earlier
  account's scope. Reads initialize fresh state/notices; malformed saved scope
  still requires reset, while denied storage permits an unsaved session.
  Reset updates retained defaults even during a transient analysis link.
- Late capability/model responses are ignored after the loading effect is
  disposed. Existing abort guards for filter choices have mounted-component
  regression coverage.
- The English scientific matrix uses real `evidence_scope` envelopes: 31 planned
  generations, hard cap 33 actual generation attempts including failures/retries.
  The operator runner stops on structural failures and captures supplied evidence,
  answers, metrics, timing and available provider usage. Manual claim review is
  required; this runner does not establish live role/authentication acceptance.

## Local validation

| Check | Result |
| --- | --- |
| Original count regressions before fix | Both API reproductions failed as expected; clarification distinction also failed |
| Focused routing/source tests | 96 passed; later source-envelope regression refinement: 58 routing tests passed |
| Full backend/coverage | 935 passed, 36 integration skips, 78.24% coverage; exact-source remote CI pending |
| QA matrix and actual-attempt budget | 2 passed |
| Python lint / generated scope | Passed |
| Runtime dependency audit | 64 locked packages, zero known vulnerabilities; pip consistency passed |
| Frontend | 52 tests passed, typecheck/build passed; serving dependency audit: zero known vulnerabilities |
| PostgreSQL 16 / pgvector | Fresh migration to retained head `20261001_0014`; 36 integration tests passed |
| History | Real API/record lifecycle independently read with fresh ORM sessions: answer, freshness, clarification, no-source, no-evidence; exact scope, effective Vertex settings, evidence hash and citation audit retained |
| Upsert replay | Second isolated import: zero inserts/updates across all eight loaded tables |
| Backup/restore | Isolated database: 28 tables; verified restore database removed |

The first sandboxed backend run failed because loopback HTTP fixtures could not
bind sockets. Rerunning with local socket access passed. The first local backup
attempt lacked client tools; using the disposable PostgreSQL container passed.
These are setup failures, not claimed product failures.

## Browser and remaining gates

Disposable local role fixtures use required authentication and the existing
mock-login mechanism only in `DEPLOYMENT_ENV=test`. They do not change production
roles, invitations or authentication. Viewer navigation respects its role;
source toggles/disclosures/native dropdown type-ahead work with the keyboard,
CTD station choices cascade, and all-disabled persists after reload with Ask and
quick questions blocked. Question draft is not restored. A researcher on the
same origin starts with independent defaults. Additional role/return/reset checks
remain pending.

Two in-app-browser attempts to apply a mobile viewport timed out; read-only DOM
inspection confirmed the viewport remained 1280 pixels wide. Mobile acceptance
is pending, not passed. Live viewer/researcher sign-ins were requested and are
pending. Live candidate admin/history and repeated scientific claim review are
also pending. Earlier v0.6.0 QA does not silently waive these gates.

The owned feedback section exposes its interaction ID as a DOM data attribute
for bounded independent readback; QA need not scan unrelated history.

Private raw captures/operator outputs remain under `/tmp/ocean-v061-release`.
No private accounts or credentials are committed.
