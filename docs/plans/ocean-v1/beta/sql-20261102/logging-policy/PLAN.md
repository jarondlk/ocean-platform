# Beta SQL credential statement privacy — 2026-11-02 JST

**Prepared only. No GCP calls, tokens, flag changes or native test runs were
performed by this task.** This plan applies only to project
`ocean-v1-beta-20261101` / number `534831104543`, instance `ocean-v1-beta-sql`
(`POSTGRES_16`) and its independent `ocean_v1_beta` bootstrap. Client-side SCRAM
preparation and same-connection settings attestation are separate owning changes
and must be source/image verified before bootstrap.

The permitted instance overlay is exactly:

```json
{"log_statement": "none", "log_min_error_statement": "panic"}
```

The historical [instance readback](../instance-final-readback.json) has no
`databaseFlags` member and settingsVersion`1`. That is not proof of current
effective PostgreSQL settings and must not be reused as an update precondition.
`plan.json` pins those historical bytes and leaves actual request fields pending.

## Supported flags and effective settings

The current [Cloud SQL flags reference](https://docs.cloud.google.com/sql/docs/postgres/flags)
permits both proposed values and marks both as not requiring restart. It lists
defaults `none` / `error`, with `log_duration=off` and
`log_min_duration_statement=-1`. It warns that flag updates replace the configured
flag list. Its table does not currently expose `log_min_duration_sample` or
`log_transaction_sample_rate`; do not invent Cloud SQL flags for those settings.

After reauthentication, first verify actual `POSTGRES_16` flag metadata and the
fresh instance. After any operation, require the **actual operator connection**
to attest these values before any password-bearing SQL:

| PostgreSQL setting | Required value |
|---|---|
| `log_statement` | `none` |
| `log_min_error_statement` | `panic` |
| `log_duration` | `off` |
| `log_min_duration_statement` | `-1` |
| `log_min_duration_sample` | `-1` |
| `log_transaction_sample_rate` | `0` |

Read `pg_settings` values, units, source/context and `pending_restart`, and check
relevant role/database overrides. Missing, unrecognized, conflicting or pending
settings close the gate; instance configuration metadata alone is insufficient.
Duration and sampling settings are documented in
[PostgreSQL16 logging](https://www.postgresql.org/docs/16/runtime-config-logging.html).

Also qualify active preload modules, debug statement/plan output, pgAudit and
auto_explain. An absent extension in the current database does not by itself
prove module-level collection is inactive. For example, active
`pg_stat_statements` can collect representative query text across databases and
has utility-command tracking enabled by default. Inspect its actual state if
present; do not assume universal literal masking. Any additional active
credential-statement collector needs a separately reviewed owning change, not
extra flags silently added to this patch.
[PostgreSQL statistics collection](https://www.postgresql.org/docs/16/pgstatstatements.html).

## Application sequence after root review

1. Require working CLI access, the reviewed SCRAM-capable operator/image and an
   exclusive beta configuration writer. Verify project number, instance identity,
   engine, state, empty application status and absence of competing operations.
   Save a fresh non-secret instance baseline including its complete flag list,
   settingsVersion and Query Insights configuration.
2. Read actual supported flag metadata. Build a unique-name map from every
   existing flag; reject duplicates. Overlay only the two permitted values,
   preserving every unrelated flag exactly. Review the resulting two-or-fewer
   flag diff. If the desired configuration is already present and no drift
   exists, record a no-op rather than an unnecessary update.
3. Immediately before application, read the instance again and require the same
   version and baseline with no other writer. Submit the settings-only
   [instances.patch](https://docs.cloud.google.com/sql/docs/postgres/admin-api/rest/v1/instances/patch)
   body with the fresh version and the **complete merged** `databaseFlags`
   array. Do not use a two-item `--database-flags` command that drops earlier
   flags, or a full settings replacement. Reject a concurrency/precondition
   error; do not refresh and retry without reviewing the changed baseline.
   The API describes [settingsVersion](https://docs.cloud.google.com/sql/docs/postgres/admin-api/rest/v1beta4/instances#Settings)
   as its concurrency version; an exclusive writer and immediate comparison
   remain required rather than assuming a stale request is safe.
4. Poll only the returned instance-bound operation. Require DONE without errors,
   the exact merged flag readback and preservation of all unrelated settings.
   The two rows say no restart is required, but observe the actual operation,
   RUNNABLE state and connection readiness. General flag changes can restart an
   instance; documentation is not evidence of this operation's behavior.
5. Establish a fresh operator connection and attest effective values and other
   collectors on that same connection before `CREATE ROLE ... PASSWORD ...`.
   Keep attestation output to safe settings, identities and fixed statuses.
   Do not dump password catalogues, raw queries, DSNs or arbitrary exceptions.
   Only the reviewed client-generated SCRAM verifier may reach credential SQL.

The patch does not change `log_min_messages`, `log_error_verbosity`, ordinary
severity/error diagnostics, Cloud Audit Logs, IAM/access metadata, sinks or
retention. It also preserves backups, PITR, private networking, TLS, connector
enforcement, storage and all legacy settings. It suppresses ordinary statement
bodies, not operational evidence generally.

`panic` is PostgreSQL's documented effective threshold for suppressing ordinary
failed statement text. A PANIC-level event can still include statement text;
this is not an absolute guarantee against every server crash or message path.
A SCRAM verifier remains sensitive, and the client correction plus bounded
verification remain necessary. No live policy acceptance is claimed here.

## Required owned native proof

Use a new disposable PostgreSQL/log directory with restricted local permissions,
never a live credential. Keep a known synthetic password and its exact SCRAM
verifier only in the harness's memory. Exercise successful creation and login
with the restricted roles plus a controlled failing credential utility statement.
Require ordinary error diagnostics to remain available.

Scan the **complete raw server-log byte stream for the whole owned run**,
including all lines and multiline continuations, for both the exact synthetic
plaintext and the exact verifier. Checking only matching `STATEMENT`/`CREATE`
lines or a short excerpt is insufficient. Apply the same check to any applicable
audit/collector output and qualify query-text collection separately. Do not copy
the canaries, their hashes or secret-bearing raw logs into receipts or source.
On a hit, stop with a fixed failure status and keep diagnosis confined to the
owned temporary path. The durable proof records safe booleans, byte counts,
time bounds, source identity and verified stop/cleanup only.

That proof and actual later Cloud SQL attestation are distinct gates. This plan
does not run either, amend the accepted native receipts or permit a broader flag
change. Root may apply only the concrete beta-only diff after reviewing fresh
inputs under the user's existing deployment authorization.
