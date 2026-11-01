# C27 migration and preservation rehearsal — 2026-11-01 JST

The accepted local rehearsal is [run02/receipt.json](run02/receipt.json). All 20 checks pass on a newly initialized, owned PostgreSQL 18.3 cluster listening only on `127.0.0.1`. Its three synthetic databases, temporary fixture bytes and entire temporary cluster directory were removed after `pg_ctl stop`, an observed `pg_ctl status` exit 3, closed TCP port and absent postmaster PID. No existing database, real backup, GCP resource or deployed service was accessed.

The actual graph has 21 revisions and one head, `20261027_0021`. The reviewed pre-v1 baseline is `20261005_0016`; investigation history starts at `20261018_0017`. These identifiers describe the local candidate graph. They do not describe the current schema of a deployed service.

The rehearsal verifies:

- A fresh online upgrade from base to head.
- Online upgrade from 0016 with a synthetic held legacy chat row, then 0017 with a held investigation, conversation and immutable context revision, to head. Their complete row hashes remain equal across the upgrade.
- A duplicate `research_conversation` table deliberately interrupts 0017 after preceding DDL has begun. PostgreSQL rolls back the failed Alembic transaction, preserving the original 0016 version, synthetic rows and schema. Removing only the injected blocker permits a successful retry.
- Generated offline SQL for `20260925_0013:head` is actually applied to a separate disposable database starting at 0013. The result equals fresh and incremental online upgrades: 65 tables, 713 columns, 1,033 catalogued constraints, 101 user triggers and 36 functions; schema fingerprint `77fcfe54deba1329708cc8ec24fdee4365bfb12e843a46addb4788c1bdc635cc`.
- Generated `20261005_0016:head` SQL compiles without connecting to its synthetic port-1 target. Its 125,930-byte tail is byte-identical to the corresponding tail in the SQL actually applied from 0013. This is subset execution evidence, not a separate 0016 SQL-application claim.
- Actual current application services create synthetic context, run, receipt, prepared answer, experiment revision and exact approval rows. The explicit synthetic output adapter never executes Python and is not physical C23 containment evidence. Repeating `upgrade head` preserves every table's row count/hash and the complete schema fingerprint.
- A populated downgrade toward 0016 is refused by C22's conservative-retention guard. The single PostgreSQL transaction restores head 0021, including C23 tables/functions already touched before the refusal, and all context, run, answer, receipt and experiment history. This negative rehearsal demonstrates a guard; it is not an operator rollback procedure. Operational rollback disables independent v1 entry/dispatch and preserves populated schema.

## Historical offline limitation

`alembic upgrade base:head --sql` is unsupported: historical migration `20260726_0002` calls live SQLAlchemy table inspection and raises `NoInspectionAvailable` for Alembic's offline `MockConnection`. [run01](run01/receipt.json) retains the original failed discovery. Run02 deliberately reproduces it as an expected negative observation. Its partial SQL stdout must never be applied. No predecessor migration was repaired or bypassed.

Use the exact supported 0013 or 0016 span after independently establishing the actual target revision. A fresh database uses the verified online migration path on a separately authorized, explicit v1 target. Do not stamp a version to avoid missing migrations. These local results do not authorize a real migration, establish prior-binary compatibility, prove populated scientific-corpus parity or replace live backup/restore and role/network validation.

## Commands and preserved inputs

Executed source is copied into each immutable run directory. Every command, return code, stdout/stderr, graph, schema snapshot, SQL input, row hash and cleanup result is linked by the run receipt's SHA-256 manifest.

```sh
.venv/bin/python docs/plans/ocean-v1/evidence/C27/migrations-20261101/verify.py
```

To repeat deliberately, supply a new, absent output directory; the harness rejects an existing directory and accepts no external database URL or cluster path:

```sh
.venv/bin/python docs/plans/ocean-v1/evidence/C27/migrations-20261101/rehearsal.py \
  --output /private/tmp/ocean-c27-new-evidence
```

No destructive schema downgrade is the v1 rollback strategy. No legacy routing, production target or data-transfer action is included.
