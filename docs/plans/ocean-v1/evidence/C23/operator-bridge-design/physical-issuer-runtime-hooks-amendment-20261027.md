# C23 held-lease runtime hooks and physical issuer

Design/review amendment, 2026-10-27. This file implements no runtime hook,
issuer, bridge, role grant or database operation. Existing synthetic operator
receipts remain unchanged. Root reports all four actual numerical fixtures pass
on source07 and the core local suite passes891 cases; neither establishes the
retained C22 reservation/approval bridge. The physical
`issue_termination_packet` entry point still fails unconditionally with
`sandbox_termination_issuer_unavailable`.

Reviewed sources: `linux_runtime.py` (`run`, `_cleanup`, `_command`,
`_require_linux_host`, `_readback`), `journal.py` (`DurableLease`, `claim`,
`_lease`, `finish`, `_load`), `operator_inspection.py`, `proofs.py`,
`schema/experiment_execution.py`, and the new execution store/model/0021 drafts.
The persistence owner is independently amending and testing those new drafts;
the agreed changes below are design dependencies, not native-test acceptance.

## The behavior the retained path must provide

The current synthetic `run` callback is `admission(envelope) -> envelope_hash`.
It receives neither the actual lease nor a phase. Its invocation after cleanup
can prevent `lease.finish` when permission is revoked. Reconciliation and the
timeout/cancellation error path have the same dependency. Normal completion
also appends `termination_verified` only after decoding the guest frame, so a
malformed frame prevents recording otherwise observed host termination.

The retained path must establish and durably record host termination regardless
of owner suspension, source revocation, disabled launch/publication flags,
analysis failure, malformed outputs or publication denial. Those conditions
can deny preparation, start or publication. They cannot authorize a launch,
erase observations or stand in for a termination proof. Failure to acquire the
actual lease, read the original cgroup, obtain the exact runtime deletion
acknowledgement, persist the terminal chain or authenticate the issuer still
retains capacity.

Use an explicit `run_retained` entry point, sharing reviewed internal runtime
operations where appropriate. Keep `run(..., admission=...)` and its synthetic
harness behavior intact. There must be no conversion from the old admission
callback, an `ApprovedCandidate`, a fake envelope or a caller-created execution
result to retained execution authority. No public route or automatic worker
consumer is added.

## Proposed exact interfaces

These are new internal trusted APIs, not request schemas or Boolean approval
callbacks. All returned capability/evidence types have private constructors,
detached immutable scalar identities and exact-type checks. Their types alone
never replace a fresh lease/DB/kernel check.

```python
adapter.run_retained(
    envelope: VerifiedEnvelope,
    profile: PreparedExecutionProfile,
    *,
    execution: RetainedExecutionIdentity,
    hooks: RetainedRuntimeHooks,
    issuer: LinuxTerminationIssuer,
    cancelled: Callable[[], bool],
) -> RetainedRunReport

class RetainedRuntimeHooks:
    def admit_preparation(self, *, context: HeldRuntimeContext) -> CurrentEnvelopeReceipt: ...
    def admit_start(self, *, context: HeldRuntimeContext) -> FreshStartPermit: ...
    def admit_publication(
        self, *, context: HeldRuntimeContext,
        terminal: DurableTerminalReference, candidate: QuarantinedResult,
    ) -> PublicationReceipt: ...
    def close_execution(
        self, *, context: HeldRuntimeContext,
        terminal: DurableTerminalReference,
    ) -> ClosedExecutionReceipt: ...
    def record_termination(
        self, *, context: HeldRuntimeContext,
        closed: ClosedExecutionReceipt, packet_bytes: bytes,
    ) -> TerminationProofReceipt: ...

issuer.issue_under_lease(
    *, context: HeldRuntimeContext,
    terminal: DurableTerminalReference,
    closed: ClosedExecutionReceipt,
    observation: HostTerminationObservation,
) -> SignedTerminationPacket
```

`HeldRuntimeContext` is created only inside the adapter's actual
`with journal.claim(job, envelope_hash) as lease` scope. It carries that exact
`DurableLease` object, the exact configured journal/adapter, retained execution
identity, verified envelope, prepared profile, worker/boot/journal identity and
the retained start-event reference when known. A guarded `require_current()`
calls the real journal's lease validation, rather than checking a copied epoch.
Before and after every hook, the adapter rechecks that lease, the expected
phase and the exact journal head for that operation. Detached snapshots remain
read evidence. A context cannot be serialized, reconstructed from JSON, reused
after its lease closes, copied into another process or accepted by another
adapter instance.

`FreshStartPermit` additionally binds the immutable DB start event/one-use
start ID, returned DB fence, worker/boot/job/envelope/profile, actual durable
epoch and pre-start journal head. It is minted only for a newly committed start
consumption. An exact DB replay returns reconciliation data, never this fresh
capability. The adapter consumes the in-process capability once, marks the
attempt before calling runsc, and performs no external callback between the
last lease/head check, durable `start_intent` and that single start attempt.
A crash, ambiguous transaction acknowledgement or failed journal append after
consumption permits cleanup only. It never resets the DB event or reissues a
fresh start permit, even if analysis probably did not begin.

Preparation admission repeats the C22 retained byte/owner/context/source checks
before runsc create. Start admission repeats them after enforcement readback,
immediately before consuming start. Both reuse the C22 lock order and closing
authority fence after all external source/access callbacks. Inspection is an
earlier snapshot and does not supply either admission. The source hash of
frozen C22 inputs, accepted worker-source hash, source-policy hash, profile-policy
hash and prepared per-job profile hash retain their distinct meanings.

`QuarantinedResult` describes bounded validated private files and their manifest,
not publication. Publication repeats current owner/context/source/publication
checks and the final DB authority fence, then atomically records the C23
publication event and its private artifact visibility reference in that same
transaction. The manifest can be prepared privately before that transaction.
An exact publication replay reconciles its existing reference. An acknowledgement
loss is resolved from the stable event ID and immutable payload before closure;
it cannot authorize a different result. Denial or unavailable publication does
not prevent `close_execution` or issuer work.

The retained return type exposes a public result reference only after successful
publication admission. It does not return quarantined output bytes through the
old synthetic `LinuxExecutionResult.outputs` field. Trusted private operator
diagnostics may remain available through a separate explicit audit path.

## Ordered lifecycle under the same actual lease

1. Verify exact trusted environment/materials and fresh preparation authority.
   Create the original outer cgroup, open and retain its directory descriptor,
   retain its device/inode and journal the creation identity before runsc create.
   Perform the existing actual enforcement/native-process readback. Acquire and
   consume the fresh start permit as above.
2. On completion, cancellation, timeout, revocation or an error after cgroup
   creation, cancel queued helper launches and append a `cleanup_intent` under
   the current lease before physical cleanup whenever the journal is healthy.
   Attempt cleanup even when journal recording fails; a failed journal prevents
   later issuance. Cleanup does not call owner/source admission. Kill the exact
   original outer group, observe it empty, execute the exact pinned runsc delete,
   kill/observe empty again and finish draining the existing control pipes.
3. Retain a trusted native observation and append `termination_verified` from
   that observation independently of guest-frame/output validity. Parse and
   validate guest bytes separately. Malformed frames or failed numerical work
   produce a bounded unsuccessful analysis disposition; they do not change a
   measured empty group into a successful scientific result.
4. Retain validated bytes only in worker-private quarantine. Build the durable
   machine result with analysis disposition, output manifest hash if valid,
   original material identity and native observation references. It contains
   no issuer packet, packet hash, closed DB fence, proof ID, release ID or
   publication assertion. Call `lease.finish`, then re-read through the same
   actual lease and extract a `DurableTerminalReference` from the validated
   finished chain. This happens before any publication callback.
5. Attempt publication admission for an eligible result. Record denial or
   callback failure only in independent operator history; do not try to append
   another event to a finished journal. Resolve an ambiguous DB publication
   transaction by its stable exact event. Then call `close_execution` using
   independent trusted cleanup authority, even after admission was denied.
   This advances the DB fence and irrevocably closes future start/publication.
6. Read back the committed exact closed DB binding/event. Under the same lease,
   the physical issuer rechecks the terminal journal and actual kernel state,
   verifies the native deletion receipt and accepted worker/material policy,
   freezes one issuance intent and signs. Verify the signed bytes against the
   independent pinned registry, retain them create-only, then call the restricted
   proof recorder with raw packet bytes. The recorder reloads DB authority and
   reverifies the signature/full expected tuple itself.
7. Capacity release can follow in its existing independent verifier transaction,
   after immutable proof retention. It holds the established capacity lock and
   correlates the exact closed fence/proof/reservation. The physical lease may
   remain held through this bounded call, but a released physical lock is never
   release evidence. The release operation needs neither launch enablement nor
   the owner's current permission. Retain the original cgroup until issuance
   and evidence retention succeed; do not delete it to manufacture absence.

All callbacks are bounded and synchronous. No DB transaction stays open while
runsc executes, analysis runs, outputs are extracted, a signature is generated
or a remote wait occurs. No SQL function acquires the filesystem lease: the
trusted controller's actual held-lease checks and the native DB fence are
complementary boundaries. A stale controller cannot use an old permit after a
new lease epoch. Trusted controllers must not perform asynchronous start or
publication operations that outlive their held context.

Post-cleanup paths must not enter the existing generic exception branch and
lose terminal recording because publication raised. Use a separate terminal
finalization path. Optional diagnostic retention failure must not overwrite an
already persisted mandatory observation; failure to persist required native
witness/journal bytes still prevents issuance. A process killed before this
path completes is reconciled from durable history and actual kernel state;
`finally` is not claimed to run after SIGKILL or power loss.

## Minimum trusted physical checks

The real issuer accepts no `TerminationClaims`, result dictionary, checksum,
guest Boolean, diagnostic JSON or lease-shaped object as the physical source.
`HostTerminationObservation` is minted only by the configured native cleanup
implementation after direct operations, with private construction and adapter/
lease binding. The issuer independently performs these checks before signing:

- Require actual Linux, real/effective UID0 and the exact configured
  `DurableExecutionJournal`. Reread the kernel boot UUID and machine identity;
  compare worker/boot with journal, retained start identity, closed DB binding
  and accepted registry. Verify `/sys/fs/cgroup` is the expected cgroup2 mount.
- Revalidate the actual live lease through `journal.require_current(lease)`:
  same journal object, registered current lease, creating PID, open descriptor,
  original private lock device/inode, current job/envelope and epoch. Read the
  trusted journal UUID from its validated identity marker through a new guarded
  journal identity accessor, rather than accepting a request-provided UUID.
- Hold the original outer-cgroup directory descriptor from creation (or reopen
  the exact retained original identity during an approved recovery). Use
  directory-relative no-follow reads. Match named path and open descriptor to
  the original device/inode, expected `/ocean-c23/{job}`, root ownership,
  protected permissions, actual cgroup2 mount and domain type. Reject missing,
  replaced, symlinked or differently mounted groups. Read bounded duplicate-free
  `cgroup.events` and require strict `populated 0` after deletion and again at
  issuance. An empty PID list, missing process or absent state file is not a
  substitute for this kernel observation.
- Retain the exact command receipt directly from the trusted launcher/capture:
  pinned runsc executable/material identity, exact configured runtime root and
  arguments ending `delete --force {job}`, direct process return code0,
  bounded stdout/stderr hashes, pipe EOF, original boot/job/cgroup and ordered
  kernel monotonic timestamps. Do not infer deletion acknowledgement from
  a guessed exit code or copy it out of `LinuxExecutionResult`. After delete,
  permit no further runsc operation or queued helper join in this job. Re-read
  the original group's emptiness; the configured watchdog cannot authorize new
  work and stops only after verified cleanup.
- Recheck the material registry against actual protected runtime/helper/source
  files, accepted image receipt/read-only materialized rootfs, sealed init and
  rerendered exact prepared profile. Keep worker source, adapter source and
  profile-policy identities distinct. Cleanup/proof does not reapply mutable
  owner publication policy; it uses the retained accepted materials and an
  independently configured cleanup/verifier trust policy. If those materials
  or the trusted verifier policy cannot be authenticated, retain capacity.
- Load the complete bounded chain under the same lease. Validate journal UUID,
  worker/boot, job/envelope, hash/sequence links, create identity, original start
  binding, cleanup intent, native termination observation and terminal event.
  Require finished head/sequence and exact stored result hash read back from
  durable storage. Derive observations and timestamps from these trusted native
  operations, never arbitrary result fields. Check the actual closed DB event
  refers to that same terminal sequence/head/result and closure lease epoch.

The existing private diagnostics are useful audit bytes but explicitly have no
execution authority. They do not yet provide the required stable native deletion
receipt, original directory handle or guarded terminal/journal identity API.
Those are implementation prerequisites, not facts supplied by this document.

## DB closure, same-boot recovery and immutable terminal binding

Coordinated with the persistence owner: preserve the immutable original start
event, its start ID, boot/journal identity, original journal epoch, prepared
profile and `preceding_journal_sha256`. That last field continues to mean the
original pre-start head; do not repurpose it as the finished head.

Add nullable `terminal_sequence` and `terminal_head_sha256` event fields, both
required for `closed` and absent for start/publication. Existing `result_sha256`
is required for `closed` and means the durable journal result hash for that kind;
for publication it remains the validated result/manifest reference. The proof
guard must compare authenticated packet terminal sequence/head/result and
closure journal epoch to the current immutable closed event, in addition to
comparing packet witness columns and the full `ClosedExecutionBinding`.

After same-boot process-crash reacquisition, a nonterminal journal has a newer
epoch. Later publication/close events may use an epoch greater than or equal to
both the original start epoch and the current DB event epoch. They retain the
same boot/journal/profile/start ID and original pre-start head. The original
start event is never edited. The actual issuer verifies continuity of the real
journal claims/events and actual held lease; SQL accepting an integer increase
does not itself establish that continuity. `ClosedExecutionBinding.journal_epoch`
is the actual closure epoch. The unchanged start-event link preserves original
start pins without expanding the current packet schema.

A terminal journal reacquisition preserves its existing terminal epoch. It
does not create another start, new finished head or a new signed observation.
Boot-change/reboot, missing history, replacement cgroup and a missing original
native receipt remain unsupported. They cannot be repaired by choosing a new
epoch, recreating a cgroup, updating boot identity or fabricating a result.

## Exact retry and avoiding the packet/journal hash cycle

The durable terminal result is finalized first and excludes the signed packet
and every packet-derived identifier. The closed DB event then references its
fixed terminal sequence/head/result. The packet subsequently signs that terminal
reference plus the exact returned closed fence/binding. Nothing later is appended
to the finished journal. DB proof/release rows can refer to the packet hash
without either earlier object referring back to those rows.

Ed25519 is deterministic for fixed bytes, but regenerating issuance timestamps
would change the bytes. Add a separate issuer-owned, bounded, private,
create-only issuance-intent record keyed by execution+closed fence. It freezes
the exact canonical unsigned packet, selected issuer/key IDs and one observed
issuance timestamp after all mandatory checks. It references the terminal and
closed DB identities; neither references this issuance intent. After a crash,
the issuer can sign only those exact frozen bytes following renewed live-lease,
boot, DB and kernel checks. It must not replace observations/timestamps or change
keys at the same issuance identity. Conflict means retain capacity and report
the conflict. Incomplete intent/packet files remain evidence of an uncertain
write; do not overwrite or silently delete them.

After signing, the existing create-only packet receipt provides stable
execution+closed-fence names and byte-exact retries. Lost proof/release
acknowledgements replay those exact bytes and deterministic DB identities. A
different packet, closed tuple, observation, key, terminal reference or fence
conflicts. A retained exact authenticated packet may be delivered to the
independent recorder again without newly asserting physical observations; first
issuance still required all native checks. Key revocation/disabling may block
new acceptance; it does not justify resigning old evidence under another key.

If the original native delete acknowledgement was not durably retained before
process death, kernel emptiness or absent runtime state alone cannot reconstruct
it. Recovery must obtain a fresh actual supported delete acknowledgement and
new native witness under the current lease, or remain uncertain. Whether runsc
delete of an already deleted job yields an acceptable acknowledgement must be
tested explicitly; no successful idempotent behavior is assumed here.

## Outstanding implementation and acceptance gates

- Implement/review the explicit retained bridge, fresh start capability and
  phase-specific hooks; freeze a source-bound profile/worker/material policy.
  The DB functions alone do not repeat current C22 admission.
- Implement/review the guarded original cgroup/native command/terminal accessors
  and physical issuer; keep the current unconditional unavailable gate until
  these are complete. The pure signing helper remains authentication machinery.
- Verify the coordinated close-event/epoch changes with effective native roles,
  terminal-reference mismatch tests, stale/changed-boot denial, exact replay,
  release locking and unchanged0020/ORM restrictions. Native tests signed with
  synthetic keys demonstrate database control flow, not physical issuance.
- Test revocation/disablement before start and at publication callbacks;
  publication must fail while mandatory host cleanup, durable terminal, closed
  fence, actual issuer proof and capacity release still complete. Test malformed
  guest frames, invalid outputs, failed science, diagnostic errors and timeout
  with the same separation.
- Test every acknowledgement-loss boundary: DB start consumption, journal start
  intent, delete observation persistence, durable finish, publication commit,
  DB close, frozen issuance intent, packet creation, proof record and release.
  Replays cannot create another start or change the authenticated bytes.
- Run one actual isolated synthetic retained C22 Linux proposal/approval through
  reservation, held-lease execution, independently authenticated physical issuer,
  proof recording and atomic release. Keep scientific authority unverified.

The current DB state graph has no reserved-to-closed cancellation path or
independent pre-cleanup `closing`/cancellation-fence state. Initial retained
support must explicitly stay within its consumed-start path and synchronous
single-host lease discipline. A revocation before consuming start, queued-launch
cancellation, remote cancellation/fencing while another controller holds the
lease, reboot and power loss need separate reviewed transitions/evidence. Do
not consume a fictitious start merely to satisfy the release schema. These
limitations retain capacity and remain visible rather than being hidden by
synthetic authority or an owner-permission bypass.
