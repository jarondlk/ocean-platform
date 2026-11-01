# Effective privilege amendment

This supersedes only the original operator's finalization privilege inspection.
The [independent review](../REVIEW.md) found that direct
`information_schema.role_table_grants` omitted PUBLIC and column-only rights.
The original package's local receipt remains historical and must not be used
to accept the unfixed finalization stage for deployment. All six original source
bytes are preserved under `frozen-source/`; `original-receipt.json` is an exact
copy of the unchanged predecessor receipt. Original guard/native artifacts and
failed attempts are neither modified nor relabelled.

`verify_serving_privileges` now inspects actual PostgreSQL effective table and
column rights, including delegation rights, over all non-system user schemas.
It checks explicit PUBLIC relation and column ACLs independently, so a PUBLIC
grant on an otherwise allowed table is also rejected. Initial serving policy
remains SELECT on `app_user`/`alembic_version` and SELECT/INSERT/UPDATE on
`rate_limit_bucket`, only in public; no sequence access is allowed. PostgreSQL17+
MAINTAIN privilege inspection is version-gated for Cloud SQL16 compatibility.
The check runs before and after the normal narrow grants. It never revokes or
resets unexpected state; a failed stage preserves that state for inspection.

The new owned native run passes **38 checks**, retaining the previous bootstrap,
SCRAM role, restricted migration, limiter, direct-grant/delegation, denied access
and proxy-finalizer checks. It adds five actual grant scenarios:

- PUBLIC SELECT on private `audit_event`.
- PUBLIC SELECT on only its `id` column.
- Direct serving UPDATE on only the `app_user.role` authority column.
- SELECT with GRANT OPTION on only an otherwise allowed `app_user.email` column.
- PUBLIC SELECT on an otherwise allowed `app_user` table.

Each scenario first demonstrates actual effective access using a real serving
connection, then verifies finalization refuses it and exact table/column ACLs
remain unchanged. Only those deliberately injected fixture privileges are
removed afterward inside the owned disposable cluster. No production operator
reset/revoke path is added. No account row is enrolled or changed, and no real
data is used. All 26 existing local guard/finalizer cases also pass with the new
source. Ruff passes the changed source and new amendment verification/harness.

The accepted native server is stopped; status3, closed port, absent PID and
temporary directory removal are observed. This still proves native PG18, not
Cloud SQL16's limited-superuser bootstrap, actual cloud proxy process exit,
private routing/IAM or live deployment acceptance. C23 role/ownership bootstrap
and execution remain unqualified and disabled. No cloud or image action ran.

The read-only verifier binds the source supersession and unchanged predecessor
receipt/artifacts, current source/native pins and the new output artifacts:

```sh
.venv/bin/python docs/plans/ocean-v1/beta/packaging-20261102/operator/effective-privileges-amendment/verify.py
```

Do not repeat the successful stateful run for unchanged source. Source-only
operator context generation and actual immutable image build/review remain
parent-owned next steps. The existing four explicit stages, private credential
contract, fixed loopback proxy finalizer and all other original live gates remain.
