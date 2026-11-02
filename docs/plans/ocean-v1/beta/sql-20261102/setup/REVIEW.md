# Independent setup review — 2026-11-02 JST

**No blocking implementation issue was confirmed in the credential installer or
job renderer.** This closes independent source review for this local package;
it does not accept installed credentials, a deployed job or a live SQL stage.
Reviewed installer SHA256
`ac91c5b2b3ef0e6c6dc93ca325bf268cc3b86c4eeb4136891b70530fd6c5e23d`
and renderer SHA256
`3370b02b00a2d60c32c309bc267c0238d61f9c607294e02f6016a5e3eace8a76`.
All5source,7artifact and2static-input hashes match the retained receipt. Its
50mocked results were inspected, not rerun. No token, random credential,
container, native database or cloud mutation was created by this review.

## Credential installation

The helper defaults to a non-mutating plan and reserves a new metadata receipt
before token acquisition. The applied path checks the exact active project
and number534831104543, private Tokyo instance/connection, PG16 edition/tier,
network/private address, connector/encryption policy, backup/PITR, disk bounds,
deletion protection and existing `ocean_v1_beta` database. It accepts only the
seven fixed secret identifiers. The three existing containers must be empty;
only the four named new containers can be created. Exact project ownership and
Tokyo user-managed replication, plus absence of versions in any state, are
checked before generation and again during installation. A detected existing
version rejects overwrite or automatic resume.

Five distinct memory-only URL-safe values produce independent auth/internal
secrets and three coupled database credentials. Serving/migrator DSNs contain
the same password values stored in their separate role-password versions.
The bootstrap DSN contains the same generated postgres password used in the
final SQL update. Each installed version requires its own exact numeric name,
ENABLED state, CRC acknowledgement and metadata readback. No payload is read
back, and no token, credential, base64 data or payload digest/checksum enters
the receipt or CLI arguments. HTTP exception bodies and SDK output are not
printed. HTTPS target prefixes are fixed and redirects are refused.

The requests match the documented Secret Manager
[create](https://docs.cloud.google.com/secret-manager/docs/reference/rest/v1/projects.secrets/create)
and [addVersion](https://docs.cloud.google.com/secret-manager/docs/reference/rest/v1/projects.secrets/addVersion)
methods. Only after all seven coupled versions are retained does the helper
perform the instance-scoped postgres password
[users.update](https://docs.cloud.google.com/sql/docs/postgres/admin-api/rest/v1beta4/users/update),
without role-grant options. Completion requires an exact-target UPDATE_USER
operation to reach DONE without error.

Mutations are not retried. An uncertain or partial result retains phase,
pending mutation and known references and refuses automatic continuation.
The documented single-writer condition remains essential: list/version checks
are not an atomic conditional write against another installer or console user.
Lost acknowledgements or a failed local receipt update still require manual
inspection of the fixed resources. No new receipt or fresh credential set
should be used to bypass that recovery gate.

## Four private job bodies

The renderer checks the completed exact-project metadata receipt and all seven
numeric enabled version references. It accepts only a digest-pinned operator
image in the beta registry and embeds the reviewed API/operator source
revisions. The selected operator revision's source matches the previously
reviewed effective-privilege amendment. Syntax alone does not prove that a
provided digest contains those bytes; the root operator must bind the actual
immutable build/image evidence before submitting jobs.

The v2 task bodies keep one task, parallelism1, zero retries, a600-second
timeout, Gen2 and private-range Direct VPC routing on the exact beta network
and subnet. Two explicit identities separate bootstrap/readback from
migration/finalization. Stage mounts are limited to the required numeric refs;
no secret values appear in rendered bodies. Actual narrow instance/secret IAM
is not applied by this package. Since both containers share their task identity,
mount selection is not an isolation boundary against other secrets granted to
that same identity; the README correctly preserves that IAM gate.

Cloud Run's documented [Container](https://docs.cloud.google.com/run/docs/reference/rest/v2/Container)
fields include `dependsOn` and `startupProbe`, and the official
[jobs health-check guide](https://docs.cloud.google.com/run/docs/configuring/jobs/healthchecks)
supports HTTP startup probes. The proxy readiness endpoint and120-second probe
budget match that contract. The selected proxy's private-IP, loopback5432 and
loopback admin9091/quitquitquit flags agree with its
[versioned official documentation](https://github.com/GoogleCloudPlatform/cloud-sql-proxy/blob/v2.26.3/docs/cmd/cloud-sql-proxy.md)
and the operator's fixed shutdown target. Probe success does not authenticate
the SQL principal. The operator must perform its actual database checks, and
its shutdown acknowledgement must be followed by successful per-container
process-exit readbacks. Rendering never submits or executes a job.

## Remaining live gates

The installer still requires working CLI authentication, a single-writer
window and fresh live preflight; this review creates no credential or password
operation. Job submission additionally requires the actual accepted operator
digest/source evidence, dedicated identities, narrow secret/connector grants,
provider acceptance/readback and real private startup. Each SQL stage remains
an explicit action with complete results and proxy/container exits required.
Native PG18 and mocked REST checks do not establish Cloud SQL16 limited-user
capabilities. OAuth, account enrollment, scientific composition, C23 activation
and all original operational release gates remain separate and unaccepted.
