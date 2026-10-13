# C06 — Model runtime contract

**Status:** Not started. **Prerequisites:** None. **Contract:** provider-independent generation result v1.

## Objective and boundaries

Fix audit F07 and expose the execution metadata needed by the future research controller. A nonempty response stopped by an output limit is incomplete, including Ollama `done_reason=length`; it cannot enter a completed-answer path.

Included: common result/termination semantics for ordinary and structured generation, measured duration, provider usage where available, compatibility wrappers and mocked-provider tests. Excluded: choosing new models, changing provider credentials, live benchmarking, controller retries, native function-calling requirements and embedding redesign.

## Existing entry points

Verified boundary: [model runtime](../../../../model_runtime.py), with consumers in [settings planning](../../../../orchestration/settings_planner.py) and [query orchestration](../../../../orchestration/query_orchestrator.py). Existing tests are `tests/test_model_runtime.py`, `tests/test_query_orchestrator.py` and `tests/test_auto_settings.py`. The current protocol returns strings; Vertex already checks some answer termination while ordinary Ollama chat does not.

## Interface decisions

Add result-returning generation methods exposing content, provider/model, normalized termination status, original finish reason, elapsed time and optional token usage. Keep existing string-returning `chat` and `structured_chat` wrappers for compatibility; they return only completed content and otherwise raise a provider-neutral typed error. Use explicit completed, output-limited, refused, failed and unknown outcomes. Do not turn unavailable usage into zero or unknown termination into success. Structured JSON validity does not override an incomplete provider response. Normalize provider payloads centrally and never log credentials or complete sensitive prompts.

## Resumable checkpoints and acceptance

1. **Result contract:** define typed generation metadata and mocked provider payload fixtures. Acceptance: both provider adapters map normal completion, missing metadata and output-limit termination consistently; usage remains optional.
2. **Completion enforcement:** wire normal and structured generation plus legacy wrappers through the common boundary. Acceptance: partial but nonempty text or parseable JSON cannot become a completed answer; old callers receive supported completed strings.
3. **Consumer compatibility:** exercise orchestration error handling and record usage/timing without adding automatic provider retries. Acceptance: incomplete generation produces the existing safe failure/partial path and never a fabricated answer or successful completion receipt.

Implementation validation: `python -m pytest tests/test_model_runtime.py tests/test_query_orchestrator.py tests/test_auto_settings.py`. Extend existing runtime tests with Ollama length stops, Vertex limits, missing/unknown finishes, refusal, malformed payloads, absent usage and completed legacy calls. All provider calls remain mocked. No model quality, latency benchmark or live provider acceptance is claimed here.

## Compatibility, rollback and handoff

Keep model selection/configuration and existing string-call signatures. New controller components will consume metadata methods; old clients need no response-shape migration. Reverting must preserve refusal of truncated outputs, even if metadata reporting is disabled. Document the result schema, normalized provider mappings, consumer migration notes and test results in `handoffs/C06.md`. Update `STATUS.md` after each checkpoint and complete only after both adapters and consumers pass.

## Exact prompts

**Planning-only**
> Review C06 without implementing. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C06-model-runtime.md and relevant handoffs; no prerequisites apply. Inspect current runtime consumers and the checkout, then report refinements only. Do not edit code, call live providers or begin implementation without an explicit implementation request.

**Implementation**
> Implement only C06. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this C06 specification and relevant handoffs under docs/plans/ocean-v1; no prerequisites apply. Verify the checkout and preserve unrelated work. Follow checkpoints, update STATUS.md and handoffs/C06.md after each, and run required mocked-provider tests before completion. Do not start another component, publish, make cloud writes, provision, deploy, call paid models or run paid model evaluation.

**Resume**
> Resume C06 only. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C06-model-runtime.md and handoffs/C06.md; there are no prerequisites. Reconcile checkpoint claims with code and test evidence, then continue the next step. Preserve unrelated work, retest changes and update status/handoff. Do not start another component, publish, make cloud writes, provision, deploy, call paid models or run paid model evaluation.
