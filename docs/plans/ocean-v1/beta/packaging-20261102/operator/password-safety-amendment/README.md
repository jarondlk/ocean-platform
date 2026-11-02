# Password statement and utility-collector amendment

This supersedes checkpoint `756c7a7`'s cleartext role-password SQL path following
the copied [password review](PASSWORD_REVIEW.md). No live credentials or cloud
bootstrap were performed by this work. Three exact756operator source files and
three original receipt files remain byte-preserved. Original receipts, native
outputs, application/migration files and the separate50-check credential setup
receipt are unchanged; this amendment has its own source/evidence identity.

Before any password-bearing SQL, bootstrap and role creation read the actual
session logging policy. The operator does not issue SET or change provider
flags. It requires statement logging off, error-statement threshold PANIC,
duration/sampled-duration logging disabled, transaction sampling zero, debug
parse/plan/rewrite and statement/parser/planner/executor statistics off, and
SCRAM server policy. Optional pgAudit/auto_explain statement paths must be absent
or disabled. These ordinary logging checks do not claim universal redaction,
PANIC/crash/memory confidentiality or provider-metric acceptance.

The pg_stat_statements check examines shared preloads and its GUCs as well as
current-database extension presence. An extension's absence in this database
does not imply the shared collector is inactive. If present/preloaded, utility
capture must be disabled by `track_utility=off` or `track=none`. Query metrics
need not all be disabled. The parent owns the new-beta-only
[actual logging flag plan](../../../sql-20261102/logging-policy/PLAN.md), fresh
Query Insights/provider configuration and unexpected-collector review. No cloud
flag or audit-policy change is performed by this code or evidence capture.

Once policy is attested, `psycopg2.extensions.encrypt_password` uses the actual
driver connection and explicit `algorithm='scram-sha-256'` to prepare each role
password on the client. Only the resulting SCRAM verifier is bound in SQL.
Supported libpq/server versions and the verifier format are required; there is
no MD5, plaintext, implicit-algorithm or error fallback. The session is rechecked
immediately before each sensitive binding. The plaintext and verifier remain
private memory, are never printed, placed in argv/receipts or hashed as evidence.
The verifier is still sensitive; encryption is not an excuse to capture it.
[Psycopg2 preparation API](https://www.psycopg.org/docs/extensions.html#psycopg2.extensions.encrypt_password),
[PostgreSQL16 logging controls](https://www.postgresql.org/docs/16/runtime-config-logging.html).

The successful bootstrap result includes only fixed logging-policy metadata and
collector qualification. Unmet settings reject before extension/role/password
mutation. Existing fixed safe errors, fresh database/role checks, exact source/
project/identity confirmations, restricted grants and proxy finalizer remain.

## Acceptance evidence

**32 new pure checks, 26 existing guard regressions and 48 actual owned native
checks pass.** The final accepted native run is
`native-final-qualified/receipt.json`. It establishes:

- Default ERROR statement logging refuses work before password preparation;
  no role or extension is created.
- Real pg_stat_statements is preloaded with no extension in the application
  database. Utility-on refuses before preparation even after ordinary logging
  is corrected; utility-off accepts.
- Both actual role SQL bindings contain client-prepared SCRAM, and both
  independently restricted roles authenticate through real SCRAM connections.
- All previous38 bootstrap/migration/privilege/PUBLIC/column/proxy checks hold.
- A controlled duplicate role-password statement fails using a synthetic
  verifier. The whole server-log stream, including continuation lines, contains
  neither synthetic plaintext nor any tested verifier/prefix. Sensitive logs
  would be withheld from evidence rather than exported.
- The separate postgres database's collector view contains68ordinary app query
  entries with no canary/verifier material. Query texts are scanned in memory
  and never exported; normal metrics remain active with utility capture off.

The owned native configuration uses PostgreSQL18.3/pgvector0.8.7 and its bundled
pg_stat_statements. Only its temporary configuration is modified. It does not
configure or attest Cloud SQL16. Server stop/status3, closed port, absent PID,
proxy fixture exit and removal of all owned temporary files are verified.
No scientific data or real account is used. Native unexpected exceptions emit
only a fixed diagnostic, not a driver traceback carrying sensitive parameters.

`native-accepted` preserves the first harness's direct-driver exception-type
mismatch after the actual privilege checks; its server-log scan and cleanup
passed. The corrected harness then passed44checks under `native-final`.
`native-query-qualified` preserves the intermediate48-check collector result
before the explicit supported-server prerequisite was added. Their receipts are
historical and unchanged, with byte-verified source snapshots. The current48-case
receipt binds the final source including that prerequisite; no earlier receipt
is retargeted or labelled as current acceptance.

```sh
.venv/bin/python docs/plans/ocean-v1/beta/packaging-20261102/operator/password-safety-amendment/verify.py
```

The verifier is read-only and checks current pins, immutable predecessor copies
and native/log-cleanup evidence. Do not repeat the successful native run for
unchanged source. Independent review, a new source commit and rebuilt immutable
operator image are required before application. Root must separately supersede
the job renderer's old756operator revision after the new commit/image is bound;
the old setup receipt remains historical. Actual Cloud SQL session/provider
policy, private job stages and all OAuth/account/scientific/C23/release gates
remain explicit. No live password exposure or managed-service acceptance is
inferred from these local results.
