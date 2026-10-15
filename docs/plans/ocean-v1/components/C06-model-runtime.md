# C06 — Model runtime contract

**Status:** Complete locally and delivered (2026-10-15 JST). **Prerequisites:** P00. **Contract:** provider-independent generation result v1.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

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

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c06). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Readiness audit — 2026-10-15 JST

Ready for explicit implementation selection, still Not started. P00 is Complete
and all 36 accepted source hashes match. C05 delivery/hosted CI passes. The three
listed baseline suites pass 99 cases. Synthetic adapter and actual stubbed API
probes reproduce F07 and identify missing/unknown termination handling and metadata
as the intended first checkpoint. No C06 application source changes or provider
calls occurred. See [readiness audit](../C06_READINESS_AUDIT_2026-10-15.md).

## Local acceptance — 2026-10-15 JST

Generation-result v1, strict ordinary/structured wrappers and metadata-aware
API/planner integration pass 230 required/consumer cases, including 119 runtime
and 24 actual-adapter/API/SQLite/planner cases. Full backend:1,937 passed,
63 PostgreSQL-gated skips and 81.81% coverage. Separate actual disposable PostgreSQL
regressions pass 39 cases and two idempotent corpus upserts; its server is stopped.
Independent review, Ruff, scope contract and preservation pass. Provider calls
remain mocked; no live provider/model quality or deployment is claimed. See
[handoff](../handoffs/C06.md) and [local source receipt](../evidence/C06/verification.json).

Hosted acceptance now passes for implementation commit 27d76c9: 1,928 backend tests,
82.64% coverage, both frontends and 63 PostgreSQL cases plus backup/restore.
See [delivery receipt](../evidence/C06/delivery.json). C07 remains unselected.
