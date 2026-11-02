# Bootstrap password statement review — 2026-11-02 JST

**Verdict: change the client-side password preparation before the first live
bootstrap.** The current code sends a cleartext password inside the SQL statement
seen by PostgreSQL. Server statement/error logging can retain it. This is a
documented path, not an assumption that all Cloud SQL statements are automatically
redacted. No actual exposure is established: this review made no cloud calls or
test runs, and the current operator handoff reports no live secret versions or
bootstrap execution.

Reviewed checkpoint: `756c7a7dc46d4ba75e3a0308b7ab23d9b3553bfe`,
`deploy/gcp/beta/operator/operator.py` SHA256
`988fced9ee949df08a2d4d74a24d23c931badfdfb16fe71628b2afe23cfa4c00`.
This review is scoped to `create_roles` and its direct DB-driver statement path.
It does not accept an image build or attest to actual live database flags.

## What the current protections cover

`create_roles` passes `(env[key],)` to `cursor.execute` for
`CREATE ROLE ... PASSWORD %s`. Psycopg2 adapts those values into the SQL sent to
PostgreSQL; a placeholder in Python is not server-side password redaction. The
driver documents that `mogrify` exposes the same bound query that `execute`
would send. Do not call or print it with real credentials.
[Psycopg2 cursor reference](https://www.psycopg.org/docs/cursor.html#mogrify).

The trusted Cloud SQL proxy protects the connection path. The operator's fixed
error messages and SQLAlchemy `hide_parameters=True` protect their own output.
They do not rewrite PostgreSQL's statement text or control its server logs;
this helper also uses a direct DB-driver cursor.

## Server logging and redaction

PostgreSQL16 documents `log_min_error_statement=ERROR` as the default, with the
failing statement included at that severity. A failed role-creation statement
can therefore enter the server log even when successful DDL is not being
logged. Enabling `log_statement` or duration logging provides other statement
paths. Actual instance values have not been inspected in this review.
[PostgreSQL logging](https://www.postgresql.org/docs/16/runtime-config-logging.html).

Cloud SQL separately warns that non-`none` `log_statement` can log passwords.
Its recommendation to use pgAudit does not establish blanket masking of ordinary
PostgreSQL error/statement logs.
[Cloud SQL flags](https://docs.cloud.google.com/sql/docs/postgres/flags).
Cloud SQL has an explicit pgAudit literal-masking feature; its documented scope
is the audit record produced by the extension. No such setting or extension is
assumed here, and it is not evidence that other server log paths redact the
statement. [Cloud SQL pgAudit masking](https://docs.cloud.google.com/sql/docs/postgres/pg-audit#mask-sensitive-data-in-audit-logs).

PostgreSQL's own role documentation cautions that cleartext passwords in role
commands may appear in logs. The `ENCRYPTED` keyword or a server-side
`password_encryption=scram-sha-256` setting does not remove the supplied plaintext
from the original SQL text. Those settings concern how the password is stored.
[ALTER ROLE](https://www.postgresql.org/docs/16/sql-alterrole.html),
[CREATE ROLE](https://www.postgresql.org/docs/16/sql-createrole.html).

## Minimal change

Use the existing psycopg2/libpq client to generate a **SCRAM-SHA-256 verifier in
memory**, then bind only that verifier in the same fixed `CREATE ROLE` statement:

```python
from psycopg2.extensions import encrypt_password

raw_connection = connection.connection.driver_connection
verifier = encrypt_password(
    env[key], role, scope=raw_connection, algorithm="scram-sha-256"
)
if not verifier.startswith("SCRAM-SHA-256$"):
    raise OperatorError("Independent role password preparation rejected")
# Keep the existing identifier composition and restricted role attributes.
statement(connection, template, role, parameters=(verifier,))
```

This is an implementation sketch, not a patch applied by this review. Explicitly
select SCRAM, require supported libpq/server versions, and fail with the existing
fixed safe diagnostic if preparation fails. Do not fall back to MD5, plaintext,
or an environment-selected algorithm. Preserve current transaction, identity,
role-attribute and fresh-database checks.

Libpq specifically provides this operation to avoid transmitting the original
password in commands that can be logged. Psycopg2 exposes it as `encrypt_password`;
an explicit algorithm also avoids its implicit server-setting lookup.
[Libpq password preparation](https://www.postgresql.org/docs/16/libpq-misc.html#LIBPQ-PQENCRYPTPASSWORDCONN),
[Psycopg2 encryption API](https://www.psycopg.org/docs/extensions.html#psycopg2.extensions.encrypt_password).
PostgreSQL16 accepts an already prepared SCRAM verifier without converting it
again. This follows the same principle as `psql`'s `\password`, which prepares
the password on the client before issuing the role command.
[psql password command](https://www.postgresql.org/docs/16/app-psql.html).

## Remaining confidentiality boundary and acceptance

A SCRAM verifier is still sensitive authentication material. It can appear in
statement/error logs if they capture the SQL and can support offline password
guessing. The change removes the cleartext-password statement path; it does not
make verifier logging acceptable or prove universal redaction. Keep both values
out of output, receipts, query dumps, exception details and debug logging. Retain
the existing protected transport and restricted log access. There is no need to
disable server diagnostics as a substitute for this client-side correction.

Before live use, the owning change should establish that the driver receives a
valid SCRAM verifier and never the plaintext password; unsupported preparation
fails closed; and the generated password still authenticates with the actual
restricted role in an owned disposable PostgreSQL check. A controlled failing
statement may use a disposable synthetic canary to qualify server-log behavior;
do not probe that behavior with a live credential. Preserve old receipts,
checkpoint the changed operator source, and rebuild/verify its exact image
before application. This review itself changes no operator code or live state.
