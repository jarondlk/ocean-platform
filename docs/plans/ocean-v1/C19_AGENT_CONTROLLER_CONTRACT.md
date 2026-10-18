# C19 exploration controller

The separate v1 controller is a synchronous, host-injected application service in
`orchestration/research_controller.py`. `ENABLE_V1_RESEARCH_CONTROLLER` defaults
to false. It does not construct a provider, call legacy Chat, expose a production
route, run arbitrary SQL or provision workers. C20 owns durable runs and concrete
frontend transport; C21 owns final synthesis and evidence presentation.

## Admission and scope

`ResearchController.execute` accepts an investigation ID, conversation ID,
explicit context revision ID and original question. The host supplies the actual
C17 investigation service, the same actual C14 catalogue instance, current
identity callback and optional C06 structured runtime/model identity. Admission
captures C17's canonical context hash and sealed snapshot. Every dispatch and
final return rechecks ownership, current permissions, retained context, current
references and catalogue policy revision. Revocation clears protected results.

Scope resolution uses a bounded whole-question EN/JA grammar for dataset counts,
quoted exact IDs, dataset coverage and explicitly registered native operations.
Unsupported or residual qualifiers require clarification. This is not general
natural-language scientific interpretation. Dataset pins restrict inventory and
tool targets. Known source product/version/method/control/protocol restrictions
remain binding; distinct incompatible pins clarify. Unsupported metadata,
relationship, table or artifact pin semantics cannot authorize exploration.
Attachments are supplementary quoted context and do not restrict the population.

Published analysis pins require C01 compatibility with the actual original
question, the exact frozen analysis scope and a unique protocol. A C13 template
cannot substitute for the question. An immutable publication pin does not permit
ad hoc recomputation. A native operation that cannot faithfully express an exact
scientific protocol remains unavailable or requires clarification.

## Actions, inventory and evidence

Deterministic `c13.inventory` runs before model-directed exploration. Pin-detail
validation is itself a counted tool attempt. The model may request seven C14
read-only tools, clarification or finish. Strict JSON rejects duplicate keys,
nonfinite values, excessive depth/size and recursive trusted envelope fields.
Actual C14 request schemas and source-owned native parameter schemas are reused.
The host forces the submitted snapshot, effective scope and current access.

C06 generations must explicitly complete before action parsing. Truncated,
refused, failed or unknown generations stop without repair. One completed but
malformed action may be repaired inside the original budget. Tool failures retain
safe machine reasons and count as attempts.

Each observation binds the context revision, canonical scope, snapshot, full
payload reference/hash, complete input manifest count/hash, semantic counts,
operation/parameter identity, availability and scientific qualifications. Dataset
count comes from the typed semantic count, never preview length or the number of
registry provenance objects. Whole inventories and aggregates are not bounded by
the default100/maximum500 listing page limits. Host evidence retains full payloads;
model context compaction bounds row/object previews while preserving mandatory
identity, scope, counts, cursor and qualification metadata. Oversized mandatory
metadata stops safely instead of dropping scientific limitations.

The current collector is in memory and checkpoints contain detached full payloads.
C20 must store those payloads durably before publishing progress and must validate
any restored state. C19's restored budget is a trusted host counter interface,
not a claim of durable step replay or observation restoration.

## Completion and stopping

Host-owned requested facts and dataset dispositions determine completion. A model
finish request cannot assert support. Coverage requires explicit known semantic
fields; unknown coverage is distinct from known zero. Operation results must
match the requested binding, scope, targets and parameters. Publication facts
require every requested table's full contiguous, nonoverlapping page coverage,
consistent content/input identities and C01 compatibility. Partial previews,
missing pages, overlapping pages and unknown totals cannot complete a table.

The default budget is180 active seconds,12 tool attempts and one malformed repair.
Time includes preflight, model/tool calls and final completion. Reservations occur
before dispatch; restored counters never reset these limits. Checkpoints occur
before and after operations, including discarded late returns and safe failures.
`finishing` is a proposal; only a successful return is a controller result. C20
owns its final publication transaction and cancel-versus-complete fencing.

Cancellation is cooperative at operation boundaries. It does not forcibly stop a
blocking provider or worker. Invalid or backwards timing stops future effects and
returns partial with `invalid_clock`; the retained elapsed value is explicitly a
last valid lower bound, not a newly measured duration. The closed final budget is
authoritative: cancellation, first deadline crossing or first clock failure during
finalization cannot produce a completed result.

## Acceptance limits

Acceptance uses TEST principals, sealed synthetic C09–C13 inputs, actual C14/C17
services, and fake structured C06 runtimes. The100000-item test uses an explicit
synthetic C14 backend and frozen submission loader; it does not establish C13
snapshot capacity or actual100000-dataset C17 storage. It verifies full counts
across preview sizes, exact ranks26/502/100000 and context-bound later-page cursors.
Synthetic publication labels and rows are test fixtures, not scientific approval.
No real provider, real-data transfer, OIDC session or cloud deployment is accepted.

Original failed iterations remain immutable in `evidence/C19`. Final acceptance,
source hashes, intentional config supersession, review and hosted delivery are
recorded separately. Existing C18 frontend sources and all legacy files are
preserved; C20/C26 must verify real transport and assembled browser recovery.
