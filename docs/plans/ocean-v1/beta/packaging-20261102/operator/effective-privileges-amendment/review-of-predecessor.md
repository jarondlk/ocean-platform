# Independent operator review — 2026-11-02 JST

Reviewed frozen operator SHA256
`e39b489dd76541c0edf1d2e1e312577fba51836d34223a1899a9493f78a36e87`.
The receipt's6source and55artifact hashes match. This is a read-only source and
retained-evidence review; no suite, native cluster, image or cloud action ran.
Original receipts and failed attempts are unchanged.

## Blocking finding: effective table and column privileges are incomplete

`finalize()` checks `information_schema.role_table_grants` only for the direct
`ocean_v1_serving` grantee (operator lines360–369). PostgreSQL explicitly omits
PUBLIC-derived grants from that view. Consequently an unexpected
`GRANT SELECT ON public.audit_event TO PUBLIC` is invisible to this check, even
though serving already has schema USAGE and gains effective access to private
history. The remaining role-attribute, creation-rights and application-function
checks do not reject that table grant. This follows directly from the query;
it was not executed against a database in this review. See PostgreSQL's
[role_table_grants documentation](https://www.postgresql.org/docs/current/infoschema-role-table-grants.html).

Column-specific grants are also absent from this table-grants inspection. For
example, an unexpected UPDATE on an `app_user` authority column can permit a
mutation without appearing as table-level UPDATE. Column permissions and their
delegation options need independent inspection; a direct table-only ACL
allowlist cannot establish the documented closed serving privilege boundary.
PostgreSQL describes those rights in
[role_column_grants](https://www.postgresql.org/docs/current/infoschema-role-column-grants.html).

Before accepting finalization, the owner should reject unexpected effective
table/column access, PUBLIC ACLs and delegation rights, while preserving the
unexpected state for inspection. Cover at least an injected PUBLIC private-table
grant, an injected serving authority-column write and a column GRANT OPTION.
Do not silently revoke unrelated drift. The existing23native cases cover direct
table grants and table GRANT OPTION, but do not close these paths. A later source
revision and distinct retained acceptance evidence must supersede this finding;
the current frozen receipt must remain historical. **Do not accept the current
finalization stage for live deployment.**

## Boundaries that match the reviewed local design

The target is fixed to the new beta project, exact Tokyo SQL connection,
`ocean_v1_beta`, proxy loopback5432, selected stage principal and separate source
and operator revisions. Missing confirmations, ambient `DATABASE_URL`, imported
application configuration, enabled execution flags, foreign targets and invalid
private inputs reject before stage work. Credentials enter through environment,
not CLI arguments or context; normal operator output uses fixed diagnostics and
bounded metadata. Migration raw subprocess output is captured rather than
printed. Stage-specific IAM/secret mounts must still avoid exposing unnecessary
credentials to the process.

Fresh bootstrap checks identity and empty state under a transaction lock,
refuses existing independent roles/schema objects, creates only the selected
roles/extension and revokes PUBLIC database/schema privileges. Role-attribute,
membership and ownership gates fail closed. Migration is an explicitly selected
fresh bounded process using the accepted API entry, exact head and object-owner
credentials. It does not invoke the legacy serving entry. Finalization grants
only three initial account/readiness/limiter tables in its normal fresh path;
the blocker concerns its incomplete rejection of drift.

Every parsed stage outcome attempts only the fixed loopback proxy shutdown
endpoint. Shutdown failure returns exit3 even if a stage committed. A2xx reply
is correctly qualified as a request acknowledgement; acceptance still needs
actual proxy process exit and successful per-container Cloud Run readbacks.
No timeout or stopped job is promoted to success.

The native PostgreSQL18 evidence is not Cloud SQL16 qualification. The limited
managed bootstrap principal, actual immutable operator/proxy images, private
routing/startup, secret IAM and live stage readbacks remain separate gates.
C23 ownership/role activation, user enrollment, scientific composition and the
twenty original operational gates remain closed or pending as documented.
