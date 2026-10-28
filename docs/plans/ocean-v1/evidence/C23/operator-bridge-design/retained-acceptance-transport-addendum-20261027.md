# Retained acceptance application principal and source boundary

Implementation preparation only. The root operator owns live cluster, SSH,
worker, network controls, credential staging and actual acceptance evidence.

The two cases use separate new disposable SCRAM PostgreSQL clusters, databases,
schemas and role sets. The planned worker loopback endpoints are 55423 for
`scientific` and 55424 for `publication-revoked`. This does not expose a public
database or install PostgreSQL on the worker. Configuration accepts only an
explicit `postgresql+psycopg2` URL to 127.0.0.1, an `ocean_c23_*` database and the
exact distinct application/controller/verifier LOGIN names. No ambient database
URL, admin connection, SET ROLE or controller factory substitution is used.

An additional application writer credential is explicitly authorized for the
authentic synthetic C22 fixture. Bootstrap stays on the Mac. The application
role receives the existing fixture grant of SELECT, INSERT and UPDATE on
AppBase application tables **excluding every C23 EXECUTION_MODELS table**.
The harness checks actual current database, current/session role, schema and
absence of C23 table/column DML rights. This writer is trusted application
setup authority; these are real C22 writes, not a lock-only or read-only grant.
Existing controller C22 grants remain the nine-table SELECT and UPDATE(id) on
the three C22 lock heads. C23 mutation functions and the independent verifier
retain their existing restricted policies. No controller observation grant is
added for C22 reservations or outbox.

The application writer creates a new synthetic C17/C22 fixture, stores the
fixed scientific code, and invokes existing create and approve with the actual
fixture owner. It never invokes dispatch. Its engine is disposed before runtime.
C23 reserve, current start and current publication use the exact controller
factory. Proof verification and atomic capacity release use the verifier.
After runtime, a separate short application READ ONLY transaction observes C22
reservation/outbox rows and is immediately disposed.

In the revoked-publication case, the writer is reopened only after the durable
terminal exists. A short actual C22 UPDATE changes the owner from active to
suspended, the only accepted inactive AppUser status in the current CHECK
constraint. Acknowledged commit and a fresh status readback are required for the
revocation receipt. The feature flag remains true, so the subsequent current
publication denial is attributable to owner status. The writer is disposed
before publication continues. Closing, physical issuance, proof recording and
release must still complete independently of owner permission. An unknown write
acknowledgement is a failed acceptance observation and is never relabelled as a
verified revocation.

Each worker configuration and raw 32-byte Ed25519 seed must be root:root0400
inside a canonical root-private0700 parent. The configured public key is pinned
separately and must match the seed. Neither secret may be within the source
archive, attempt/export tree, rootfs, OCI layout or runtime material tree. No
credential or key enters a guest input, mount, output, public DTO or receipt.
Only the full configuration SHA is retained. Errors omit DSNs and exception
messages that could disclose connection strings.

The protected source manifest binds the current worker, aggregated profile,
trusted wrapper, harness and fixture modules. Required host modules and the
four explicit fixture modules are imported from the protected archive before
the first database access, and the full loaded-source provenance helper checks
their origins. Current admission repeats protected byte and loaded-origin
checks while the actual job lease is held. Copied synthetic software fixtures
have a separate trust scope and cannot establish actual loaded provenance.

The harness does not mark C23 complete, approve science, expose serving routes,
release uncertain capacity, acquire real datasets or alter legacy deployment.
Actual source-bound Linux/database execution and raw receipt review remain the
next gates. Unknown cleanup or transport state is retained for the root
operator; isolated resources are stopped only after exact evidence export and
identity-based cleanup verification.
