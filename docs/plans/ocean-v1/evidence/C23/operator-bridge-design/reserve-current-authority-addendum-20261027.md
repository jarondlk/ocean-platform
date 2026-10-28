# Retained controller transaction and reserve-only slice

Decision record for implementation after checkpoint `5a02f221`. This does not
authorize a runtime start, publication, physical proof or reservation release.
Keep C22 service/ORM/migration0020 unchanged. Use one explicitly isolated,
unmounted operator PostgreSQL database, independently restricted controller
credentials, and the exact same controller session factory in the C22 reader
service, its investigation service, inspection configuration and C23 store.
An admin factory, SET ROLE, monkeypatched ORM locks, or a second mutation
transaction is not an equivalent bridge.

## Exact read and lock privileges

The unchanged ORM selects complete model rows, so the restricted controller
needs SELECT on the current columns of these nine tables:

| Table | Reason | Additional lock privilege |
| --- | --- | --- |
| app_user | Fresh actor/status/role/identity | UPDATE(id) |
| research_investigation | Owner, lifecycle and active context head | UPDATE(id) |
| research_experiment | Owner and active proposal head/version | UPDATE(id) |
| research_context_revision | Immutable selected context bytes/hash | None |
| research_conversation | Exact investigation/conversation correlation | None |
| research_experiment_revision | Immutable proposal/environment/manifest hashes | None |
| research_experiment_approval | Exact retained application approval request | None |
| research_experiment_revision_file | Retained input file membership | None |
| research_experiment_input_blob | Exact owner-bound input bytes | None |

Prefer explicit column SELECT grants matching the frozen model column list,
so a newly added column fails closed until reviewed. No controller grant is
needed on C22 capacity/reservation/outbox for these reader methods; the existing
named C23 SQL function and its NOLOGIN owner retain their separate permissions.
The site retention fence uses `pg_advisory_xact_lock(bigint)`, not another table.

PostgreSQL requires UPDATE on at least one column for every selected table using
a row-locking clause, including SHARE/KEY SHARE. The installed SQLAlchemy
compilation of C22's `with_for_update(key_share=True)` is `FOR NO KEY UPDATE`.
[PostgreSQL SELECT privileges](https://www.postgresql.org/docs/18/sql-select.html)

UPDATE(id) is **real primary-key write privilege**, not a special lock-only
permission. The chosen minimal implementation explicitly trusts this separate
controller principal, which already owns current-admission decisions for C23
native operations. Native tests must deny writes to every other C22 column and
all direct C23 mutation. A role-specific DML-denying database trigger can harden
the three id grants later; it is not present or claimed by this decision. Do not
duplicate C22 authentication logic in a new SQL function merely to avoid these
three reviewed privileges.

Apply the grants only through explicit admin bootstrap on the configured owned
operator schema. Bootstrap is setup, never a bridge session factory. Serving,
verifier and unrelated C22 roles receive no new grants. Preserve the existing
`_check_session` role/current-user/session-user/database/schema/function checks.

## Last-callback ordering

Naively calling `reserve_in_transaction` after C22's closing gate is unsafe:
its `_controller` check invokes the store enable callback again. That callback
can change authority after the last fence.

Add a separate `reserve_after_fence_in_transaction(session, binding,
final_fence=trusted_bridge_closure)` operation. It performs `_controller`, all
strict binding validation and complete canonical parameter/SQL preparation
before the closure. The closure runs remaining bridge flag checks and its last
source/access check, then takes the closing DB fence. The store immediately
executes the already prepared named SQL statement when that closure returns.
No enable/source/access or user-supplied callback follows the closing fence.
Keep the old low-level method
unchanged and continue to describe it as lacking current C22 admission.

The closure belongs to the trusted configured bridge; requests cannot supply
it. Its final path expires ORM state, rebinds the exact configured service and
factory, calls C22 `_closing_gate(active=True)`, reads the exact retained
revision/approval/input bytes, and compares them with the prepared candidate.
Do not call `_revision` or `_context` after this closing gate: those paths call
catalogue/source resolvers. `_candidate`/`_exported` byte rechecks and fixed
environment-registry checks are local retained-data checks, not fresh source
callbacks.

## Reserve-only bridge flow

1. Explicit default-off bridge and material policy validate exact site,
   controller factory, Linux environment and pinned worker/runtime/source
   identities. Inspection remains evidence, not authority for a later effect.
2. Obtain a current retained candidate using the existing inspection flow.
   Full source materialization/verification runs between read transactions.
3. Derive stable execution/reservation IDs from site, owner and idempotency key.
   Use the real retained C22 approval and C22 metadata constructor; a temporary
   reservation-shaped object supplies only the planned ID. Never create a fake
   reservation/outbox or invoke fake dispatch.
4. Enter `store.controller_transaction()`. Repeat actor/owner/context/candidate
   checks and fresh access/flag callbacks, comparing exact retained bytes.
5. Call the new store method. After its own last enable/role/binding checks, the
   trusted closure performs the final DB authority fence and fresh byte checks.
   The SQL reserve operation takes capacity only after the C22 lock order and
   retains identity/envelope/state atomically. An exception rolls all of it back.
6. Return a private detached `RetainedExecutionIdentity` only after commit has
   returned successfully. It reports capacity retention and exact identity; its
   execution/start/publication/release/scientific authority is false. Lost commit
   acknowledgement is uncertain and may be reconciled by exact idempotent replay.

The C22 reader service uses the restricted controller factory. Native fixture
preparation uses a distinct explicitly scoped application-writer principal to
create a synthetic user/context/proposal and invoke the real C22 approve method.
The approval is authentic application authorization for that synthetic fixture,
not scientific approval or a fabricated approval-row insert. Use a real accepted
Linux descriptor for eventual worker acceptance; descriptor-only local tests
remain preparation. Assert no fake outbox/delivery, no route registration, and
no real data or existing user approval is borrowed.

## Next start/publication API boundary

These remain future phases. The current event SQL returns an identical UUID for
new insertion and exact replay. That result cannot mint fresh start authority.
The controller has no UPDATE privilege on C23 state and must not issue its own
SELECT FOR UPDATE. The reviewed minimal next-phase design instead generates a
fresh internal UUID under the actual held runtime context, confirms reserved
state/fence1 and UUID absence, then uses the existing SECURITY DEFINER locked CAS
with expected fence1. Distinct concurrent internal IDs cannot both succeed.
Only acknowledged commit, exact post-read start/fence identity and a live
one-use held-context latch can create fresh authority. Reused/external UUIDs,
exact replay, lost acknowledgement or a new controller/epoch mean reconciliation
only. A native UUID-only response by itself remains insufficient. This refinement
needs no new migration and remains outside the reserve-only implementation.

Publication must repeat current owner/context/source admission and its last
closing fence in a short transaction, binding validated output bytes and exact
start/fence identity. No database transaction remains open during runsc execution.
Cleanup/terminal recording is separate and available after revocation; it must
not depend on successful publication. Authenticated physical issuance and atomic
release remain independent gates.

## Required tests for this slice

- Default-off/exact factory/site/source/material binding and no environment or
  database discovery; no C22 route/source/ORM/migration changes.
- Late enable/access/source callbacks alter owner status, role, proposal/context
  head, approval bytes, sources or factory: no reservation; cached ORM rows cannot
  hide the mutation. No external callbacks occur after final closing checks.
- Canonical metadata and staged frozen bytes match the retained C22 approval;
  deterministic IDs/exact retry are stable and changed retry conflicts.
- Native disposable PostgreSQL uses the **actual restricted controller factory**
  for the unchanged C22 reader and the atomic reserve operation. Never substitute
  the setup/admin factory. Verify the nine read grants and only three id grants,
  deny other C22 columns and all direct C23 mutations, retain capacity on rollback,
  enforce same-owner/global capacity and no fake/real-channel promotion.
- The detached reserve receipt cannot be constructed or treated as a start,
  publication, termination proof or release capability. Future new-versus-replay
  and held-lease tests are required before adding a start API.

No DB/cloud command or grant was executed to produce this design record.
