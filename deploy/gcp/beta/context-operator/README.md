# Exact context-grant operator

This adds C17 context privileges in the existing beta database as
`ocean_v1_migrator`. It creates no database objects, roles, memberships, credentials
or sequence grants and does not read or modify account/scientific/context rows.
Unexpected effective grants, PUBLIC ACLs, delegation or ownership drift are
refused without automatic resets. Only the fixed table/column policy in the
script is grantable; no caller SQL, privilege list or destination is accepted.

The immutable base is accepted operator `8e2a1630d5d2a7028495ec7b56a422a38b1c0807`,
image `operator@sha256:0a89057b7459342e191e4b194628bee00cc7544749489df9f85f31508399e7b3`.
Its accepted helper/source manifest is checked before execution. The new script
and privilege contract are separately pinned to a full source checkpoint.
After committing that source, prepare a new private source-only build context:

```sh
.venv/bin/python deploy/gcp/beta/context-operator/prepare_context.py \
  --revision FULL_CONTEXT_SOURCE_COMMIT --output /private/tmp/NEW_CONTEXT_OPERATOR_BUILD
```

The later cloud operator uses the existing migrator service account and exact
`ocean-v1-beta-migrator-database:1` DSN reference mounted as
`OCEAN_V1_OPERATOR_DATABASE_URL`. No secret values enter build args, CLI arguments,
source manifests or logs. Required environment includes production beta project,
exact SQL connection name and `OCEAN_V1_CONTEXT_OPERATOR_REVISION`. All execution
flags remain false; ambient `DATABASE_URL` and bootstrap password inputs are
rejected. Invoke with exact `--confirm-project`, `--confirm-database`,
`--confirm-source` (new context commit) and `--confirm-operator` (accepted base
operator commit). The existing loopback proxy is stopped on terminal outcomes.

Production preflight requires actual PostgreSQL16, independent beta database,
restricted unmapped migrator/serving roles, exact migration head0021 and reviewed
C17 column ownership. The SQL transaction adds table SELECT/INSERT for the four
C17 tables, column-only UPDATE on their mutable head/metadata/delivery fields,
INSERT on audit_event and **SELECT(created_at) only** on audit_event. Actual
SQLAlchemy AuditEvent INSERT uses RETURNING created_at; native rehearsal first
proves INSERT-only access fails, then proves this narrow additional column read
is sufficient. No full audit/history read grant is added. Fresh-connection
readback verifies the final effective policy, including no GRANT OPTION,
DELETE/TRUNCATE, account writes, sequence or application-function access.

The disposable native rehearsal passes28 checks on PostgreSQL18.3/pgvector0.8.7,
including real restricted-role C17 create/replay/rename/archive/conversation/
attachment/history and expected privilege denials. This is native software
qualification, not actual CloudSQL16 execution, IAM or GCS CAS acceptance.
See `docs/plans/ocean-v1/beta/context-20261103/native/attempt02/receipt.json`.
Do not rerun existing cloud bootstrap/migration/enrollment jobs. Root handles
source-bound image build, exact new job selection and cloud readback separately.
