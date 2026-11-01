# Effective privilege amendment review — 2026-11-02 JST

**The table/column privilege blocker in REVIEW.md is resolved for the local
operator checkpoint.** Reviewed current operator SHA256
`988fced9ee949df08a2d4d74a24d23c931badfdfb16fe71628b2afe23cfa4c00`.
The new read-only verifier passes:4current sources,21amendment artifacts,
55unchanged predecessor artifacts and6preserved original sources. Prior
REVIEW.md and receipts remain unchanged. No guard suite, native database,
container or cloud operation was repeated by this review.

The amended inspection uses PostgreSQL's effective `has_table_privilege` and
`has_column_privilege` checks, rather than the direct-grant information-schema
view. It checks every non-system user schema and compares schema/table/privilege
against the fixed public-schema allowlist. A disallowed effective privilege or
any corresponding GRANT OPTION rejects finalization. Allowed table rights do
not excuse forbidden column-only writes or column delegation. Explicit PUBLIC
relation and column ACLs are rejected separately, including PUBLIC access on an
otherwise permitted table. Sequence access is forbidden. Table MAINTAIN is
inspected only when `server_version_num >= 170000`, avoiding use of that
PostgreSQL17+ privilege name on the intended PostgreSQL16 target.

The check runs before and after the three narrow grants, within the owning
stage transaction. Unexpected privileges are refused and remain inspectable;
no automatic revoke/reset path was introduced. The existing role/membership,
ownership, creation-rights and application-function checks remain in place.
The other target, credential, migration-process and proxy-finalizer boundaries
reviewed previously are unchanged.

The retained38-case native result now demonstrates actual effective access,
refusal and unchanged ACLs for PUBLIC private-table SELECT, PUBLIC private-column
SELECT, serving authority-column UPDATE, allowed-column SELECT with GRANT
OPTION, and PUBLIC SELECT on an otherwise allowed table. It retains the earlier
direct-grant/delegation, limited serving DML, denied access and finalizer checks.
Its26guard results and complete native cleanup are source-bound by the new
receipt. The original23-case receipt is historical and is not retargeted.

No further blocker was confirmed in this amendment for checkpointing and
building the operator image. This verdict does **not** accept live SQL stages:
the intended Cloud SQL16 limited bootstrap principal, actual immutable image and
proxy, private connectivity, secrets/IAM, exact live schema/grants and successful
per-container proxy/job exits still require their own evidence. Native PG18
does not prove managed-service capability. C23 activation, account enrollment,
scientific composition and the original twenty operational gates remain
separate and unaccepted here.
