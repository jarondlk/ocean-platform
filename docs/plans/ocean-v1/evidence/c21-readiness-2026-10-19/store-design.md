# C21 store, attachment and retirement design review

Read-only preparation on overhaul after C20 history amendment source `a149239`.
This does not select C21 or implement application changes. No tests, services,
providers, cloud operations or scientific data changes were performed.

## Verified behavior and the concrete gap

- C17 `retire_expired` serializes holds/retirement with a site advisory lock,
  locks archived investigations, and checks pending C17 operations, unretired
  descendants and held ancestors. It does not know C21 receipts, answers,
  attachment dependencies or pending C21 publication. Retirement changes metadata
  only and releases zero references, but `_owned` subsequently hides retired
  investigations. `context/get` therefore cannot reopen that origin.
- C20 history authorization ultimately calls C17 `context/get`; a C21 evidence
  loader that simply calls C20 status has the same origin-retirement problem.
- C17 artifact resolution accepts an older snapshot and records the returned
  immutable artifact SHA separately from the context snapshot. It freshly checks
  owner, exact artifact ID, original snapshot and SHA. Its current `_bindings`
  protects only the context snapshot and registered child snapshots.
- `artifact_resolver(user, reference)` has no consumer investigation, candidate
  revision, operation ID or caller session. It runs during C17 preparation while
  the target investigation may already be locked. A resolver that opens another
  write transaction and locks its source can self-deadlock or form A/B lock
  cycles. It cannot establish a reliable consumer dependency by itself.

Returning `RetainedArtifactBinding` is an authorization/hash assertion, not a
retention registration. The contract draft needs the integration below before
it can promise that another active chat keeps an old receipt reopenable.

## Conservative initial retention policy

For the first C21 delivery, retain all ready receipts/answers and their snapshot
references; perform no physical deletion or reference release. Do not overload
C17 `legal_hold` to represent automatic evidence protection: that would lose the
separate meaning and provenance of an operator's hold/unhold action.

Add explicit immutable C21 protection/dependency records. A prepared or uncertain
publication protects its exact source investigation/revision/run and complete
snapshot closure. A ready receipt or answer continues that protection. A context
revision that attaches a receipt records a consumer-to-receipt dependency; a
new receipt that consumes that attachment records receipt-to-receipt origin.
Use composite owner/binding foreign keys and RESTRICT deletion, not naked IDs.

The simplest safe initial retirement guard blocks C17 metadata retirement while
an investigation anchors any retained C21 receipt/answer, a pending/uncertain C21
operation or a protected dependency closure. This is deliberately conservative
metadata retention, not a new scientific approval or permanent user legal hold.
It avoids inventing a C21 exception that bypasses C17's retired-context access
rules. Later pruning/retirement can narrow protection only through a separately
implemented safe policy. Disabling synthesis must not disable these guards.

If product policy instead permits origin metadata retirement while an attached
receipt stays ready, that needs an explicit separate read policy: authorize the
active consumer and retained immutable receipt directly, without requiring the
origin's ordinary C17 context endpoint. Do not silently introduce that exception
while claiming existing C17 semantics. The conservative guard is recommended for
this delivery.

## Required C17 integration, after selection

Use an explicit trusted same-store integration, rather than ambient discovery:

```text
EvidenceProtection.prepare_context(session, context_operation, candidate)
EvidenceProtection.activate_context(session, operation, new_revision)
EvidenceProtection.blocks_retirement(session, investigation) -> bool/reason
EvidenceProtection.resolve_attachment(user, reference) -> RetainedArtifactBinding
```

The attachment resolver remains read-only, uses no nested row locks and does not
call back through C17 `context/get` or the complete synthesis loader. It verifies
an already-ready immutable receipt, current owner/source eligibility, exact
original snapshot, receipt hash and completed independent snapshot protection.

C17 preparation writes provisional dependency rows in its existing application
transaction once the operation has reserved its candidate revision UUID. Link
provisional rows to the existing `ResearchContextOperation`; do not require a
foreign key to a context revision that will not exist until activation. Pending
or uncertain dependency operations already block source retirement.

After C09 protection is verified, C17 activation commits the new revision and
immutable consumer dependency edges in the same application transaction. Recheck
receipt readiness/hash/current access before activation. A stale head conflicts
without removing possible protection. Retry uses the same operation and edges.
Detaching later does not erase dependencies of older retained revisions.

C17 `retire_expired`, including dry-run eligibility, calls the same-session guard
under its existing retention lock before marking candidates retired. Add a
migration-level retirement backstop so another C17 service instance, disabled
C21 flag, or direct SQL cannot retire a protected origin. A guard is protection,
not cleanup; do not add release-on-rollback compensation.

The callback must be wired for administrative retention independently of new
synthesis dispatch flags. If the explicit guard is unavailable or dependency
state is missing/corrupt, retain conservatively. A database backstop alone is
insufficient for accurate dry-run counts, but prevents actual broken retirement.
These are intentional C17 source supersessions requiring updated source-bound
regression evidence; original C17/C20 receipts remain immutable.

## Protection protocol and lock order

1. Under the application transaction, acquire the current owner row using
   PostgreSQL NO KEY UPDATE, then the existing site retention advisory lock,
   then all affected investigation rows in deterministic UUID order. Check owner,
   origin/consumer lifecycle, hold ancestry, existing dependency graph and exact
   receipt inputs; persist immutable prepared protection state and commit.
2. Outside the application transaction, register and verify every C09 reference
   with deterministic keys derived from site, protection operation/receipt and
   dependency snapshot. Include the old receipt's own snapshot and registered
   children, documentary snapshots and transitive receipt dependencies.
3. Reacquire the same lock order, recheck all witnesses and protection, and
   atomically activate receipt/dependency/publication state. Flush and recheck
   current source policy before making content public.

C17 context prepare/activation and hold/retirement integration must follow that
order before taking investigation locks. Never acquire the advisory lock for
first time inside a callback invoked after a target row lock. Owner NO KEY UPDATE
also permits C17 audit foreign-key KEY SHARE checks, avoiding the owner/investigation
cycle considered in C20. Resolver calls inside C17 remain ordinary reads.

A SQL retirement trigger must not first acquire a site advisory lock after the
UPDATE already owns an investigation row: that reverses the order. It checks
existing prepared/ready protection. Publication preparation itself locks the
source investigation before inserting protection, so retirement winning first
causes preparation to reject the retired origin; preparation winning first
causes retirement to observe protection and refuse. Verify this exact wait/commit
interleaving on disposable PostgreSQL during implementation; do not infer it from
SQLite. Shared site serialization covers supported service operations, while the
trigger is the final raw-SQL backstop.

C09 add-reference acknowledgement loss leaves prepared/uncertain protection.
Reconcile exact deterministic keys and snapshot IDs before exposing ready state.
Never release a reference because the caller saw an exception. Holds and
attachments preserve bytes; current withdrawal still overrides disclosure.

## Dependency graph and reopening

Use an immutable receipt/revision graph, not an investigation-level DAG. A result
from A can be attached to B, then B's later result attached to a later A revision;
that is legitimate temporal provenance even though investigation labels form a
cycle. New edges may point only to already-ready immutable receipts. Reject
self/forward references and malformed receipt cycles with bounded graph traversal;
missing nodes, owner mismatch or unbounded traversal retain protection and fail
closed. Traverse C17 branch ancestry separately for legal-hold inheritance.

On list/open/page/export/attachment resolution/final answer publication, recheck
fresh owner permissions, exact source binding, receipt/payload hashes, dependency
readiness, all required original snapshot registrations/lifecycle and current
catalogue policy. Export additionally requires current export permission. Never
substitute a newer publication. If any required retained dependency is revoked,
return controlled unavailable without leaking protected body, names or counts.
An attachment remains supplementary evidence and does not alter inventory scope.
Do not recurse from resolver to C17, back to resolver, to authorize the same graph.

## Verified C20 extraction requirements

The loader should produce the draft's host-owned RunEvidenceAnchor from terminal
C20 rows and immutable journals, without executing ResearchController again:

- Require exact owner/run/investigation/conversation/revision/snapshot/hash and
  requested input version equal to the run's terminal input version. Old
  clarification input versions have journal/input history but no independently
  retained accepted terminal ControllerResult; do not manufacture one.
- Parse the actual persisted `controller_result_json` and compare binding,
  effective question/input history, immutable manifest and their separate hashes.
  Missing actual result is explicit unavailable for synthesis. Mutable latest
  checkpoint JSON is not proof of accepted final evidence.
- Use C20 persisted active/call/repair counters as the budget floor, including
  database-time high-water and invalid-clock reason; the returned result budget
  can be lower. Cancelled/invalid/exhausted states admit no new synthesis effects.
- Validate every committed Step request hash and retained replay-envelope hash;
  only accepted successful tool outcomes can support scientific receipts.
  Rejected/discarded/incomplete model/tool bytes remain private diagnostics.
  Replay envelope SHA is not the canonical C14 response SHA or result-content SHA.
- Decode supported replay/projection versions and logical step grammar, with
  numeric pin/inventory/turn/repair ordering. Neither lexicographic step order nor
  UUID/timestamp ordering establishes controller execution order. Validate
  expected pin and inventory requests, and typed model decisions when needed to
  establish later tool ordering/arguments. Never expose private model prompts.
- Rebuild pin witnesses and `resolve_scope` from exact committed pin opens,
  terminal effective question and frozen context; check actual effective scope,
  requested facts and scope-witness SHA. Apply `validate_action` to recover exact
  trusted C14 envelope arguments. Preserve complete original parameters alongside
  `scientific_parameters_hash`, which deliberately omits outer limit/offset.
- Reproject exact accepted C14 bodies with the known pure ObservationCollector
  implementation and compare terminal observation identity, full-payload hash,
  counts/denominators, input IDs/hash, authority, qualifications and completion.
  Preserve semantic unknowns and exact-input manifests independently of previews.
- Reconstruct `c19.inventory_union` only from complete accepted child inventory
  bodies, ordered roots and executed scope, then compare the terminal derived
  observation/ref/hash. It may be absent from C20's latest checkpoint because no
  later checkpoint captured that pure derivation.
- A prefix-only continuation can have an empty checkpoint and copied committed
  pin/inventory steps with no local physical Attempt row. Recognize only that
  supported copy path; verify exact parent manifest, request/outcome hashes,
  immutable parent chain and current authorization. Do not require a local attempt
  for this valid reuse or infer that later parent observations were inherited.
- Do not compare a reopened run against the current controller source fingerprint
  as if it were the historical binary. Verify retained version/configuration
  claims against explicitly supported historical projection implementations;
  unsupported versions fail with a controlled unavailable result.

## Concrete implementation gates

Before C21 acceptance, cover source-retire versus prepared/ready receipt,
attach/activation versus source retirement, old-snapshot attachment protection,
source/ancestor holds, acknowledgement loss/reconciliation, self-source resolver
without nested locking, legitimate A/B temporal dependency chains, corrupt
cycles, revoked dependencies, disabled-dispatch retention, exact raw/union/prefix
extraction and final-publication withdrawal. Use synthetic sealed sources and
actual disposable PostgreSQL for locks/triggers. No live resource is needed.

## Reviewed source pins

- `docs/plans/ocean-v1/evidence/c21-readiness-2026-10-19/design.md`: `945d4c9e395ba063167ac33b5723ca638e4b3f9285b5c428c72af9823c81793d`
- `docs/plans/ocean-v1/evidence/c21-readiness-2026-10-19/contract-draft.md`: `80ea504ddbfc125097382d54426dd78ed91ca73a4379e7931e893bcc075348e9`
- `orchestration/investigations.py`: `e19bb6c27cdfb458c061940de53b5754a012d995dc0d136eb855ba3df0a867f3`
- `orchestration/research_runs.py`: `11f62de141f07c04a0a9bf736a3875154dab5ab438d4d354ea4c634ad15b8b0b`
- `orchestration/research_controller.py`: `3b612ccec487ea771357c04b89c9bf90f51a78314242d61fec8b0e1f2abbc2d0`
- `orchestration/research_controller_observations.py`: `e3aeff8f74aa25997ebd1e000ddba490326bde6e908509fc212627379b71b81d`
- `orchestration/research_controller_scope.py`: `ef467081034801df20c49b94ffd0132e461c7f602bfcbeddda7d8044f8e14351`
- `schema/research_controller.py`: `af4e1091b11c7affa6d0f1577582d6b4261d9cf9ace9b745312d756af117d634`
- `db/app_models.py`: `6b2c59e854537a02e2fd7c3f0a85aac4389793cfca832c0fb71e1315d6c4fe2d`
- `ingestion/catalogue_snapshot.py`: `450669acc6bc09a31532e101f9af38a2dee22d57053dd1b0b1e5f23ca892cec4`
