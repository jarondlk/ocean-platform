# One-flag utility collector overlay — 2026-11-02 JST

**Prepared only; no token, cloud call, flag change or job execution performed.**
Scope is project `ocean-v1-beta-20261101` / `534831104543`, instance
`ocean-v1-beta-sql`, PostgreSQL16. The separate two-flag patch and its original
source/session receipts remain immutable. This plan proposes one additional
instance flag only:

```json
{"pg_stat_statements.track_utility": "off"}
```

The actual `inspection-jobs-dcde1ef/live/readback-operator-result.json` reports
`pg_stat_statements.track=top`, `track_utility=on` and its shared preload. The
earlier two-flag readback has settingsVersion`3`, existing
`log_statement=none`/`log_min_error_statement=panic`; its verification records
Query Insightsfalse. These are historical inputs, **not a fresh patch
precondition**. The utility collector remains a separate password-SQL gate
despite successful application of the two ordinary logging flags.

## Supported representation and limited effect

The official [Cloud SQL flags table](https://docs.cloud.google.com/sql/docs/postgres/flags)
lists `pg_stat_statements.track_utility` as boolean, accepts the string values
`on`/`off`, defaults to on, and marks it as not requiring restart. Use the
database-flag API's string value `"off"`, not a JSON boolean or an invented
flag name. Root must still retain fresh POSTGRES_16 supported-flag metadata;
the saved two-flag metadata does not contain this third row.

PostgreSQL documents that this setting controls utility commands, while normal
SELECT/INSERT/UPDATE/DELETE/MERGE statistics are outside that switch. Keep
`pg_stat_statements.track=top` and the preloaded module. No collector reset,
history deletion or broad query-metric shutdown is proposed.
[PostgreSQL16 collector controls](https://www.postgresql.org/docs/16/pgstatstatements.html).

Do not remove Google/provider preloads or change pgAudit, error verbosity,
ordinary severity diagnostics, Query Insights, sinks, retention, network, IAM,
storage or any legacy project. No new role setting, parameter privilege or
superuser fallback is part of this overlay.

## Root-owned application sequence

1. **Wait for the active qualify execution to finish and verify its physical
   operator/proxy exits.** Do not patch concurrently with a running task. Then
   verify no active beta readback/qualify/bootstrap/migrate/finalize or other
   database job, no SQL operation pending/running, and one configuration writer.
   Unknown execution/operation state closes this gate; do not cancel a job merely
   to make the patch fit. Retain the completed qualify observation separately.
2. Verify actual project ID/number, RUNNABLE exact private SQL instance and
   POSTGRES_16. Retain fresh flag support using the documented
   [flags.list API](https://docs.cloud.google.com/sql/docs/postgres/admin-api/rest/v1beta4/flags/list)
   with `databaseVersion=POSTGRES_16`. Require the exact name, BOOLEAN type,
   supported version and no-restart metadata. A missing/unsupported row is a
   gate; do not substitute `track=none` or alter preloads. A metadata read does
   not prove the instance setting is effective.
3. Read the full fresh instance using the **same API representation** that will
   be used for patch/readback. The proposed route is
   `https://sqladmin.googleapis.com/sql/v1/projects/ocean-v1-beta-20261101/instances/ocean-v1-beta-sql`.
   Capture complete `databaseFlags`, settingsVersion, unrelated settings and
   Query Insights representation. Preserve the original no-op/default-false
   qualification; do not confuse v1/gcloud-beta4 representation differences
   with a new provider change. Actual unexpected enabled Insights or other
   baseline drift requires review, not an automatic extra change.
4. Reject duplicate flag names. Require the two accepted ordinary flags still
   equal `none`/`panic`; do not silently repair their drift. Make a complete map
   of every configured flag, overlay **only** utility=`off`, preserve every other
   name/value exactly, then emit the whole merged sorted list. If utility is
   already off and all baselines match, record a no-op and obtain fresh session
   evidence instead of issuing an update.
5. Immediately re-read the instance, jobs and SQL operations. Require the same
   baseline/version and no active writer. The only prospective request is a
   settings-only [instances.patch](https://docs.cloud.google.com/sql/docs/postgres/admin-api/rest/v1/instances/patch)
   containing the **fresh** settingsVersion and **complete merged** flag list.
   Never submit version3 from this plan, a three-item replacement that drops
   unrelated flags, or full instance settings. Do not refresh and retry a stale
   version/precondition failure without a new reviewed baseline.
6. Retain and poll only the returned target-bound operation. Require DONE
   without error, RUNNABLE state, expected one-flag diff and preservation of all
   unrelated settings, the two accepted flags and Query Insightsfalse. The
   docs' no-restart classification is not evidence that this actual operation
   has completed or that an old connection has adopted the setting.
7. Run a newly reviewed **readback** execution with no overrides after the
   operation completes. Require actual fresh-session utility=`off`, track=`top`,
   expected preloads, no pending restart, relevant role/database overrides and
   unchanged ordinary logging/privacy settings. Preserve safe metadata plus
   physical operator/proxy exit evidence. Do not reuse the prior utility-on
   session as a pass or infer utility-off from configuration metadata alone.

With only the historically observed two flags, the merged map would contain
`log_min_error_statement=panic`, `log_statement=none` and
`pg_stat_statements.track_utility=off`. This is explanatory arithmetic, not an
executable packet; actual version and additional flags remain unresolved until
the fresh baseline is reviewed. `plan.json` intentionally leaves request values
null and marks required live inputs explicitly.

The overlay can close only the observed utility-collection configuration gap
after actual session proof. It does not authorize password SQL, a real
bootstrap, managed-role/extension capability, new user enrollment or C23
execution. The strict client-SCRAM and finite collector/logging attestation,
limited-role guards, safe stage sequencing and all original release gates
remain in force. There is no claim of universal provider redaction.
