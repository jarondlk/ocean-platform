# C21 implementation design preparation

Read-only design while C20's history amendment and final hosted delivery are
pending. This document does not select C21, freeze an implementation contract or
claim acceptance. No application source, existing receipt or pinned preparation
file is changed. Root owns final schema/API contracts and orchestration wiring;
the proposed synthesis module consumes trusted store interfaces below.

## Existing integration constraints

C20 publishes `ControllerResult` only after its lease/current-owner/context/policy
checks and final event flush. Terminal `ResearchRun` rows are immutable in ORM
and PostgreSQL; their counters, controller result and event cursor cannot be
updated later. The seven C20 HTTP actions remain `research-runs-v1`; public
`result` is literally null, and runtime synthesis is unavailable. Reopening
status/history never performs generation.

The controller closes its budget before returning. Its result's elapsed value
can be lower than C20's final database high-water, because `_settle` also charges
the final active database interval. Shared synthesis admission therefore starts
from the persisted run counters/time, not merely `ControllerResult.budget`.
Frozen limits come from that input version's execution manifest: at most180
active seconds,12 tool attempts, one malformed repair and
`tool_actions + malformed_repairs + 1` model attempts, which is14 at defaults.

C17 already supplies the trusted callback
`artifact_resolver(user, reference) -> RetainedArtifactBinding | None`.
It checks owner, artifact ID, original snapshot and immutable SHA256. Catalogue
references must match the current context snapshot; retained artifact references
may use an older snapshot. C19 currently rejects unsupported artifact-pin
semantics; C21 must not silently convert an attached receipt into a new inventory
restriction or change that completion rule.

## Minimal additive backend records and ports

Use new versioned C21 schema and additive v1 tables. Do not add prose to the
immutable C20 controller result or reopen a completed run. Suggested contracts:

```text
RunEvidenceAnchor:
  run_id, input_version, owner_id, binding: ControllerBinding
  effective_question, effective_question_sha256
  controller_result: ControllerResult, controller_result_sha256
  execution_manifest_sha256, effective_scope, scope_witness_sha256
  limits: ControllerLimits, run_budget_high_water: BudgetSnapshot
  actor_binding, catalogue_policy_revision, clock_invalid

EvidenceReceipt:
  version, receipt_id, owner_id, run_id, input_version, conversation_id
  binding, observation_id, evidence_kind, original_authority
  operation_id/version, exact_parameters, parameters_sha256
  executed_scope, complete_input_manifest_ref/count/sha256
  payload_ref/sha256, result_content_sha256, origin_step_refs
  source_completeness, query_completion, total_rows/state
  preview_count/truncation, qualifications, publication_compatibility

VerifiedEvidenceSet:
  anchor, receipts, full_payloads_by_receipt, attached_receipts
  completion, unresolved_work, effective_question_scope_witness

EvidenceStore.load_verified(run_id, input_version, current_actor)
EvidenceStore.retain(verified_candidate, protection_operation_key)
EvidenceStore.open/page/export(receipt_id, current_actor, bounded_request)
EvidenceStore.resolve_attachment(current_actor, ContextReference)
```

`RunEvidenceAnchor` is host-owned and constructed from C20/C17 records, not
accepted as authoritative client JSON. The store must validate exact binding,
current access, execution manifest, committed raw outputs and every referenced
payload hash. Reconstruct pure scope resolution using the retained effective
question, frozen context and exact committed pin-open witnesses; compare the
scope-witness hash. Do not broaden documentary search to context scope when the
question or pins narrowed the actual executed scope. Do not call the active
controller/provider again to reopen evidence: historical manifests intentionally
pin older source/runtime fingerprints. Support known projection versions or fail
with an explicit unavailable result.

Keep both complete original parameters and their semantic hash. The C19 hash
normalizes pagination; it cannot substitute for the original operation arguments.
Large inputs/tables are separate immutable bytes with bounded previews/pages.
Counts use trusted semantic values and denominators, never returned-preview rows.
Unknown totals/coverage remain unknown. Published, descriptive, documentary and
experimental evidence retain distinct kinds/qualifications; no generated summary
can change the underlying scientific approval status.

## Exact hash domains and evidence reconstruction

- `Observation.full_payload_sha256` hashes canonical C14 response JSON.
- `ResearchRunPayload.sha256` hashes the entire private replay outcome envelope,
  including accepted/discarded status. These digests are not interchangeable.
- A C21 receipt hash covers its versioned receipt content. Blob hashes cover
  exact retained payload bytes. The synthesis-pack hash covers exactly the
  evidence/preview/qualifier packets actually supplied to generation.
- Request, execution-manifest, effective-question, scientific result-content and
  input-manifest hashes retain their original separate meanings.

Read immutable committed step requests/outcomes as the primary source. A mutable
latest checkpoint is a cache and may lack valid terminal evidence. Specifically,
`inventory_union` is created after the last inventory tool commit; a deterministic
multi-root count can finish without any later model commit. C20 supplies no
`on_checkpoint` callback, so that derived payload can be absent from its stored
checkpoint. Reconstruct only the known `c19.inventory_union` algorithm from exact
child inventory receipts, ordered roots and scope, then verify its terminal
observation/ref/hash. An unsupported or inconsistent derivation is unavailable.

Explicit continuation copies only verified committed pin/inventory prefix steps;
it omits model, repair, later-turn and finish decisions. A child that only replays
that prefix can have an empty latest checkpoint despite valid terminal
observations. Resolve the copied raw steps and, when needed, immutable parent
origin chains with current authorization. Do not infer that all parent evidence
was inherited or supplied to the child. Another conversation's narrative is never
evidence; only its explicitly attached retained receipt can supplement context.
Older-snapshot attachments keep their origin and cannot establish current-run
membership, counts or publication compatibility by association.

## Durable synthesis and the remaining shared budget

Add one authoritative synthesis-budget head per C20 run segment, with a unique
run foreign key and the immutable final C20 budget as its floor. Different
idempotency keys, output locales or engine versions must not create independent
fresh allowances. A linked C20 continuation is the only separately granted run
segment. Automatic retries preserve the same budget head and operation identity.

The synthesis worker uses a separate outbox/lease/epoch and append-only attempts,
raw outcomes, controlled events and final answer. It never mutates the terminal
C20 row. Admit execution only for a permitted active context and eligible
completed/partial exploration. Cancellation, invalid clock and exhausted time
block new effects. Retained deterministic fact/limitation views can still be
opened without generating a replacement answer. C20 cancellation is terminal and
cannot cancel a later independent job; C21 requires its own explicit idempotent
cancellation action and worker fence.

```text
SynthesisJournal.bind(manifest) -> lease + absolute combined BudgetSnapshot
SynthesisJournal.lookup(step_id, request_sha256) -> committed raw outcome | None
SynthesisJournal.prepare(step_id, kind, request_sha256, request,
                         proposed_absolute_budget) -> attempt_token
SynthesisJournal.commit(attempt_token, raw_outcome, projected_state,
                        absolute_budget) -> None
SynthesisJournal.publish(candidate_answer, evidence_manifest_sha256,
                         absolute_budget) -> immutable answer_id
```

Bind the run/input/context/question, controller-result hash, evidence-pack hash,
engine/prompt/schema versions, model/runtime identity, locale and frozen limits.
Lookup committed steps before charging new effects, but always recheck current
owner/policy. Reserve and persist before each physical effect; settle database
active time through unresolved intervals after a crash. Bound provider timeout by
remaining time. Enforce absolute combined counters in PostgreSQL as well as local
code. A documentary search is a tool attempt; a model/repair attempt consumes the
same remaining model/repair allowances. The C19 repair may already be spent.
Prepared repair recovery must not consume a second repair reservation, while an
uncertain repeated provider call is another model attempt. Never claim
exactly-once provider billing.

One bounded synthesis generation plus at most the remaining permitted malformed
repair is sufficient. C06 output-limited/refused/failed/unknown generations are
retained privately and rejected before parsing; they are not repairable completed
answers. Late, cancelled or revoked returns can be retained as discarded private
outcomes but cannot publish prose. Commit loss replays committed raw generation
through pure parsing/packing, without dispatch or counter reset.

## Proposed synthesis module boundary

```text
SynthesisInput:
  verified_evidence: VerifiedEvidenceSet
  output_locale: en | ja

SynthesisPack:
  version, exact_question, binding, effective_scope
  host_completion, unresolved_work, mandatory_qualifications
  supplied_packets, supplied_receipt_ids, citation_alias_map, pack_sha256

DocumentaryProvider.search(question, binding, effective_scope,
                           permitted_input_manifest, limit, current_actor,
                           remaining_timeout) -> RetainedDocumentPackets

SynthesisEngine(runtime, model, documentary_provider=None).execute(
    input, journal, current_authorization, cancelled) -> SynthesisOutcome

SynthesisOutcome:
  status: completed | partial | unavailable | cancelled | failed
  candidate_answer?, generation_diagnostics, absolute_budget, safe_reason
```

The module packs permitted evidence and produces a candidate. Only the store's
final publication transaction makes it visible. Use deterministic rendering for
exact counts and other fully typed facts; the model cannot replace fact values,
mark unresolved work complete or invent new receipts/authority. A generated
answer's completeness remains the C19 host assessment plus successful synthesis
validation. Partial answers explicitly preserve missing facts/cohorts.

Bound rows/objects supplied to the model while keeping every necessary scope,
identity, count, unit, denominator, authority and scientific limitation. If that
mandatory metadata exceeds the context bound, stop honestly; do not truncate it.
Citation aliases reference only packets actually included after packing. Resolve
aliases to stable retained receipt IDs and audit unseen/malformed citations.
Reuse the existing citation helpers where compatible, but preserve legacy links.
Do not pass a global evidence list to a resolver if some packets were omitted.

Model prose with a valid citation is still not independently verified fact.
Prefer structured fact references rendered by the host, and explicitly typed
relationship statements whose authority comes from qualified C13 receipts.
Reject unsupported physical-identity, causal or approval claims rather than
relying only on prompts. Any remaining free-form summary is labelled and evaluated
as model narrative; tests/citation syntax cannot establish general factual
accuracy. Store the actual output locale; do not invent an ungenerated translation.

The optional documentary provider is explicit, independent-v1 and frozen-scope
bound. It returns retained document bytes/hashes, source identities, current
permission witnesses and source coverage diagnostics. Top-k is only documentary
selection and cannot establish inventory totals or missingness. Existing legacy
retrieval/global cache/regional-current-publication fallback is not an authorized
implementation of this port. Absent configuration means documentary capability
unavailable, not an automatic fallback or data acquisition.

## Storage protection, reopening and public integration

Retain receipts/payloads in independent v1 stores. A conservative initial policy
may retire metadata while retaining protected bytes/references; do not silently
release references or run production cleanup. The source investigation's legal
hold and held ancestor branches protect its answers, receipts, payloads and
snapshot dependencies transitively. Explicit receipt attachment creates a retained
dependency too. C17 only registers its own context snapshot dependency set, so
the C21 receipt store must independently protect an older attached receipt's
original snapshots; returning `RetainedArtifactBinding` alone is insufficient.

Mirror C17's conservative protection protocol: prepare an immutable registration,
add/verify all C09 snapshot references, then expose the ready receipt. A failure
or lost acknowledgement leaves a prepared/uncertain operation and never
compensates by releasing possibly committed protection. Serialize hold/retirement
and publication/dependency operations consistently. Protect ancestor/descendant
and cross-conversation attachment references before considering any physical
cleanup; fail closed if ancestry/dependencies are missing or corrupt.

Current withdrawal/access rules override history. Recheck on load, documentary
search, export, attachment resolution and final answer publication, including a
post-flush freshness check under appropriate owner/investigation/budget locks.
Withdrawn content is not public merely because a hold preserves its bytes.
If a required cited source is revoked, return a controlled unavailable view
without leaking names/counts/body. Do not silently regenerate from a changed
publication or display an older answer as current verified evidence.

Root can expose separate versioned answer and evidence action DTOs and runtime
capabilities while preserving the seven C20 actions. Answer status/events are
separate from C20 terminal event cursors. Answer/evidence reads never enqueue
generation. Public fields contain bounded answer/receipt metadata and previews,
not private raw model outputs, prompts, reasoning, storage paths or full tables.
Frontend selection calls the evidence client and keeps drafts/navigation intact;
identity/policy loss clears retained views. CSV export uses C07 serialization and
fresh researcher-level export permissions. JSON/CSV provenance carries authority,
scope, snapshot, parameters and truncation. Never execute source-returned HTML.

## Integration requirements before implementation

1. Root finalizes C20 amended hosted delivery and C21 formal readiness/selection.
2. Root/schema owner agrees exact anchor, receipt, pack, candidate and public DTO
   fields; store owner supplies the verified-loader and shared-budget journal.
3. Loader proves committed raw/derived/prefix evidence and effective scope with
   stable supported projection versions, without active controller replay.
4. Store implements per-run combined limits, cancellation/lease fencing,
   idempotency/raw-outcome replay and separate immutable answer publication.
5. Root wires explicit synthesis/documentary capabilities and APIs; frontend
   handles separate answer progress, citation opening, paging and safe exports.
6. Focused synthetic cases cover incomplete model output, unseen citations,
   exact counts versus previews, unknown coverage, publication changes, parent
   prefix/derived-union reconstruction, revocation-at-publication, hold/attachment
   retention races, lost commit, concurrent requests and exhausted shared budget.

No live provider, cloud queue/storage provisioning, real data transfer or
scientific review is needed for this local design/implementation. Those targets,
authorizations and real-world validation stay explicit external gates.
