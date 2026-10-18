# C17 investigation persistence contract

C17 persists private investigation/conversation metadata and immutable context in
application storage. The host explicitly supplies an independent v1 session
factory, `v1:` site identity, C14 service, C09 store and exact scientific snapshot
registrations. There is no ambient database fallback, legacy-history lookup,
model call, agent controller, execution, sharing or UI. Research remains unavailable
until C18 integrates its interface. Executable history arrives through C20/C21;
conversation responses explicitly say `unavailable_until_c20_c21`.

## Storage and migration

Four additive `AppBase` tables retain investigations, separate conversation IDs,
append-only context revisions and durable prepared operations. No corpus-table FK
is introduced. Owner IDs reference `AppUser` with RESTRICT. Composite foreign keys
bind heads, predecessors, creators and operations to the correct investigation and
owner. Metadata uses optimistic versions; context changes require an exact head.
Refresh predecessors preserve both investigation and immutable revision identities.

Migration `20261018_0017` follows `20261005_0016`; older migrations are unchanged.
PostgreSQL guards reject revision updates/deletes, preparation/identity rewrites
and truncation. ORM events protect corresponding SQLite fixture operations.
Canonical JSON/hash matching is checked by the service; SQL constraints also
enforce exact lowercase64hex hash shape. Downgrade locks the four tables and refuses
populated history. Disabling the feature is the rollout rollback; rows/references
are preserved. Actual migration acceptance uses only a guarded disposable database.

## Authenticated operations

All fourteen recognized routes are exact POST operations beneath
`/research/investigations/`, require existing `data:read`, and default off through
`ENABLE_V1_INVESTIGATIONS`. A configured `InvestigationService` is required.
Researcher/admin qualify; admin retains the private owner predicate. Every service
transaction rechecks current database role, status, account type, provider, email
and permissions against the trusted current principal. Other-owner and missing
private records return the same404. Historical reads recheck current catalogue
access and withhold protected labels/content.

| Operation | Contract |
|---|---|
| create/list/get | Named private investigation, exact snapshot and C08 scope; bounded owner-only UUID keyset paging |
| rename/archive | Expected metadata version and idempotency key; archive can be explicitly undone while retained |
| conversations/create/list/get/rename | Separate persistent names/IDs; no transcript import or implicit narrative evidence |
| context/get | Current or explicit historical immutable revision belonging to the investigation |
| context/change | Expected revision plus explicit attach/detach/pin/unpin/scope operation |
| refresh | New branch from an exact predecessor revision, requested new snapshot and name |
| operations/get/retry | Owner-only status and exact prepared-operation recovery |

Names are bounded200-character visible text; UUIDs and snapshot hashes are strict.
Request objects reject extra fields, nonfinite values, duplicate keys and invalid
UTF-8. Body size is enforced during streaming at262144bytes; oversized tails are
not buffered. Bounded body caching preserves FastAPI parsing. Whole service work,
transaction release and JSON encoding occur on the worker; cancellation cannot
publish a result after its checkpoint. Validation/errors never echo raw requests,
database messages or private labels. Public input cannot supply owner, role,
authority, trusted names, access revisions or artifact hashes.

## Context and evidence

Canonical C08 `scope`, `attachments[]` and `pins[]` are distinct. Attaching makes
context available without excluding other eligible data. Pins record explicit
restrictions; they are not approximated as source enable flags. Each list is
bounded256 references. Catalogue references carry canonical object ID plus exact
snapshot and are resolved through current C14 policy. Scope changes and removals
can retain explicit unresolved references; they do not silently erase history.

Artifact references require a separately configured trusted resolver returning a
fresh owner/current-access binding to exact ID, snapshot and SHA256. The first
binding is retained immutably; later hash disagreement fails unavailable.
Unconfigured artifact capability is explicitly unavailable. No URI/path, legacy
interaction or another chat's generated narrative is opened or promoted to evidence.
C21 owns actual artifact generation/storage integration.

Refresh creates a new investigation linked to the exact predecessor. It rechecks
catalogue references against the requested snapshot, retains unresolved IDs and
never guesses replacements or adopts latest implicitly. Retained artifact bindings
keep their original snapshot/hash. It copies no conversation narrative. Original
context bytes/revisions remain unchanged even after withdrawal denies current use.

`load_for_submission` returns an explicit immutable revision/snapshot/hash for one
owned conversation after fresh access checks. It never substitutes the latest
head. Any unresolved attachment or pin blocks submission until resolved or removed.
C20 must persist that binding with its later run request; C17 enqueues nothing.

## Cross-store commit and recovery

Every context mutation commits a prepared application operation first, containing
owner-scoped idempotency key, exact request/hash, expected head, reserved candidate
revision, candidate JSON and complete dependency bindings. Reusing a key with a
different request conflicts. The operation then adds independent C09 references
for the exact scientific index and every distinct child snapshot. Same-snapshot
revisions reuse stable investigation/snapshot dependency names; immutable operation
rows retain every candidate's binding set.

Activation locks the operation and investigation, rechecks current access, retained
bindings, active state and expected head, then inserts the immutable revision,
advances the head, completes the operation and writes its audit in one transaction.
Concurrent candidates cannot silently merge or overwrite a winner. Committed
replays verify stored revision JSON, SHA and snapshot just like historical reads.
Metadata replay recovers the original committed result, including conversation ID,
after current ownership/access validation.

PostgreSQL and C09 are separate transactions. Partial registration, ledger capacity
failure and uncertain commit acknowledgement retain protection and a recoverable
operation identity; no compensating release is attempted. Retrying the same key
or operation inspects/reuses the exact candidate. A trusted reconciliation method
observes or retries bindings and explicitly exposes reference release as
unavailable/conservative retention. Physical deletion and automatic orphan release
are not implemented. C09's4MiB control/audit ledger remains a bounded local storage
limit; saturation returns pending/unavailable without advancing the head.

## Retention and operational limits

Trusted `retention:manage` operators may place metadata-only holds across owners
without gaining private content reads. Logical retirement requires an explicit
duration and defaults to dry-run. Only expired archived, unheld records without
active branches or pending operations qualify. Ancestor holds also protect branches.
PostgreSQL transaction advisory locking for the explicit v1 site coordinates hold
and retirement ordering; refresh coordinates through the predecessor row lock.
Conversation writes require active state and update parent activity. Counts report
logical retirement separately from zero physical deletions/reference releases.
No shared C09 hold is cleared, and existing C03 chat cleanup is unchanged.

Local synthetic evidence does not establish real OIDC enrollment, approved real
data/scientific authority, production capacity/retention policy, target migrations
or live independent-site IAM/network isolation. Cloud configuration, provisioning
and deployment remain separate required gates. See the [handoff](handoffs/C17.md).
