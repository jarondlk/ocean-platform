# C21 proposed integration contract

Planning draft only while C20 sourcea149239 hosted delivery is pending. This does
not select C21 or authorize work beyond the existing synthetic local boundary.
Root will finalize the implementation contract after the readiness gate.

## Separation and public actions

Keep C20's terminal records, seven actions, result:null and event cursor unchanged.
Use separate versioned C21 answer and evidence envelopes, explicit independent v1
services and default-off flags. Never generate from status/open/list/page/export.
Proposed action families:

- /research/answers/: submit, status, events, cancel, list.
- /research/evidence/: list, open, page, export.

Submit binds owner/run/input version, output locale and idempotency key. One
canonical synthesis/budget head per run segment prevents new keys/locales/versions
from resetting allowances. Separate C21 outbox/lease/cancel fences new work.
History can remain configured when generation is disabled. No legacy Chat fallback
or silently generated fixture answer is permitted.

All action/read boundaries validate current identity, owner, conversation/run,
context, retained snapshot and source policy; bounded UTF-8/finite JSON with no
unknown request fields. Page default100/max500; evidence previews are bounded and
never stand in for a result population. Public records exclude private model
journals/prompts, physical storage paths and full input manifests/tables.

## Shared internal interfaces

The store supplies a detached VerifiedEvidenceSet with a RunEvidenceAnchor:
run/input/owner/binding, effective question+hash, immutable controller result+hash,
manifest+hash, actual effective scope/scope witness, frozen ControllerLimits,
C20 final persisted budget floor, current access/policy witnesses and clock state.
Receipts bind exact operation/version/parameters, complete input identity manifest
and hash, raw payload/result hash domains, executed scope, authority, availability,
source/query completion, count denominators, page bounds and qualifications.

The store validates committed raw step requests/outcomes before projection. The
latest checkpoint alone cannot establish all evidence: known inventory_union
and prefix-only child results may require verified pure reconstruction from exact
retained inputs and ordered roots. Historical opening does not execute the active
controller or compare its new fingerprint as though it were the historical binary.
Unknown/unsupported projection versions fail explicitly.

SynthesisEngine consumes only verified host evidence, a durable journal, current
access callback and cancellation. It returns a candidate; only the store publishes
an immutable answer after final locked/fresh policy checks. The journal persists
manifest, physical reservations and raw outcomes, looks up committed results
before charging another effect and accounts for every unresolved database interval.
Absolute combined limits remain180s/12tools/14models/1repair at defaults; C20's
persisted final counters/time are the floor. Different output choices cannot grant
a fresh budget. Explicit C20 continuation is the separately granted next segment.

## Scientific rendering and citations

Proposed finite synthesis output selects/arranges trusted fact IDs, supplied
receipt aliases and exact documentary excerpt IDs. It cannot submit replacement
values, authority, completeness, scope or arbitrary relationship assertions. Host
rendering keeps exact typed values, counts/denominators, explicit partial/unresolved
work, original authority and mandatory qualifications. A structured selector is
not independent scientific verification. Citation syntax establishes traceability.

Use deterministic rendering for exact supported counts where appropriate. For
model selection, require C06 completed GenerationResult before strict bounded JSON
parsing. Unknown aliases, extra fields, unsupported relationship wording, output
limits/refusal/unknown termination and invalid repair results never publish an
answered record. At most the remaining shared malformed repair is available.
Retain exact generation metadata/raw outcomes privately for honest replay.

An optional explicit documentary provider searches only the resolved effective
question/pin scope and permitted source identities, consumes a remaining tool
attempt and returns immutable source/document hashes and access witnesses. Its
packets always have documentary authority; top-k cannot establish inventory,
coverage or totals. No configured provider means documentary search unavailable,
with no global/current legacy retriever or acquisition fallback.

## Retention and frontend

Receipts and large blobs are immutable independent-v1 storage. Snapshot protection
must complete before public ready state; lost acknowledgements remain prepared or
uncertain without compensating release. Source/ancestor legal holds and explicit
receipt attachments protect transitive evidence/snapshot dependencies. Metadata
retirement may conservatively retain bytes/references; actual physical pruning
needs its own implemented safe policy. Current withdrawal still denies disclosure
of bytes preserved under a hold. Reopening uses original retained content, never
a changed publication or another conversation's generated narrative.

C17's explicit artifact_resolver resolves retained receipt IDs and hashes; it
must independently protect older-snapshot dependencies rather than assume C17's
current snapshot reference protects every attachment. Attached receipts supplement
context and never silently restrict inventory. Cross-chat prose is not evidence.

Frontend uses separate answer/evidence clients and state. Answer cards disclose
complete/partial outcomes, citation buttons open freshly authorized retained data,
pages distinguish preview size from totals and C07 exports carry bounds/scope/
authority. Navigation preserves private drafts; account/permission/access loss
clears answers, citations and evidence views. Raw HTML is never rendered. Legacy
links stay on their own site. C26 retains assembled browser/system acceptance;
local component checks do not claim real provider/GCP/IAM/scientific approval.
