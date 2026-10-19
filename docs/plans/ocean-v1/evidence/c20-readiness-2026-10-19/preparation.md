# C20 preparation while C19 hosted delivery is pending

This is read-only design preparation, not C20 selection, implementation or
acceptance. Three existing agents inspected C19, C18, C17 and C04 interfaces.
The preliminary audit reconciles36 formal entries/34paths and87 C19 transitive
test pins. Final selection must refresh after C19 delivery is committed/pushed.

## Replay and budgets

Counter-only restoration cannot recover C19 execution. Prefer a host-owned,
versioned replay journal with stable logical IDs for pins, inventory, model turns,
tool actions and repair reservations. Separate logical position from charged
physical attempts. Replay committed exact raw tool/C06 outcomes through the
existing pure projection/parser without another dispatch or reservation. Preserve
failed/discarded attempts; an uncertain uncommitted retry is a new charged attempt.

Persist canonical request hashes, frozen C17 context and controller/model/limits
versions. Model diagnostics alone cannot replay malformed/incomplete decisions:
retain exact content, termination, timing and nullable usage privately. Validate
committed payload hashes/configuration before reuse. Reconstruct and compare
scope witnesses, facts, inventory and observation order; current owner and source
policy remain authoritative. Saved authorization never grants present access.

Committed lookup must precede new-effect budget admission. At12 actions or180
seconds, permitted committed evidence must remain recoverable without outbound
calls. Repair reservations need stable keys so malformed-output replay does not
spend the one repair again. Terminal redelivery returns the stored terminal run
after current checks rather than executing the controller again.

Persist active time in database time, with lease epochs fencing every commit.
Never restore a process-monotonic timestamp on another worker. Recovery must
conservatively charge unresolved active intervals/reservations; queue waiting and
durable clarification/approval pauses do not consume active time. Lease expiry
does not prove an old model call stopped. If pending time cannot be bounded,
stop partial rather than inventing unused time. A repeated uncommitted model call
may bill again. Commit observations/payloads/checkpoints before public progress;
terminal publication requires the actual returned C19 result, not `finishing`.

## Persistence and dispatch

Add v1-only run, immutable input history, public event, private step/attempt,
checkpoint and outbox records through additive migration. Bind owner,
investigation, conversation and context revision coherently at database and
service boundaries. Worker service identity is separate from a fresh owner
principal loaded from the explicit v1 store. External tool/model calls occur
outside transactions. Lock/fence final cancellation against completion.

An at-least-once queue uses stable delivery IDs, transactional outbox and leases.
Outbox send failure after queue acceptance may redeliver; committed steps remain
idempotent. Local fake dispatch and disposable PostgreSQL prove application
invariants. Actual Cloud Tasks/private Cloud Run configuration is a later external
gate and does not authorize provisioning resources here.

## Frontend and API

Use fixed same-origin POST endpoints `/research/runs/submit`, `status`, `events`,
`cancel`, `clarify`, `continue`, plus auxiliary `list` for owner/conversation run
discovery. Submission sends IDs/expected snapshot+hash and question; the server
loads canonical C17 scope/refs. Mutation keys bind exact owner/request hashes.
Clarification retains immutable input history and a current clarification ID.
Continuation is an explicit linked run on the frozen binding; distinguish its
deliberately granted segment from automatic retry of an existing budget.

Runtime bootstrap needs an explicit trusted execution capability; absence stays
unavailable. Distinguish owner read APIs from new dispatch enablement so disabling
dispatch preserves status/history/cancellation. Fixture injection remains a
separate explicit development dependency. Add awaiting-approval status/event but
keep experiment approval unavailable until later components.

Keep event high water separate from the last locally merged cursor. On reload,
discover runs and backfill consecutive events; status cannot replace activity
with a truncated tail. Preserve exact mutation intents/keys in the current
verified account/permission-revision-bound memory across lost acknowledgements.
Block conflicting uncertain writes. On full reload, discover committed work
before resubmit; a never-committed in-memory draft cannot be reconstructed.
No private history or question is introduced into persistent browser storage.

Identity/permission changes clear cached runs/events/drafts/intents and discard
stale responses. Aborting HTTP polling does not cancel durable execution; only
the cancel action requests it. Network errors never select fixtures or legacy
Chat. C20 public progress/result completion must not fabricate C21 narrative or
retained synthesis artifacts; normal controller completion can keep `result:null`.
