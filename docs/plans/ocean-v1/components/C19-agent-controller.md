# C19 — Agent exploration controller

**Status:** Complete for all3 local checkpoints; source checkpoint and exact-source hosted delivery pending. **Prerequisites:** C01, C06, C14, C17.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Give the agent a complete inventory and validated operations before selecting detailed evidence. The observable result is a snapshot-bound investigation that can answer a whole-dataset count or locate an item outside legacy top-25 retrieval, and explain any unfinished coverage.

Include scope resolution, typed actions, tool dispatch, budget accounting and completion checks. Exclude durable queue delivery (C20), final answer/evidence presentation (C21), arbitrary SQL, experiments and infrastructure. Keep the controller separate from the legacy Chat function.

## Verified entry points and contracts

Inspect [model runtime](../../../../model_runtime.py), [unified retrieval](../../../../orchestration/unified.py), [scope rules](../../../../orchestration/evidence_scope.py) and [research intents](../../../../orchestration/research_intents.py). Existing structured model calls and exact workflows are reusable boundaries; their existence does not establish that the new controller is implemented.

Use C06's provider-independent structured action contract and C14's tools. Capture the C17 snapshot and context revision before the first action. Explicit pins are binding; incompatible geography, period, taxon, product or method requires clarification. The deterministic inventory step precedes model-directed exploration. Existing exact-answer shortcuts remain valid after the same scope checks.

Default to 180 seconds of active execution, 12 tool actions and one malformed-action repair inside that budget. Listing pages default to 100 rows and cap at 500; these limits never bound aggregate input rows. Store requested facts and relevant dataset dispositions in the completion checklist. Only supported facts or explicit unresolved dispositions permit completion; a model `finish` action cannot bypass it. Unresolved facts produce a partial or clarification outcome.

## Resumable checkpoints

1. Define action, observation, budget and completion contracts with deterministic fake-model fixtures; map existing exact operations without changing legacy behavior.
2. Implement inventory-first dispatch, shared scope validation, bounded observation previews and one repair attempt. Preserve scientific limitations during context compaction.
3. Implement deterministic completion and partial outcomes; test cancellation hooks for C20 and supply C21 an evidence reference list.

## Future verification and acceptance

No checks are executed by this planning document. Existing regression command: `python -m pytest tests/test_research_chat.py tests/test_model_runtime.py tests/test_chat_source_scope.py -q`. Add and run `tests/test_research_controller.py` as part of implementation, recording its exact command in the handoff.

Acceptance covers rank-26 and later-page discovery, exact counts independent of preview size, conflicting pins, unknown coverage, hostile tool/document text, premature finish, malformed actions, model truncation and exhausted budgets. Use fake runtimes; paid/live model evaluation is a separately authorized activity. All observations must retain executed scope and snapshot identity.

## Compatibility, rollback and handoff

Gate the controller independently of legacy `/chat`. Disabling it preserves investigations and observations. Update [status](../STATUS.md) and `handoffs/C19.md` after each checkpoint with code location, contracts, executed checks and the next unfinished step.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c19). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Local acceptance — 2026-10-19 JST

C19 local acceptance passes: 4570 backend/187 gated skips/85.43%;356 new C19 cases and164 required compatibility cases; all9 generated checks/Ruff and independent source review. Inventory-first C17/C14 exploration, binding pins, full-count/later-page discovery, deterministic completion and cooperative stopping are implemented. C18 frontend23 sources remain unchanged. Source checkpoint and exact-source hosted delivery are pending. [Handoff](../handoffs/C19.md), [contract](../C19_AGENT_CONTROLLER_CONTRACT.md), [receipt](../evidence/C19/verification.json).
