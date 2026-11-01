# Independent v1 operator runbook

This is a local release-preparation artifact, not an apply script or a release
authorization. **Stop before any live action:** the manifest is not deployable,
all 20 operational gates remain `not_run`, and concrete beta targets and runtime
integrations are missing. The existing legacy site remains independent.

## 1. Identify and verify the candidate

Read `release-manifest.json`, `requirement-evidence.json`, `release-gates.json`
and the C26 defect register together. Verify the C27 package with:

```sh
.venv/bin/python docs/plans/ocean-v1/evidence/C27/verify.py
```

The verifier reads evidence and source; it does not provision, migrate a
database, dispatch a task or mark live gates passed. Its success means the
recorded local preparation is intact. A later candidate must receive new
source-bound software/runtime evidence; do not relabel the old receipts.

The exact accepted software commit is `afe9cb2d1a6d2c28a834daab1a342de4563dc3a3`.
C26 closure `a69eb57` adds evidence/docs. C27 keeps all 844 accepted source paths
unchanged and pins its separate operator tools. No image digest, tag or live
revision is inferred from a commit or the label `v1.0.0-rc.1`.

## 2. Resolve the live preflight

Create a private non-secret operator worksheet from
`deploy/gcp-v1/examples/site.operator.pending.json`. Require an explicit isolated
v1 project ID/number and region/zone, frontend/API/controller services and exact
image digests, database/storage/network targets, queue/controller audience,
runtime identities and numeric secret-version references. The temporary C23
test project and the legacy project are excluded by the C24 validator.

Set independent OAuth and signing material; never copy legacy credentials.
Require the beta HTTPS origin, exact callback/CSRF/CORS origin and host-only
Secure/HttpOnly cookie. The null cookie domain is intentional. Verify inherited
IAM and negative network/database/storage/secret access to legacy resources.
Current DNS/TLS/Host routing, direct-service URL denial and browser session
isolation must be observed on the actual target. Leave main/apex/www traffic,
cookies and identity configuration unchanged.

Choose actual capacity, log/retention/backup policies, RPO/RTO and spending
controls. Synthetic C24 values are examples, not configuration or authorization.
Validate the exact filled input with the existing offline C24 renderer, then
review provider-specific definitions. Artifact wrappers cannot be sent to a
provider API. No current provider schema, IAM grant or cloud state is attested
by local rendering.

Record the concrete authorized operations and targets separately before any
live implementation/provisioning/build/migration/restore/transfer/promotion.
For each gate retain operator, time, source/config/image/material identities,
exact targets, commands, raw observation hashes, result and cleanup. Unknown,
missing or failed evidence stops that stage. Never edit an old receipt to
change `not_run` into `passed`; add a source-bound live decision record.

## 3. Review migrations and retention

The actual Alembic head is `20261027_0021`; the legacy-era additive reference is
`20261005_0016`. The v1 additions are `0017` investigations/context, `0018` durable
research, `0019` retained evidence/answers, `0020` proposals/reservations and
`0021` retained execution/proof release. This reference does not authorize a
legacy database upgrade or imply an older application can read the v1 schema.

Review the exact offline SQL, graph, native schema and rehearsal receipt under
`migrations-20261101/`. Supported offline spans are `20260925_0013:head` and
`20261005_0016:head`. Full `base:head` offline generation is unsupported because
historical `0002` reflects live tables; its original failed attempt is retained.
Fresh `base → head` online migration passes separately. Do not use that result
to claim full offline bootstrap works. Only newly owned local synthetic databases are used by
the rehearsal. The generated SQL names no live endpoint and grants no cloud
permission. Applying it later requires reviewed v1-only targets and a compatible
operator-owned migration identity.

For a real launch, obtain a separately authorized private v1 backup and an
isolated restore; prove the chosen RPO/RTO, exact schema, counts/hashes, holds,
investigations/context, run steps/events/outbox, receipts/answers, experiment
approvals/reservations/outputs and physical proof/release history. C27's local
synthetic backup/rehearsal cannot satisfy that live gate. Never acquire or
restore legacy production backups through this runbook.

On migration error, stop activation, inspect transaction/revision state and
preserve the failure. Use a reviewed forward repair/retry after reconciling the
actual database. Do not stamp a revision without applying it. Do not downgrade
populated v1 history or discard tables to make a startup check succeed.

## 4. Order later activation by capability

The host/auth/proxy/bootstrap integration, real Cloud Tasks adapter/outbox
consumer/private endpoint and production experiment supervisor must first be
implemented and accepted in their owning components. A static export, fake
queue, preview server or synthetic operator harness is not an operational
substitute. Dispatch stays disabled until those integrations and their gates pass.

After separately authorized provisioning, establish private connectivity and
independent identity/session isolation first. Verify exact image/material bytes
and worker boot-image unique identity. Accept read-only catalogue and authorized
retained investigation/evidence access against synthetic v1 inputs before any
new research or experiment execution. Missing wiring must report unavailable.

Pause and read back the actual queue before enabling a producer; queue creation
does not imply paused state. Accept duplicate delivery, uncertain ACK, epochs,
owner revocation and shared exploration budgets on the real adapter before
research activation. Readiness flags alone do not establish adapter availability.

Before experiment activation, accept the genuine proposal hash/approval,
reservation/start one-use boundary, actual host resource readbacks, two-job
aggregate capacity, no guest network/credentials, complete process-tree cleanup,
signed termination, independent proof and narrow atomic release on the new host.
Original C23 receipts remain historical host/source evidence. Never release a
reservation based only on a clock, VM state or a queue acknowledgement.

Repeat C26's full applicable scientific/access/UI/isolation matrix on the live
candidate. Execute the separately authorized matched-model protocol and record
tokens/cost as observed, not invented zeroes. Reproduce and resolve or obtain a
documented assessment of D26-07 before external beta validation. Functional
Reload recovery is not acceptance of first-read latency or production capacity.

Promote only after an explicit release decision references all applicable
source-bound live receipts, concrete target/image/configuration identifiers,
accepted exceptions and rollback owner. No promotion is performed by C27.

## 5. Abort and drain without losing history

Abort on source/material mismatch, missing authentication, scope/owner leakage,
scientific-authority upgrade, unsupported input, unexpected legacy target,
unreconciled migration, unsafe resource/termination observation, stale health,
reservation inconsistency or loss of history/receipt integrity. A high test count
cannot override one such failure. Keep dispatch unavailable while investigating.

Use the tested backend flag profiles in the rollback receipt. Normal drain
disables new research dispatch/controller actions and synthesis and disables
new experiment approval/reservation/dispatch, while keeping the service flags required
for authorized saved status/history/evidence and cancellation. Turning every
flag off is emergency unavailability; it does not promise history routes remain
accessible during that outage. Dispatch drain does not prohibit all editing:
proposal/context editing may remain available. It is not a read-only admission
policy. Flags require the actual host to use them; a
configuration edit alone is not a live readback or a process drain.

Disable producers and new claims, pause/read back the actual research queue and
stop new experiment reservations. Leave the trusted cleanup/reconciliation path
available. Request cancellation through retained APIs; retain committed steps,
cursor/event history, outbox records, approvals, reservations, artifact bytes
and protected snapshots. Allow the active supported worker to checkpoint or
reach verified terminal cleanup; do not delete work or replay a committed step
to make a queue appear empty. Provider billing is not guaranteed exactly once.

For each experiment retain the original boot, cgroup, lease/fence and journal
binding, the physical signed packet and independent durable proof before release.
Queued/reboot/pre-packet reconstruction and uncertain start/signing/commit ACKs
remain capacity-held qualifications. Isolate the failed host and preserve its
state for supported reconciliation. No force-release operation is supplied.
Owner revocation must block publication while permitting verified cleanup.

## 6. Roll back v1 only and recover

The verified local fallback is flags/entry points off with populated v1 data
preserved, followed by the same candidate restoring authorized reads. No earlier
v1 image is declared compatible. Keep the failed v1 site unavailable until a
forward repair is accepted if no earlier compatible image has been verified.
Do not send beta traffic to legacy, share its database or restore an old schema.

Retain the actual v1 revision/image/configuration manifest and all data under
their original identities. A later alternative rollback candidate requires its
own additive-schema/history/authorization tests before use. Startup/bootstrap
must refuse missing/unreconciled stores, rather than importing legacy defaults.

Recovery requires current source/material/boot/epoch and permission checks,
supported reconciliation of uncertain work, verified retained rows/bytes,
restored history and explicit clearance of the failed stage. Resume read-only
access before producers. Re-enable research and experiments independently only
after the relevant actual gates and authorization are recorded. Record the
incident, preserved evidence, rollback/readback and cleanup; scheduler remains
paused unless the user separately resumes it.
