# Limited creator and rollback-only provider qualification

This amendment supersedes the operator source at `8b06a1b` for prospective builds. Its original password/privacy and privilege receipts remain unchanged, including their original source pins. `operator.before.py` contains those exact accepted operator bytes. The separate API source/migrations, historical scientific files and Cloud SQL resources are outside this amendment.

The new operator sets each newly created application's role database defaults **before** revoking its automatic creator membership. It keeps the original final role-attribute and zero-membership checks, client-side SCRAM preparation, logging/utility-collector attestation, fresh-database checks and fail-closed errors. Correct ordering alone does not establish that a managed provider permits the required revocation.

## Preserved failed qualification

`native-root-20261102/receipt.json` is the original failed native run, with cleanup verified. `operator.ordering-candidate.py` matches its operator source pin; `native_rehearsal.py` and `native-root-20261102/native-harness-source.py` match its harness pin. The initial harness incorrectly assumed that its non-superuser fixture would remove the automatic membership on `REVOKE`, then fail at `ALTER ROLE`. PostgreSQL automatically used the bootstrap superuser (OID10, `native_admin` in that fixture) as grantor. The current `postgres` was another role, so the membership persisted and the strict final membership guard refused the operation instead. That failed run is not a successful bootstrap qualification.

The new `probe_native_rehearsal.py` distinguishes both profiles in separate disposable clusters:

* `--profile other-grantor`: initialize `native_admin` at OID10 and create a separate non-superuser `postgres`. Both old and corrected role helpers must refuse the residual membership and roll back the application roles. The NOLOGIN probe must report unsupported behavior.
* `--profile self-grantor`: initialize `postgres` at OID10, create a separate native administrator, then use that administrator to demote `postgres` to a real non-superuser with CREATEROLE/CREATEDB. The old order must fail with SQLSTATE42501 at defaults after revocation; the corrected helper must succeed with restricted attributes and zero memberships, and both synthetic role logins must authenticate with SCRAM.

These fixtures explicitly grant `pg_read_all_settings` only on the owned local server and use PostgreSQL18. They qualify the exercised native behavior, not actual Cloud SQL PostgreSQL16, vector installation, migrations or C23 worker execution. The root agent owns launching the reviewed native harness. No native result is claimed until its own new receipt passes.

## Actual provider observation before real bootstrap

The explicit `qualify` stage accepts the existing exact project/database/API-source/operator-source confirmations and the bootstrap-principal DSN. It requires no application role passwords. Within an explicit transaction it refuses a pre-existing fixed `ocean_v1_beta_setup_probe`, creates only that role with NOLOGIN and every elevated attribute disabled, reads its finite membership/grantor identities including OIDs, attempts database defaults followed by creator-membership revocation, then always rolls back. It disposes the pool and checks from a distinct physical session that the probe is absent and the application role/table inventories are unchanged. It never drops an existing role, creates actual application roles, binds a password or changes provider logging/privileges.

A supported observed sequence returns exit0/`qualification_observed`; a refusal returns exit2/`qualification_refused`. Both explicitly return `bootstrap_authorized=false`, and the existing proxy finalizer runs on both success and failure. Root must separately review actual private-job evidence, logging/collector/provider configuration, finite ownership and role metadata before choosing a real bootstrap. In particular, a successful probe does not qualify the provider's vector extension or C23 restricted-role execution checks.

`readback` now adds `provider_safety`: actual database/public-schema owners; finite current-principal attributes/OID; whitelisted logging, collector and search-path settings with source/context/pending_restart; and only matching finite role/database overrides. It reads no password catalogue, SQL history, DSN, arbitrary configuration values or secret material. Hidden settings remain explicit, and metadata never authorizes password SQL by itself. The strict independent privacy attestation still runs before any sensitive binding.

## Verification and limits

`probe_checks.py` exercises20 pure checks for exact target/source validation, fixed probe scope, supported/refused grantor outcomes, rollback/new-session absence, preserved inventories and pre-existing roles, unreadable baselines, sanitized SQLSTATE diagnostics, exit status and proxy-finalizer behavior. Existing password-policy32 and auth/proxy26 checks are re-run into new files, preserving their original receipts. The new native harness scans the entire owned server-log byte stream for exact synthetic plaintext and verifiers and for any SCRAM marker, exports neither the log contents nor secret hashes, and destroys its cluster after confirming shutdown.

The amendment's receipt/verifier binds the current operator, checks, harness and documentation, explicitly maps historical native pins to frozen source bytes, and preserves the failed run. No Cloud SQL mutation, image build, renderer change, migration, data transfer or deployment is performed by this amendment. Actual provider qualification and bootstrap remain explicit gates owned by the root deployment flow.
