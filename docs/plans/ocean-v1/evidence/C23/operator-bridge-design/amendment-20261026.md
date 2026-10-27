# C23 retained-approval bridge: implementation split after core runtime tests

Read-only implementation audit,2026-10-26. This supplements the Oct24 design;
it changes no service, schema, migration, database, runtime or dispatch setting.
Root reports actual smoke/namespace/network containment passed on source00abd95;
resource acceptance is still in progress. Those operator fixtures remain
explicitly outside retained C22 approval/reservation authority. They do not
satisfy the C23 contract's narrow reservation-release integration gate.

## Starting constraints reconfirmed

C22 still accepts only FakeExperimentExecutor as its executor. Linux descriptors
can be retained and approved, but `_environment(dispatch=True)` and
`load_execution_envelope` reject them. `_decision('approve')` also performs the
fake dispatch-enabled check between transactions, so a synthetic retained-flow
fixture must configure the existing fake service/flag while never invoking its
dispatch method for Linux. No new public dispatch route is needed.

The exact existing capacity singleton, active-owner/slot partial unique indexes,
immutable approval/files and reservation identity must be reused. The C22 ORM
guard and migration0020 guard currently prohibit every release, including from
accepted. Keep their source files and historical receipts unchanged. Any release
exception must be an explicit new migration and a privileged, named operation.

C22 `_public` labels every reservation a fake delivery and projects no execution.
The first real bridge must therefore use a separate operator-only synthetic
site/store with HTTP/tool routes unmounted. Its C23 status DTO must not call
`_public` or `_response`. A future shared serving-store contract needs an explicit
reviewed compatibility change; this bridge does not quietly change C22 fields.

## Smallest useful API

Add `C23ExperimentOperatorBridge` in a new module, composed with an explicitly
configured matching ResearchExperimentService/exporter/investigation store.
Require a default-off trusted OperatorBoundaryConfig: exact site/store, accepted
real environment registry, worker/source/profile policy, verifier identity and
privileged recorder connection. Never discover DATABASE_URL, legacy state,
environments, credentials or verifier keys from a request or result document.

```text
inspect_approved(request, *, current_owner) -> ApprovedCandidate
reserve_approved(request, *, current_owner) -> ExecutionIdentity
load_current_envelope(execution_id, *, phase) -> VerifiedEnvelope
admit_start(execution_id, *, worker_lease, expected_fence) -> StartPermit
admit_publication(execution_id, *, worker_lease, expected_fence) -> retained hash
record_verified_termination(verified_packet) -> TerminationProofIdentity
release_terminated(execution_id, *, proof_id, expected_fence) -> ReleaseLedger
```

`inspect_approved` is the first independently implementable slice: it is read-only
and validates current owner/permissions, exact current proposal/context heads,
immutable approval request hash, all five approved hashes, frozen bytes and
trusted exact environment. Reuse C22's `_actor`, `_owned`, `_revision`,
`_expected`, `_exported`, `_environment(dispatch=False)`, `_verify` and closing
fence semantics through the explicit composed service. Reject fake descriptors.
Do not reuse the fake-only execution loader or reinterpret a recomputed hash
as a retained reservation. A candidate grants neither launch nor capacity.

Reserve only after external full/source-access callbacks and a closing DB fence.
Use the established lock order: actor/retention, investigation, proposal head,
then capacity/reservation/execution. Under the existing singleton row lock,
enforce one owner/two global slots, insert the real reservation and immutable
execution identity atomically, and create no fake outbox. A new C23 operation
identity/idempotency key belongs in new storage, not a fake C22 dispatch operation.
An existing fake reservation/outbox cannot be promoted. Duplicate exact requests
return stable IDs; changed content conflicts.

## Minimal persistence refinement

Separate changing state from immutable identity. The Oct24 design's combined
"identity/state" item must not lead to either mutable approved identity or a
supposedly immutable row whose epoch changes.

1. `research_experiment_execution`: immutable execution ID, reservation/owner,
   site, retained envelope, request/idempotency hash, deterministic job ID and
   accepted image/runtime/profile/init/adapter/source policy. Existing reservation
   identity supplies proposal/revision/approval through its immutable joins.
2. `research_experiment_execution_state`: one row with monotonic fence/state and
   one-use start identity; no terminal-to-launchable transition. Append immutable
   execution events for history. State transitions require the trusted operator.
3. `research_experiment_termination_proof`: immutable exact execution/fence,
   authenticated issuer/worker/boot, original cgroup path/device/inode, journal
   terminal sequence/head/result hashes, populated0 and delete acknowledgement,
   raw observation/packet/signature hashes and verification policy identity.
4. `research_experiment_release`: immutable unique reservation/proof association.

Use existing reservation `(id,user_id)` FK and derive its other immutable keys,
or add explicit insertion checks for duplicated keys/envelope. New proof/ledger
composite FKs must correlate the whole new execution identity. Do not add broad
C22 ORM mutation exemptions merely to support convenient FK targets.
An identity-insert guard rejects any existing fake outbox. A separate additive
outbox-insert guard should also reject an already bound real execution so the
two channels cannot be mixed by direct SQL. Original0020 code stays immutable.

New tables reject forbidden identity/history UPDATE,DELETE,TRUNCATE and cascade
loss. Downgrade refuses populated C23 tables. Empty downgrade restores the exact
old release function. Operational rollback disables starts and retains evidence.

## Necessary C23 adapter hooks and proof issuer

The current Linux adapter's admission callback receives only the envelope and
returns its hash. Its durable lease/epoch is internal, and its result document
is not an authenticated termination packet. A LinuxExecutionResult instance or
opaque JSON must not become a privileged release capability.

Root should own one narrow C23 adapter amendment: phase-aware trusted callbacks
for start/publication, with the held DurableLease, and a termination issuer hook
after durable terminal readback while that same exact job lock is still held.
Keep the old synthetic operator callback contract as an explicitly separate
compatibility path; it continues to grant no C22 authority. Publication means
making validated results available through the retained C23 store. Private worker
quarantine/audit bytes may exist before publication admission without exposure.

The start permit binds execution, exact worker/job/envelope, accepted material
policy and current fence; it cannot authorize a fresh journal or second start.
Reconciliation of lost acknowledgement performs cleanup, not replay. The DB
fence and durable journal epoch are distinct fields and must be explicitly bound.
Terminal journal reacquisition currently preserves the terminal epoch; absence,
boot change or a new journal never substitutes for the retained terminal proof.

A trusted host issuer checks the actual held lease and terminal chain, exact
accepted image/profile/runtime/init/adapter and current host boot, plus original
cgroup identity and observed emptiness/deletion. It signs a bounded canonical
packet with a key held outside image/input mounts. A verifier uses an out-of-band
registered key and expected worker/source scope, not a key supplied in that
packet. Ed25519 support is already available through pinned cryptography50.0.1;
temporary keys for an owned synthetic test are routine test setup, not invented
production authorization. A checksum alone is not issuer authentication.

Database schema owner remains trusted. A serving role cannot insert accepted
proofs/ledgers or execute the release function. A separate verifier/recorder role
can record only the verified typed packet. Functions must revoke PUBLIC execute,
use a fixed qualified search path and enforce caller privileges. Do not claim
SQL-forgery resistance while using one unrestricted owner connection for serving.

## Narrow release and revocation semantics

The new migration may replace only the release-trigger definition with a narrow
exception requiring the exact immutable proof/ledger and current closed execution
fence, real retained Linux environment, no fake outbox and no remaining start
authority. Preserve all other0020 identity/delete/rollback/accepted-state guards.
Keep the old ORM release prohibition; call a privileged SQL function instead.

Under the existing capacity lock, proof validation, immutable ledger insertion
and reservation release commit atomically. Same proof replay is idempotent;
altered replay conflicts. Rollback leaves capacity held. A lease timeout, guest
success, missing process/state file, unchecked JSON or arbitrary signed payload
does not establish physical termination.

Start/publication require fresh owner/context/source/publication-policy checks,
including callbacks followed by the closing DB fence. Cleanup and proven release
must still work after owner suspension, revoked source or disabled launch flag;
they require independent trusted cleanup/recorder authority. Frozen inputs,
approval/source holds and audit history survive release.

## Concrete file ownership and tests

- **Protocol/issuer owner:** new `schema/experiment_execution.py`,
  `orchestration/experiment_sandbox/proofs.py`, and proof tests. Exact typed packets,
  canonical signing/verification, expected-source scope, wrong-key/replay/oversize
  refusal and no release from a caller-created result object.
- **Persistence owner:** new `db/experiment_execution_models.py`, migration0021,
  disposable PostgreSQL support and native execution tests. Explicitly import new
  models for the operator/test metadata; no serving registration is needed.
- **Bridge/root owner:** new `orchestration/experiment_sandbox/operator_bridge.py`,
  an independent retained-synthetic runner and narrow Linux adapter hooks. Root
  owns final source supersessions, contract/status/handoff and actual acceptance.

Before any actual bridge launch, test callback-time owner/head/source revocation,
environment/hash/fake-outbox mismatches and exact replay. Native PostgreSQL must
test fake+real owner/global races, release-vs-reserve atomicity, lost/stale fences,
wrong proof tuples, serving-role forgery attempts, immutable history, populated
downgrade refusal and unchanged C22 fake behavior. Existing migration-head test
updates are intentional new-source changes, never altered historical receipts.

Finally run an actual synthetic C22 proposal -> immutable owner approval -> real
reservation -> held-lease Linux execution -> authenticated proof -> atomic release,
with current admission before start/publication. Its runtime receipts and native
DB races are complementary; neither substitutes for the other.

## Decisions versus authorized implementation

Local modules, typed protocols, default-off configuration, synthetic key fixtures,
new migration text and owned disposable PostgreSQL tests can proceed under the
existing implementation authorization. No real scientific review is needed for
software fixtures, and none should be fabricated. Do not ask for production
decisions merely to prepare this code.

Activation still needs an explicitly identified separate operator DB/schema and
role grants, registered worker/key/source policy, completed relevant runtime
receipts and a retained actual proposal/owner approval for the exact environment.
An owned disposable synthetic target can be configured and verified separately;
missing production targets/keys are not permission to reuse legacy credentials.
Real data/publication decisions, a shared serving-store response contract and
C24 site deployment remain separate gates. No SQL or cloud action was performed
by this audit.
