# C19 preliminary readiness and interface audit

Recorded 2026-10-18 against overhaul `78a10a0c17cc29d1fa46498bf7df3c0d1be6e882`.
This is a pending, read-only prerequisite audit. C18 implementation/browser
verification is active in the parent thread; C19 remains Not started. The parent
must finish C18 source checkpoint, exact-source hosted CI and delivery, then
refresh readiness before selecting C19 under the user's sequential authorization.
No application test, model/provider, service, source edit or Git mutation was
performed for this audit. Only this readiness directory was created.

## Prerequisite evidence

The formal graph, component specification and PROMPTS agree on C01, C06, C14 and
C17. The audit read the component specification, matching prompt, prerequisite
handoffs, plan/decisions, acceptance map, site boundary, UX brief and actual
interfaces. Historical no-advance/commit restrictions in component prompts are
superseded by the user's standing sequential/commit/push authorization; they do
not authorize external providers, transfers or deployment.

[pending-verification.json](pending-verification.json) reconciles **59 formal
source entries / 52 unique paths**. It verifies original sorted path/hash
aggregates and records every intentional later accepted replacement. The
current union aggregate is
`12df27faa26b7936d1b4b1d278bc72934aff66184dd254243dcd1fd7c7c8c298`.
No unexplained source drift remains. All 19 C17 accepted files and the four C18
client/state files remain unchanged. Original receipts are read and pinned;
none was rewritten.

C01's original receipt is historical: the C01/C02 delivery audit corrected
nullable instrument aliases and subsequent accepted C06/API integrations supply
the current source. C06's 16-file receipt retains 15 exact original files plus
the later accepted API registration changes. C14 retains its 11 core service/tool
files plus accepted auth/main/config additions through C17. C17's 19 files match
its original accepted source exactly.

Reused source-bound hosted receipts confirm:

| Component | Source | Accepted hosted evidence |
| --- | --- | --- |
| C06 | `27d76c96aa093e4e77853496c826780a26a5f66a` | Run 38667543787 succeeded; runtime/consumer and actual PostgreSQL gates recorded |
| C14 | `19ba9110206dacb061c23f8e6dd7422be4b2adb1` | Run 38916279621 succeeded; 274 new cases include actual tool/API parity and 100,000-object navigation |
| C17 | `39bb811d1053c9dfb4b700f8524162800092aa44` | Run 39101652175 succeeded; 4,178 backend, 187 actual PostgreSQL including 60 C17 cases, both frontends/builds |

For each, original local receipt pins match delivery, Git source bytes match
the accepted map, and the source commit is an ancestor of the current checkout.
These are reused immutable receipts, without a new network CI query or rerun.
The latest C17 delivery is `78a10a0`; C18 final delivery is still pending.

## Actual interfaces available to C19

- `model_runtime.ModelRuntime.structured_chat_result(model, prompt, schema,
  max_output_tokens, timeout)` returns frozen C06 `GenerationResult`. Only
  `require_completed()` releases completed content. `output_limited`, refused,
  failed and unknown outcomes retain safe metadata and cannot become successful
  actions. Provider/model, elapsed time and available usage are already recorded.
  C06 supplies this provider-independent structured-generation boundary; **a
  dedicated exploration action schema does not yet exist** and belongs to C19.
- `InvestigationService.load_for_submission(investigation_id, conversation_id,
  revision_id, user)` validates the explicit owner-private revision, current
  principal and current reference access. It returns snapshot ID, revision ID,
  payload SHA256 and canonical context. Missing/withdrawn references fail closed.
  Capture this before any model/tool action. Attachments and pins remain separate;
  another chat's generated narrative is absent. C20 owns durable invocation.
- C14 `CatalogueTools` offers seven typed read-only operations backed by the same
  authenticated executor as HTTP: overview, list, open, coverage, query,
  relationships and get_published. Identity comes from a trusted callable on every
  invocation; model arguments cannot supply owner, role, access revision or DB.
  Errors are sanitized. The strict public request includes snapshot and C08
  scope; C14 itself does **not** interpret C17 pins.
- `CatalogueQueryRequest` permits exactly c13.table/inventory/coverage/quality/
  operation with c13-v1 and one canonical input. Native C10-C12 operations must
  use the registered C13 delegation and validated parameters. No SQL, file path,
  admin action or arbitrary Python tool is available.
- C08/C13 receipts provide input object IDs and hashes, scope, snapshot, operation
  and version, parameters, authority, source completeness, query completion and
  explicit known/unknown counts. Actual `c13.inventory` visits full matching
  descendant datasets, deduplicates cross-root links and returns their complete
  identities in the receipt before bounding any preview.
- C01 `publication_compatibility` is a deterministic, bounded whole-question
  validator for registered published workflows. It preserves exact quote evidence
  and rejects incompatible/unresolved qualifiers. C13 immutable published table
  access checks exact frozen scope and records C01 compatibility, but its adapter
  uses a registered workflow template; **C19 must independently validate the
  actual user's question before selecting that operation**. A model's ready
  status or a compatible generic template cannot authorize a conflicting question.

## C19-owned implementation gaps and choices

There is no missing user decision blocking isolated local implementation after
C18 delivery. Existing defaults and explicit unavailable outcomes permit the
following conservative design without providers, real data or infrastructure:

1. Define frozen request/action/observation/budget/completion/result contracts in
   new C19 modules. Actions may select allowlisted catalogue operations, clarify
   or finish. Reject unknown keys, ambiguous JSON, nonfinite/oversized values and
   forged trusted fields. Supply an injected fake structured runtime in tests;
   gate the controller independently and leave legacy Chat unchanged.
2. Resolve the C17 snapshot and requested scope, inspect pin references through
   current C14 detail/metadata, and derive an effective restriction witness.
   Attachments add evidence but never silently restrict scope. Incompatible
   geography/period/taxon/product/method or uninterpretable pins require explicit
   clarification. Never silently drop a pin or expand to an unpinned source.
   Reuse C01 for eligible exact publication workflows; new descriptive qualifiers
   need a deterministic conservative resolver rather than broad language guesses.
3. Perform deterministic inventory before model exploration. A full population
   receipt plus bounded model summary can account for 100,000 inputs without
   loading 200 pages into the model or spending more than 12 tool actions.
   Keep full evidence server-side; expose IDs/hashes/references and limitations
   through bounded observations. Lists default to 100/max 500 and remain pageable.
   Late objects can be found by permitted search/direct open or explicit paging.
   If exhaustive per-dataset operations require more than the budget, preserve
   honest unfinished dispositions and return partial.
4. Track 180 active seconds and 12 dispatched tool actions, with deterministic
   injected clock/cancellation hooks. Count attempts, including failed calls and
   deterministic inventory, before dispatch. Limit malformed-action repair to
   one global attempt inside the same active budget; a repair is another model
   generation, never an unmetered tool action. Clarification/approval waiting
   belongs outside active exploration. Record overrun/unfinished work explicitly;
   blocking worker/provider cancellation cannot be claimed preemptive.
5. Build requested facts and relevant dataset/cohort dispositions from trusted
   request/receipts. Completion requires supporting observations or explicit
   unresolved dispositions; model finish alone cannot complete. Unknown coverage,
   failed queries, output-limited generation, unsupported fact or budget exhaustion
   must remain partial/clarification/unavailable as appropriate. A summary result
   can have `receipt.total_rows == 1` while its scientific population count is
   100,000; extract the semantic count with entity and denominator, never confuse
   preview rows, summary rows, known zero and unknown coverage.
6. Retain evidence references actually supplied to future synthesis. Compact old
   rows into immutable reference/hash witnesses while preserving all scientific
   limitations and active restrictions. Treat source/document strings as quoted
   data that cannot create tool capabilities, completion claims or identity.
   C20 owns queue/run persistence and C21 final answer/evidence presentation;
   no production route or fabricated scientific approval is implied here.

## Suggested ownership and validation

One agent can own strict C19 action/observation/budget/checklist models and
focused model-validation tests. A second can own scope/pin resolution and its
bounded EN/JA tests, including reuse of C01's actual-question validator. The parent
can own controller orchestration, actual C14/C17 fixture integration, cancellation,
inventory/completion and delivery evidence. Give each agent distinct files and
freeze sources before full acceptance; avoid concurrent broad suites.

Required tests should include actual sealed synthetic C17/C14 execution; separate
100,000-object explicit backend acceptance; rank 26/502/100,000 and later pages;
whole-scope counts unchanged for previews 1/25/100/500; canonical input deduplication;
permission/withdrawal between steps; changed conversation head preserving the
submitted revision; conflicting and unknown pins; Hokkaido/shark EN/JA publication
counterexamples; empty versus unknown coverage; hostile tool/document instructions;
premature finish; malformed action plus exactly one repair; every C06 generation
termination; elapsed/action-budget boundaries and cancellation between actions;
limitations surviving compaction; and no legacy Chat or real-provider fallback.

The planned compatibility command is `python -m pytest
tests/test_research_chat.py tests/test_model_runtime.py
tests/test_chat_source_scope.py -q`; add `tests/test_research_controller.py` and
the new owned suites, then appropriate complete backend/generated/Ruff and hosted
acceptance. **None of those commands ran during this preliminary audit.**

Next action: finish C18 acceptance and hosted delivery in the parent, regenerate
a new final readiness receipt preserving this preliminary receipt, confirm the
59-entry chain still matches, then select C19 if still ready. External providers,
scientific reviews, production data, cloud target configuration and deployment
remain separate explicit gates.
