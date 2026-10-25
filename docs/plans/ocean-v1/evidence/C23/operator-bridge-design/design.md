# C23 operator bridge and reservation-release design

Design only,2026-10-24 JST. No service, model, migration, API, database or runtime
configuration is changed by this document. C23 remains incomplete. Implement
this boundary only after the actual Linux runtime has passed independent review
and its mandatory containment/termination gates. Original receipts stay immutable.

## Audited starting point

Delivered C22 source is `66b41063a77561ad959b27eed3e9920747fd6563`, accepted by
CI39539257759. Its delivery receipt SHA256 is
`5d8caca651c6b2842f4a1708a491173cc71812942acadc2447a3c91aa9da6aa0`.
The audit receipt beside this document pins the exact files read.

- `ResearchExperimentService` accepts exact Linux environment descriptors for
  proposal persistence, but accepts only a `FakeExperimentExecutor` instance.
  `_environment(dispatch=True)` and `load_execution_envelope` reject real Linux
  dispatch. Public dispatch remains fake-only.
- Approval uses `_environment(dispatch=False)`, yet `_decision` also invokes
  `_require_enabled(dispatch=True)` between transactions. A local approval
  fixture must therefore configure the accepted fake service/flag even when
  preparing a Linux descriptor. This does not authorize real fake dispatch or
  turn a fake environment into a real one.
- The capacity singleton lock and partial unique indexes enforce one active
  reservation per owner and two global slots across every reservation whose
  state is not `released`.
- The C22 ORM guard and migration0020 trigger categorically reject NEW
  `released`, including accepted reservations. Existing native tests require
  direct SQL release to fail. They must continue to fail without a real C23 proof.
- C22 `_public` always projects `execution_performed:false` and labels any
  retained reservation a fake delivery. An actual C23 execution cannot safely
  be exposed through that unchanged public projection.

## Operator-only entry point

Add an explicit local `C23ExperimentOperatorBridge` in a new module. Do not
register a route, tool, C22 executor substitution, automatic outbox consumer or
serving worker. It requires an explicit independent site/session factory, a
trusted exact environment registry, an independently enabled operator boundary,
a verified worker configuration and the C22 source/access services. No legacy
database/cache/environment discovery or Boolean approval callback is accepted.

Proposed API:

```text
reserve_approved(request, *, current_owner) -> RetainedExecutionIdentity
load_current_envelope(execution_id, *, phase) -> VerifiedEnvelope
admit_start(execution_id, *, expected_epoch) -> one-use bound start grant
retain_validated_result(execution_id, *, expected_epoch, outputs) -> private result
record_verified_termination(execution_id, *, verified_worker_receipt) -> proof ID
release_terminated(execution_id, *, proof_id, expected_epoch) -> immutable release
```

The request binds the same expected proposal version/revision, five content
hashes and complete context identity as C22. `reserve_approved` reuses the exact
C22 owner, active context, immutable approval, environment, frozen export and
current source-policy checks. After external callbacks, refresh DB authority
with the closing gate. Reserve under the existing capacity row lock and insert
the reservation and C23 execution identity in the same transaction. Preserve
the existing owner/slot/revision indexes. Do not add a C22 fake outbox row for
a real execution; the old consumer must never receive this work.

Replays return the same reservation/execution/job IDs. Same idempotency key with
different content conflicts. An existing fake reservation/envelope is rejected;
it cannot be promoted by changing an executor, descriptor or hash. Linux work
requires a retained proposal and owner approval for the actual pinned image.

`load_current_envelope` performs all retained hash/file/approval checks, current
owner permission/status, active investigation/proposal heads and current
source/publication policy. It rebuilds the same C22 input envelope and compares
its hash to the retained reservation. The input's historical
`execution_performed:false` is not rewritten into a result assertion.

Admission is repeated immediately before start and private result retention;
the final DB authority fence occurs after external source/access callbacks.
The worker consumes a one-use grant bound to execution, epoch, envelope, image,
profile and job. Distributed start acknowledgement loss is reconciled against
the same durable job; it does not authorize another start. No claim is made
that a permission check prevents every possible future revocation atomically
across a remote runtime. Revocation after start denies publication and triggers
cleanup under the separate trusted cleanup authority.

## Minimal additive persistence

Keep migration0020 immutable. Introduce a new migration and new model module
with separate immutable identities and monotonic execution state:

1. **Execution identity/state:** exact reservation/revision/approval/owner/site,
   deterministic job ID, envelope hash, worker identity and boot ID, accepted
   image/runtime/profile/init/source hashes, current epoch and lifecycle state.
   At most one execution per reservation; a unique start intent cannot reset.
   A durable worker journal and held per-job lock serialize physical effects.
2. **Termination proof:** append-only typed record linked by exact execution/
   reservation/envelope identity and current fence. Retain actual worker/boot
   identity, outer-cgroup path and original device/inode, journal intent/final
   event hashes, cleanup sequence and observed timestamps, read-back
   `populated=0`, verified runtime deletion and original process identity pins.
   Store raw-evidence hashes and issuer/signature identity separately. A JSON
   blob, `state=stopped`, absent PID/state file, lease expiry or zero process
   list supplied by a caller is not the proof.
3. **Release ledger:** append-only unique reservation/proof association with
   exact execution/epoch/envelope and commit timestamp. It records capacity
   release, not successful execution, scientific review or publication.

New identity/proof/ledger rows reject UPDATE, DELETE and TRUNCATE, including
CASCADE. Add complete composite foreign keys where a single ID would allow
mixing owners/revisions/approvals/reservations. State transitions and epochs are
strict and monotonic; uncertain effects never reset to launchable state.
Do not delete frozen files, approval history, source holds or investigation
references when capacity is released.

## Trusted proof issuer and database privilege boundary

Physical facts come from the trusted host adapter under its exclusive durable
job lock, with exact image/runtime/profile/worker identities verified. It
collects outputs before destroying tmpfs, then kills/verifies the independently
owned outer cgroup and retains its identity until populated=0 is observed.
Normal process exit or a guest wrapper's result frame is insufficient for host
termination proof. A checksum detects corruption; it is not an issuer signature.

Register an explicit operator/worker verifier identity and pinned verification
key outside the untrusted result document. If a remote receipt is used, verify
its signature and exact canonical identity before treating it as a trusted
observation; never accept a public key that arrived in the same receipt. Keep
the signing/verifier secret and database credentials outside the scientific
image and generated analysis. Key issuance/rotation is operator configuration,
not a request field or fabricated local evidence.

The database must distinguish the serving role from the trusted proof recorder/
release role. The serving role cannot insert proofs/ledgers or call the release
function. Revoke default PUBLIC execution on security-definer functions; fix
their search path and object qualification. A narrowly privileged function may
record typed proof only after the trusted verifier has authenticated the actual
receipt. An unrestricted application database-owner role cannot provide this
separation: do not claim direct-SQL forgery resistance in that configuration.
Schema owners remain trusted and can bypass schema enforcement by changing it.

An owned disposable PostgreSQL instance may configure dedicated roles to prove
the boundary locally. Real target roles/keys must be explicitly configured and
verified before activation; GCP permission alone does not supply those values.

## Narrow reservation-guard amendment

The new migration may replace only the definition of
`ocean_research_experiment_reservation_guard`, preserving all existing identity,
delete, rollback and accepted-state guards. Add one narrowly correlated exception:

```text
if transition is nonreleased -> released:
    require immutable release ledger -> verified termination proof -> execution
    require exact OLD reservation/owner/revision/approval/envelope and epoch
    require retained revision environment kind=linux-gvisor, test_only=false
    require execution terminal/closed and trusted proof issuer accepted
    require no C22 fake outbox/delivery and no future start authority
    allow only state and updated_at to change
else:
    preserve migration0020 behavior exactly
```

Implement `release_terminated` as one transaction: acquire the established
retention/investigation/head ordering where needed, then the same global
capacity lock, reservation/execution locks and current epoch; verify the exact
immutable proof; insert the release ledger; update the reservation to released.
An identical replay returns the existing ledger. A different proof or binding
conflicts. Rollback removes both the ledger and state transition atomically.
Keep the old ORM categorical guard intact; invoke the narrow SQL function
instead of weakening generic ORM mutation. Fake accepted/uncertain reservations
remain unreleasable by this C23 path, even with a fabricated completion JSON.

Cleanup/proof/release must not require the owner's current launch permission:
the owner may be suspended or the source revoked while a job runs. They do
require trusted operator authority, the retained physical job identity, current
cleanup fence and actual proof. In contrast, start and result retention always
require fresh owner/source authority. Lease expiry grants neither cleanup proof
nor a free slot. A changed boot ID or missing cgroup remains uncertain until
the separately specified physical-termination evidence is available.

Downgrade must refuse whenever C23 execution/proof/ledger rows exist. For an
empty schema it restores the exact old guard. Operational rollback disables
new dispatch and retains evidence; it does not erase executed history.

## Public false-projection hazard

Initial actual validation must use an explicit isolated synthetic operator
site/store with C22 HTTP/tool routes unmounted/default-off. It may retain actual
C22 proposals/approvals locally, but must not publish C22's false execution
projection after a real run. Operator status uses a separate C23 result type.

If a shared serving store is later needed, an explicit reviewed C23/C25
response-contract amendment is mandatory. Until that exists, encountering a
C23 execution through the C22 public projection must fail closed, never report
that real Python was not executed. Preserve fake-only dispatch semantics and
historical receipts. This is a real compatibility gate, not permission to
silently reinterpret the existing field.

## Required native PostgreSQL and integration checks

Retain the existing C22 21 native cases and source qualifications. New migration
head assertions are intentional test supersessions, not edits to old receipts.
Use only explicitly identified owned disposable targets and random schemas.

- Verify exact model/schema/FK/index/check correspondence, empty upgrade/
  downgrade and populated downgrade refusal without data loss.
- As the serving role, attempt direct proof/ledger insertion, reservation
  release, function calls and fake completion/lease JSON. Every path must fail.
  Verify proof/history UPDATE, DELETE and TRUNCATE remain forbidden.
- Mix wrong owner, revision, approval, reservation, envelope, worker/boot,
  image/runtime/profile, epoch, journal and cgroup identity. Reject mismatches.
- Race C22 fake and C23 real reservations for one owner and three owners;
  retain one-owner/two-global capacity. Duplicate requests produce one
  execution/reservation and no fake outbox. Conflicting idempotency fails.
- Race release against new reservation using barriers and actual row locks;
  a slot becomes free only after the proven release commits. Rollback leaves
  capacity occupied. Exact replay is idempotent; altered replay conflicts.
- Lose reserve/start/proof/release acknowledgements and restart controllers.
  Reconcile stable IDs without duplicate starts, proof replacement or lease
  release. A stale fence cannot publish/release or override a live worker lock.
- Revoke user status/role, current context or source policy in the final
  callback before start and before retention. Start/publication must fail;
  trusted cleanup and proven release must still complete after revocation.
- Retain unchanged input/approval/history/source protection after release and
  after disabling experiments. Verify operator records cannot acquire fake
  public execution labels or enable a real API dispatch route.
- Bind an actual retained synthetic C22 Linux proposal through real runsc,
  sealed init, validated bytes, durable journal and proof-backed release.
  Real containment/numerical receipts remain separate from DB mock/race tests.

No real scientific review, eligible production source transfer, deployed user
approval, cloud database target or verifier key is invented by this design.
Synthetic owner approvals prove software control flow and retain explicit
experimental/unverified scientific authority.
