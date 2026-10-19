# C20 durable execution contract

This is the separate-v1 application contract. Local acceptance uses sealed
synthetic scientific snapshots, TEST principals, a private application store and
an explicitly supplied fake queue/model. A real Cloud Tasks adapter, private
Cloud Run target, service identity, secrets and deployment configuration are
external gates. No cloud resource or scientific approval is created here.

## Identity and frozen context

Every run belongs to one owner, investigation, conversation and C17 context
revision. Composite database constraints bind these identities and the exact
snapshot/payload hashes. Submission accepts IDs, expected hashes, question and a
UUID mutation key. The server loads canonical scope, attachments and pins from
C17. Editing the current context head does not rebind an older run; refreshing
scientific sources creates a separate branch.

Both chat:use and data:read are required. The run store reloads the principal from
the explicit v1 application database. An administrator cannot read another
owner's private run. The worker accepts a retained run/delivery identity, obtains
the fresh owner separately and validates the controller's actual store/catalogue
wiring. A queue service identity is not an owner principal. Current source policy,
withdrawal, context resolution and the immutable execution manifest apply to
replay, history and final publication. Revoked history is withheld conservatively.

## Public HTTP and browser recovery

Version research-runs-v1 exposes seven fixed same-origin POST actions under
/research/runs/: submit, status, events, cancel, clarify, continue and list.
Unknown actions, experiment approval, client owner/scope/budget fields, ambiguous
JSON, nonfinite values and oversized streamed requests are rejected. Requests
are bounded at64KiB; questions/clarification answers at8000 Unicode characters
and32000 UTF-8 bytes. Event cursors are nonnegative JavaScript-safe integers;
pages accept1–500 items and history pages also obey an8MiB server byte bound.

Run snapshots contain activity=[] and event_cursor=0, plus the separate committed
latest_event_cursor. Consecutive event pages advance only the browser's merged
cursor. Status cannot erase accepted activity or replace the immutable context.
The browser first discovers owner/conversation runs, then backfills events and
polls active work. Partial backfill is visible. Aborting a request stops browser
waiting; it does not cancel durable execution.

Uncertain mutations retain their exact request/key in account/permission-bound
memory and block conflicting writes. Identity/revision changes clear protected
state; stale responses cannot restore it. A hard reload discovers committed
server history, but cannot reconstruct a never-committed memory-only draft. No
private question/history enters persistent browser storage. Development fixture
injection is explicit; HTTP failure never selects fixtures or legacy Chat.

## Transactions, leases and replay

Creation commits the run, initial input, first public event and outbox row in one
transaction. Mutation keys are unique per owner and bind the exact canonical
operation/request; a changed retry conflicts. Inputs, public events, attempts,
execution manifests and retained outcome payloads are immutable. Committed steps
cannot be rewritten. Database and ORM guards prevent identity changes, budget or
version rollback and terminal mutation. Populated execution storage cannot be
downgraded or truncated.

Outbox delivery is at least once. A queue may accept a request while its
acknowledgement is lost; retry can send the same retained delivery identity again.
Only one live lease epoch can publish. Each physical tool/model attempt is
reserved durably before dispatch. External controller calls occur outside
application transactions. The exact raw outcome, payload hash, checkpoint and
controlled public progress event commit together under that epoch before progress
is exposed. An expired worker cannot commit a late result.

Replay uses stable logical step IDs and a versioned controller/model/configuration
manifest. It validates raw payload hashes and reconstructed projections against
the frozen context and current access. Committed lookup precedes new-effect
budget admission, so evidence remains recoverable at the limit without another
call or charge. An uncertain uncommitted physical call may repeat and bill again;
its earlier reservation remains charged. A prepared pure repair reservation does
not spend the one repair twice. This is not an exactly-once billing claim.
Model reservations represent C06 runtime invocations; its separately bounded
adapter retries remain possible within an invocation.

## Budget and transitions

The existing180 active seconds,12 tool attempts and one malformed-output repair
remain bounded. Database time conservatively charges unresolved active intervals
through recovery, saturating at the exhausted180000ms high water. Lease expiry
does not prove an RPC stopped. Backwards clock observations stop execution
conservatively. Queue waiting and durable clarification/approval pauses do not
consume active execution time.

| Transition | Retained behavior |
|---|---|
| queued → running | Fresh authorization, active investigation and one fenced lease; no duplicate started event on recovery. |
| running → awaiting_clarification | Immutable original question and a current clarification UUID; a full effective replacement question resumes on the same binding and budget. |
| running → completed/partial/failed | Only the actual C19 return can propose the outcome. Final publication locks the run/investigation, flushes the event and rechecks current access/policy. |
| cancellable → cancelled | Cancellation fences the current epoch under the same lock as completion. Prior observations remain retained; an already committed terminal outcome is preserved. An in-flight RPC may still return, but cannot publish. |
| partial/failed/cancelled → linked child | Explicit continuation creates a new run/segment on the same frozen binding. It may reuse verified pre-model pin/inventory outcomes; parent turn/model/repair/finish decisions are not replayed into the child. |
| awaiting_approval | Typed reserved wait only; C20 has no experiment approval endpoint or claim that an experimental process has stopped. |

## Exposure and later components

ENABLE_V1_RESEARCH_RUNS and ENABLE_V1_RESEARCH_DISPATCH default off. An actual
matching service plus the trusted runtime research_runs capability is also
required. Disabling dispatch/controller prevents new work and claims while
authorized status/events/list/cancel remain available with RUNS enabled. Existing
records are retained. No ambient store, legacy credentials or model is discovered.

Completed means the requested exploration finished. Production result is null;
C20 does not fabricate a C21 answer, citation artifact or scientific review.
Terminal runs are immutable, so C21 must add separately retained answer/evidence
records and explicit synthesis accounting. C26 owns assembled browser acceptance;
C20 checks the actual HTTP/TypeScript wire and presentation boundaries.
