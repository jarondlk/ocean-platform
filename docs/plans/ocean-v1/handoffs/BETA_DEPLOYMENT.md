# Beta deployment continuation — 2026-11-02 JST

State: **authenticated host/API software delivery accepted; two immutable images
and actual Linux container smoke accepted; private SQL and an empty beta DB exist;
beta DNS delegation applied with explicit approval. Public hosting is not deployed.**
**Live bootstrap hold:** original operator756c7a7 has a confirmed plaintext-password SQL logging risk and must not be executed. The reviewed replacement8b06a1b is now source-qualified (32pure+26guard+48actual native checks) and its renderer reference is updated. Its new immutable image, actual CloudSQL privacy profile and live stage/proxy qualification remain gated by SDK reauthentication. No live values or role creation have occurred.

Branch `overhaul`. Scheduler stays PAUSED. All original C26/C27/scientific receipts
remain immutable; no further numbered component or automation is created.

## Source and accepted software

App source `50566b7cfa4a0d8ee19686f0109e74f3a2a45d45` passes all five required
jobs in [CI41322838746](https://github.com/jarondlk/ocean-platform/actions/runs/41322838746):
6747backend passes/626explicit skips/83.67%coverage (70%threshold unchanged),
318actual PostgreSQL/16capability skips plus migration/upsert/backup/restore;
132legacy/1051prototype/50host-unit+1actual standalone HTTP cases; all frontend
builds/typechecks/production audits pass. Conditional push-only dependency review
is skipped as configured. [Separate hosted delivery](../beta/checkpoint-20261102/hosted-delivery/delivery.json).

Current880-path app identity `sha256:1d3b93f3abbf914d165982a43d4a24f830d975712029e7e5570cb0b868828128`
reconciles841unchanged accepted paths,3intentional supersessions (workflow,
optional UI fetcher, static tsconfig exclusion) and36additive app paths.
5368prior evidence files,90C27 artifacts and42protected paths verify. Later
packaging commits preserve those app bytes; their own wrappers have separate
proof and are not falsely attributed to this earlier hosted run.

Pushed packaging `7924a28`, original smoke `74f2262`, diagnostic correction
`ded63b5`, original operator `756c7a7`, cloud/CI checkpoint `6f5a385` and setup `8075542` are on `overhaul`. Password-safe source `8b06a1b` is the current required operator successor; its push is part of this checkpoint. Original native and
failed smoke attempts remain preserved. Unrelated root README, legacy deployment
template and scientific/audit/benchmark files remain excluded from commits.

## Cloud identity and cost controls

Only new beta project `ocean-v1-beta-20261101`, number534831104543, Tokyo
`asia-northeast1`; existing billing linked without altering its arrangement.
**Ambient gcloud project is still legacy: every operation needs an explicit
project.** The sole approved legacy-project exception is the new beta NS record
below; never broaden it to apex/www/legacy deployment/data/IAM changes.

Beta-only gross ¥50,000/month all-service alert (50/75/90/100%) and separate
¥3,000/month Cloud Run cap were saved/read back. Neither is a whole-project hard
cap. Initial beta-only target is¥50,000; notify before exceeding it, despite the
user's stated¥100,000 upper amount. [28actual public JPY SKU quote](../beta/quotes-20261102/README.md)
qualifies a bounded31-day scenario at¥35,604.05 including10% cost reserve and no
free credits. This is conditional usage, not an invoice or tax attestation.
No always-on worker or model/data usage is budgeted. Original stress envelope
remains historical. Initial image-build allocation is¥100; bounded plans retain
actual attempts and declared maxima.

Twenty empty foundation operations verified: registry, customVPC/subnet,
4dedicated initially ungranted runtime identities,4private uniform buckets,
8empty Secret Manager containers and a PAUSED queue. The unused default Compute
identity's automatic Editor grant was removed only in beta; other then-current
bindings preserved. Dedicated build identity has only beta-repository write,
source-bucket read, beta log-write and conditional create-only smoke evidence
prefix access. No deploy/data/secret access was granted to the builder.

## Actual images and container evidence

Source-only contexts from `7924a28` built successfully with pinned official bases:

- Frontend: `asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/frontend@sha256:adb5bc75dbc56d146bdf6e63f83a3dc8b3867b0318de0c2c02ba6fc56023e9dc`
- API: `asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta/api@sha256:f2e73ca98ba915e29a4dd7dc429e34a165475faa7f9000bc8cefaa10e5a6ee4f`

[Actual container smoke](../beta/builds-20261102/container-smoke-receipt.json)
passes nonroot/Linux/embedded source manifest checks, real API import without
legacy entry or DB credentials, unconfigured API startup refusal, actual login
and built CSS200, wrong-host403 and unauthenticated runtime401. All owned
containers removed; network disabled, no real OAuth/DB/scientific claim.
First smoke07cd8231 failed after API checks; a confirmed harness assert.match
string/RegExp defect was fixed and bounded diagnostics added. Full first failure
attribution stays qualified because its full receipt was not uploaded. Corrected
run32ed8ad4 passes and its private artifact was downloaded/verified. Both preserved.

Reviewed database operator source `756c7a7` has26guards/38actual native tests and
separate independent review after fixing PUBLIC/effective column/delegation
privilege drift refusal. Original23-case receipt/source and all intermediate
failures remain frozen. [Amendment](../beta/packaging-20261102/operator/effective-privileges-amendment/README.md).
Operator build **ae32526a-ba81-4d68-8251-0a2f5592f5f9** was submitted; its final
state/digest remain **unverified** because CLI reauthentication is now required.
Resume by describing this exact existing build, never resubmit a duplicate.

## Actual private database

Private-only Enterprise PostgreSQL16 `ocean-v1-beta-sql` and empty `ocean_v1_beta`
exist. Actual RUNNABLE/Tokyo-zone-a/db-custom-2-7680/ZONAL/SSD20GiB/growth-limit30/
private10.93.0.0/20/no public IP/ENCRYPTED_ONLY/connectorREQUIRED/deletion-protection/
backup7/PITR7 match the concrete plan. PITR logs are actually CLOUD_STORAGE;
quoted log allowance is labelled, not misrepresented as actual SSD billing.
[Settings proof](../beta/sql-20261102/settings-verification.json).
No cloud migration, application role, user enrollment or secret version was
created yet. C23 Cloud SQL limited-superuser/function-owner qualification remains
an explicit separate gate; no weakening of accepted role checks is permitted.

Private credential and Cloud Run job setup code is being prepared under
`deploy/gcp/beta/setup` with default read-only planning, exact target preflight,
zero-existing-version requirement, private coupled secret values and postgres
password last. The installer/renderer passed50mocked guards and independent review; no real value, SDK call or job was created. Apply still waits for reauthentication and completion of the separate operator password-safety amendment. The renderer now selects8b06a1b through a separate one-constant supersession with four synthetic binding checks. The old50-case setup source/artifacts remain immutable. Use [current renderer verifier](../beta/sql-20261102/setup/operator-revision-amendment/verify.py); the original setup verifier intentionally targets old807source. The new image digest and real refs are still required.
No fake OAuth client or fabricated provider/data may be mounted in production.

## Actual beta DNS/TLS

New beta project public child zone `ocean-v1-beta-domain` owns
`beta.oceaninfobio.com.` at ns-cloud-e1/e2/e3/e4.googledomains.com. Per-project DNS
authorization and its exact CNAME exist in the child zone. Global managed cert
`ocean-v1-beta-domain-cert` and exact-host map/entry exist; last observed certificate
state was **PROVISIONING**, map entryACTIVE. Public Google DNS resolves both the
beta NS set and authorization CNAME. Current certificate issuance still requires
a fresh readback; no TLS endpoint, publicA/AAAA, LB, proxy or IP is published.

Automatic review initially rejected touching the legacy authoritative parent
zone. The user then explicitly approved exactly one new NS delegation in this
chat. It was applied to data-infra-infobio/oceaninfobio-com, TTL300, no deletions.
[Authorization](../beta/dns-20261102/delegation-user-authorization.json),
[preservation proof](../beta/dns-20261102/parent-preservation-proof.json).
Four prior non-SOA record sets are byte-equivalent; the DNS service incremented
SOA serial1→2 with every other SOA field unchanged. The first overly strict
all-record-byte-equality check stopped on this normal metadata increment; no
reset or further mutation followed. Do not claim all five prior record bytes
identical or extend the exception to any other legacy change.

## Immediate continuation and remaining gates

GCP CLI refresh failed at09:01JST. A new SDK login is waiting in owned PTY98412;
IABtab1 is the user identity/passkey page. The user was asked to finish and leave
the verification-code page open; never copy the code/token into chat or source.
Native Mac controls are locked, but IAB works. No new login is needed if this
pending flow completes. Check actual session/tab state before starting another.

Continue independent local setup/review and checkpoint current cloud/CI evidence
while waiting. After reauthentication, verify the existing operator build and
actual cert state, then review/apply only the finished private credential/IAM/
operator jobs. Initial bootstrap/migration/finalize/readback are explicit bounded
stages with private proxy/directVPC and trusted cleanup, not automatic deployment
migration. First actual Cloud SQL execution and backups/restores remain unrun.

Independent Google OAuth client/account enrollment, real callback/session,
private runtime/service/provider composition, beta LB/ingress/default-URL/DNS/TLS
and full UI validation remain required. Real queue/outbox/private invocation and
retained worker integrations must precede research/experiment dispatch. The bare
API reports absent science unavailable; no data acquisition/import/legacy-user
copy or scientific approval is inferred. All20 original live release gates and
openP2 D26-07 remain; release acceptance is false. No Cloud Run service/job/worker,
LB/IP, real data, task dispatch or secret value has been deployed by this phase.

## Current password-safe continuation

[Password amendment](../beta/packaging-20261102/operator/password-safety-amendment/README.md) and its separate independent REVIEW pass:32purechecks,26guard regressions,48actual owned native checks, all cleanup verified. Client libpq supplies only SCRAM verifiers to role SQL, with no plaintext/MD5 fallback. Actual same-session ordinary logging/debug/sampling and finite audit/utility-collector profiles are attested before preparation/binding. Full owned logs and query texts contain neither synthetic plaintext nor verifier; ordinary query metrics remain active. Old756sources/3receipts and intermediate attempts are preserved. This is not universal server-crash redaction or actual CloudSQL acceptance.

New source-only context `/private/tmp/ocean-beta-operator-context-8b06a1b` and [bounded build config](../beta/builds-20261102/operator-password-safe-cloudbuild.json) are prepared **but not submitted**. Oldae32526a remains historical/unverified/superseded. Proposed total initial build ceilings remain below the already planned¥100build allocation; no cloud call occurred for this new image.

After sign-in, fresh exact-target readbacks and the [two-flag privacy plan](../beta/sql-20261102/logging-policy/PLAN.md) precede live bootstrap. Preserve unrelated flags and use fresh settingsVersion; do not silently add unsupported duration/sampling flags. Actual active utility/audit/QueryInsights collection may require its own reviewed minimal adjustment. Never treat local48-case proof as actual provider attestation. No secret versions, real credential values, migrations, application roles, accounts or CloudRun jobs have been created.

The open SDKpage was rechecked and still requests the user's passkey identity confirmation. Complete that flow in IABtab1 and use owned CLI session98412; do not start duplicate sign-in or cloud jobs. No further independent local implementation is required before this next cloud stage. All published hosting/OAuth/science/worker/release gates above remain.
