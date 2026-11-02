# Independent password-safety amendment review — 2026-11-02 JST

**The cleartext role-password SQL blocker is resolved in the reviewed local
operator source. No additional implementation blocker was confirmed in this
amendment.** Reviewed operator SHA256
`aa17c2f2a5d51207bb19c1ed7c1b2e4d3d2af2257c9ed913913423573bd876f9`.
The read-only verifier passes for5current sources and76artifacts, including
preserved756source/receipt copies and the source-bound48-case accepted native
result. The32pure and26existing guard results were inspected, not rerun.
No native server, real credential, image, token or cloud operation was created
by this review. Earlier reviews and receipts remain historical and unchanged.

## Client preparation and actual-session gate

The only role-password SQL binding now receives the result of
`psycopg2.extensions.encrypt_password` with the actual driver connection and
explicit `algorithm='scram-sha-256'`. Plaintext remains an input only to client
preparation. The code requires supported libpq and server versions, validates
the returned SCRAM verifier shape, and replaces preparation errors with a fixed
safe diagnostic. It has no plaintext, MD5 or implicit-algorithm fallback.
This matches the intended client-side use documented by
[libpq](https://www.postgresql.org/docs/16/libpq-misc.html#LIBPQ-PQENCRYPTPASSWORDCONN)
and [psycopg2](https://www.psycopg.org/docs/extensions.html#psycopg2.extensions.encrypt_password).

Bootstrap attests logging policy before extension/role mutation. Role creation
attests again before preparation and immediately before each sensitive SQL
binding. The checks read the current connection's settings; no SET or provider
flag mutation is hidden in this path. Unsafe ordinary statement, error-statement,
duration/sampling, debug or statistics settings reject work. The inspected
pgAudit and auto_explain paths must be absent or disabled. Successful output
contains fixed policy/collector metadata rather than passwords, verifiers,
their hashes or raw queries.

The pg_stat_statements gate considers preloads and registered GUCs as well as
extension presence in this database. A present collector must have utility
tracking off or overall tracking disabled. This closes the reviewed
cross-database collector path without assuming that absence of its local view
means collection is inactive. PostgreSQL documents that the active module
collects across databases while its views are enabled per database.
[Collector scope](https://www.postgresql.org/docs/16/pgstatstatements.html).
Ordinary non-utility metrics can remain active.

## Retained acceptance and preservation

The current native evidence demonstrates refusal under ordinary ERROR
statement logging before preparation/mutation, then refusal of an actually
preloaded utility collector even without an application-database extension.
After only the owned temporary policy is qualified, real libpq supplies SCRAM
bindings and both restricted accounts authenticate. The38previous
privilege/PUBLIC/column/migration/finalizer checks remain covered in the48-case
result. The controlled duplicate credential statement uses synthetic material.

The harness scans the complete owned server-log stream after stop, including
continuation lines, for all retained synthetic plaintext/verifier markers and
the SCRAM prefix before exporting a safe log. Its separate database reads
actual collector query texts in memory and checks them without exporting
those texts. Accepted evidence records safe absence booleans and ordinary
query count, with complete server/port/PID/owned-directory cleanup. A sensitive
log hit would fail and withhold that log rather than creating a passing receipt.
This local evidence is more specific than a claim of universal provider
redaction; the README correctly keeps that limit explicit.

The existing exact project/database/source and fresh-state guards, restricted
role attributes/membership, effective privilege inspection, stage separation
and fixed loopback proxy finalizer remain in the current source. Previous
failed/intermediate native runs and all predecessor receipts are preserved;
none is relabelled as acceptance for these new bytes.

## Gates before live use

This source can be checkpointed and its immutable operator image rebuilt.
Live bootstrap still requires fresh actual Cloud SQL16 session policy and
reviewed provider/Query Insights/collector configuration. Unknown provider
collection is not covered by this finite PostgreSQL gate. The code promises
neither crash/memory confidentiality nor universal log redaction; a SCRAM
verifier remains sensitive. No live exposure is established by this review.

Bind the new image to the new source commit, then explicitly supersede the
job renderer's old756operator revision and image references. The old setup
receipt must remain historical. Do not run a newly built operator through
the old revision-confirmation configuration. Actual private SQL stages,
limited-managed-principal capabilities, narrow IAM/secrets, proxy/container
exit evidence and all OAuth/account/scientific/C23/release gates remain
separate. The pending SDK sign-in has not been bypassed and no real values
have been generated here.
