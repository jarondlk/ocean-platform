# Explicit first beta account — local preparation

**Prepared locally; no real user, Google token, cloud change or native
PostgreSQL qualification has been performed.** The additive enrollment image
derives from the exact accepted API digest `f2e73ca9…5a6ee4f`. It adds only its
root-owned helper/manifest and runs as UID/GID10001. Existing operator, API,
serving, model, migration and historical receipt files remain unchanged.

The default helper CLI emits an offline plan. It does not read private inputs,
acquire/verify a real token, contact a database, stop a proxy or enroll anyone.
Applied operation requires explicit target/source confirmations, an application
role and account type. There is no role default, email-to-subject inference,
legacy import, update, upsert or automatic retry. Root must first obtain the
concrete user's account/role decision; this package invents no approval.

## Identity proof and cross-client qualification

The intended proof is a current Google-signed ID token captured by the
authorized root process from the selected SDK **human user** login. The token
must be captured directly in private process memory, never printed by running
`gcloud auth print-identity-token` directly in a visible shell. Do not use a
service-account impersonation token, ADC inference, access token, bare userinfo
response or an email-derived subject. This package acquires no token itself.
Root must independently bind the expected audience to the actual official SDK
OAuth client; do not trust a decoded token's own audience as that allowlist.

Google-auth verifies the signature against the fixed official public
certificate endpoint, issuer, audience and time bounds. The helper additionally
requires RS256, an exact single audience/authorized presenter, true
`email_verified`, the explicitly selected normalized email, a bounded subject,
maximum one-hour issue/lifetime and at least60seconds remaining. It rejects
service-account email identities. Only Google's public cert GET leaves the
process; the ID token is not transmitted to that endpoint. Redirects, arbitrary
certificate URLs and token-error details are rejected. No SDK token becomes a
beta session or private API bearer token.

Google documents an account-stable, globally unique `sub` and publishes
`subject_types_supported: ["public"]` in its OIDC metadata. **The cross-client
mapping follows from those documented properties:** the same Google Account's
SDK and future beta-web Google identity should use that public subject. This
does not mean their audiences are interchangeable; each token must be verified
for its own approved client. Actual SDK token/profile and later beta OAuth
callback comparison remain live evidence gates.
[Google OIDC claims and discovery](https://developers.google.com/identity/openid-connect/openid-connect).

Google also warns that email can change and is not the stable identity key.
`email_verified` alone does not establish current third-party mailbox ownership
outside Gmail/Workspace. Here the explicit approved email is a comparison guard;
the signed public subject identifies the Google Account. Root must approve the
actual selected human account rather than provision arbitrary matching mail.
The later beta host independently verifies its own Google callback and rechecks
the current database record. [Google token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token),
[SDK token command reference](https://docs.cloud.google.com/sdk/gcloud/reference/auth/print-identity-token).

## Private application and exact database

Applied invocation uses only non-secret confirmations:

```sh
python /opt/ocean/beta_enroll.py --apply \
  --confirm-project ocean-v1-beta-20261101 \
  --confirm-database ocean_v1_beta \
  --confirm-source 7924a28e919b1fb751890c694f7b1f9b26b104ff \
  --confirm-enrollment FULL_ACCEPTED_ENROLLMENT_COMMIT \
  --role EXPLICITLY_APPROVED_ROLE --account-type EXPLICITLY_APPROVED_ACCOUNT_TYPE
```

Root supplies these through a private job environment and narrowly scoped
Secret Manager references, with actual numeric versions retained separately:

- `DEPLOYMENT_ENV=production`, exact `OCEAN_V1_PROJECT_ID` and
  `OCEAN_V1_SQL_CONNECTION_NAME`; four execution flagsfalse.
- `OCEAN_V1_ENROLLMENT_REVISION` matching the committed packaged manifest.
- `OCEAN_V1_ENROLLMENT_DATABASE_URL`: restricted `ocean_v1_migrator` only, exact
  `postgresql+psycopg2` loopback5432 `ocean_v1_beta`; ambient `DATABASE_URL`,
  postgres/admin credentials and arbitrary query options reject.
- `OCEAN_V1_ENROLLMENT_ID_TOKEN`: the actual current signed user token, private
  mounted version; never embed it in a rendered literal environment/body.
- `OCEAN_V1_ENROLLMENT_EXPECTED_EMAIL` and
  `OCEAN_V1_ENROLLMENT_EXPECTED_AUDIENCE`: the actual approved account and SDK
  client configuration. They are not inferred or populated during preparation.

The helper checks actual database/current/session user, PostgreSQL16, exact
head0021, restricted attributes/zero memberships, migrator ownership and the
account-table column inventory. It locks the public account/invitation tables,
refuses any account or invitation state and inserts exactly one active Google
account under the selected role/account type. The schema-qualified fixed typed
INSERT follows the actual AppUser contract without importing `db/__init__` and
its legacy connection/config modules. It does not import `api.main`, discover
users or change privileges. Model/authorization source hashes are retained.

Commit is followed by a new connection and exact private row readback. Output
contains only fixed statuses, count, provider and the explicitly selected role/
account type, never a subject, token, DSN, email, private-value hash or UUID.
Fixed errors replace driver/library details. A failed or uncertain post-commit
readback requires protected manual inspection; it does not authorize retry.
The application token/DSN is never a SQL value. Approved AppUser business
identity metadata necessarily enters the database and may appear in protected
ordinary DB diagnostics in this isolated project; no universal no-PII-log claim
or new logging flag/privilege is introduced.

For applied success, failure or malformed invocation, the fixed proxy finalizer
requests only loopback9091 `/quitquitquit`. No acknowledgement means exit3,
even after a committed account. Actual successful proxy/container exits remain
required separately. A dry-run plan has no proxy/network action.

## Source context and local checks

After the new source is accepted and committed, export only these committed
package bytes into a new directory:

```sh
.venv/bin/python deploy/gcp/beta/enrollment/prepare_context.py \
  --revision FULL_ACCEPTED_ENROLLMENT_COMMIT \
  --output /private/tmp/ocean-beta-enrollment-NEW_CONTEXT
```

No credentials, identity fixtures, scientific data or whole checkout enter the
context. Building, scanning, image-manifest/digest verification and deployment
are separate parent-owned work; no image build is claimed here.

The current41offline checks verify real RS256 cryptography with ephemeral
**synthetic offline test keys/tokens**, wrong signature/issuer/audience/presenter/
verification/time/subject rejection, configuration guards, no-I/O default,
fixed AppUser/role contract, actual synthetic SQLite INSERT/first-account
refusal and safe failure/finalizer behavior. SQLite tests explicitly mock the
PostgreSQL preflight; they do not prove Cloud SQL locking, limited role behavior
or a genuine Google SDK identity. Test keys/tokens are not packaged or exported.
An initial test import exposed `db/__init__`'s legacy-config side effect; the
production helper now uses the checked typed table contract and imports no
legacy package. No prior suite or native rehearsal is repeated.

The read-only receipt verifier checks pins without rerunning those cases:

```sh
.venv/bin/python docs/plans/ocean-v1/beta/enrollment-20261102/verify.py
```

Independent source/API review, concrete role/profile decision, actual SDK
signature/audience proof, real DB preflight/locking/commit receipt, source-bound
image/job, narrow IAM/secret access and successful exits remain gates. OAuth,
scientific catalogue/provider composition, queue/worker/C23 and release gates
are not accepted by preparation of an account helper.
