# Retained execution bridge: remaining implementation

Planning record, not implemented or accepted. The separate read-only inspection
slice now passes its local tests; it grants no reservation or execution authority.
Current C22 serving source and migration0020 remain unchanged.

## Actual existing schema

ResearchExperimentReservation has immutable identity, state and updated_at; it
has no released_at column. Both capacity indexes use state <> 'released', on
user_id and slot respectively. Slots are0/1 and the singleton capacity lock is
research_experiment_capacity.id=1. A proposal revision has one reservation and
the existing approval correlation is a four-column foreign key. Keep these
constraints, original migration0020, its reservation-insert guard and the ORM
release prohibition.

## Additive persistence and role boundary

New immutable execution identity retains reservation/owner/site, exact request
and envelope bytes/hashes, job identity, accepted environment/runtime/source
policy and idempotency key. A separate mutable execution-state row carries a
monotonic DB fence and one-use start binding. Immutable execution events record
the prepared profile, worker/boot, durable journal epoch and start permit when
they become known. DB fence and journal epoch are distinct.

An immutable termination-proof row binds the complete execution/reservation/
envelope tuple, closed fence, worker/boot, material/source/profile identities,
journal epoch/terminal sequence/head/result, original cgroup identity, populated0,
runtime delete acknowledgement, authenticated packet and verifier policy. An
immutable release ledger uniquely binds reservation and proof, retaining the
release timestamp. Composite foreign keys and insertion guards reject mixed
identities. Immutable rows reject UPDATE/DELETE/TRUNCATE/cascading loss.

Fake outbox insertion and real execution insertion must lock the same reservation
row before checking the opposite channel. This prevents a concurrent fake/real
channel race without rewriting C22's existing outbox history.

Serving connections get no new proof/release authority. A controller role gets
named reserve/start/publication/close operations. A separate verifier/recorder
role authenticates packets and records proofs/releases. SECURITY DEFINER
functions use a dedicated NOLOGIN owner, fixed search_path and schema-qualified
objects, with PUBLIC execution revoked. Migration0021 must create no production
roles or credentials; explicit isolated test/bootstrap configuration supplies
grants. Tests must exercise effective restricted roles, not a superuser claiming
to be the serving boundary. Inside SECURITY DEFINER, current_user identifies
the function owner and is insufficient to identify the calling principal.

The release operation holds the existing capacity lock, reservation and execution
state; checks exact immutable proof/closed fence/Linux descriptor/no fake outbox;
inserts the ledger and updates only reservation state/updated_at atomically. The
new trigger exception requires the correlated ledger/proof/execution tuple. Same
proof replay returns its stable ledger; changed replay conflicts. Rollback keeps
capacity. Empty downgrade restores the exact old trigger; populated C23 tables
refuse downgrade. Native PostgreSQL acceptance is mandatory.

## Runtime hooks and authenticated termination

Reserve repeats current owner/context/source checks after all callbacks, using
C22's established lock order before taking capacity. An earlier inspection
candidate is insufficient. Existing fake reservations/outboxes cannot be promoted.

Add explicit retained-operator phase hooks alongside the unchanged synthetic
callback path. Pass the actual held DurableLease, envelope and prepared profile.
Start consumes a single start identity bound to DB fence, worker/boot, durable
epoch and preceding journal head before runsc start. Unknown acknowledgement
permits reconciliation/cleanup, never another start.

Separate publication authority from cleanup and terminal recording. The current
synthetic adapter calls admission after cleanup and before journal finish;
revocation can therefore prevent terminal recording despite verified cleanup.
The retained path must finish a physically terminated outcome and issue a proof
under the same held lease even when publication is denied. Failed analysis or
malformed outputs prevent successful-result claims but do not invalidate an
independently verified cleanup observation.

Use bounded canonical, domain-separated Ed25519 packets with the already pinned
cryptography dependency. The issuer checks the actual held lease, durable
terminal readback, current boot/material/source policy and original kernel
cgroup identity/cleanup observations. Retain each packet create-only for exact
retry. A verifier uses a trusted pinned issuer/worker/source registry; keys from
the packet are not authoritative. JSON, checksums and LinuxExecutionResult alone
are insufficient. PostgreSQL storing a signature does not itself verify it:
the restricted verifier/recorder connection is the authentication boundary.

Independent cleanup authority closes further start/publication admission and
advances the DB fence. It remains available after owner suspension, source
revocation or launch disablement. Missing cgroups, changed boots, missing history
or stale leases retain capacity until an explicit separately designed proof
can establish the required facts.

## Required remaining acceptance

Native PostgreSQL must cover mixed fake/real capacity races, release versus
reserve, rollback/idempotency/fence races, role forgery, immutability and downgrade.
Then run an actual retained synthetic C22 Linux approval through reservation,
held-lease execution, authenticated proof and atomic release. No scientific
approval, production dispatch or route isolation is implied by local configuration.
VM reboot/power-loss, queued-launch cancellation and revocation episodes remain
separately identified physical gaps beyond the three passed process-crash tests.
