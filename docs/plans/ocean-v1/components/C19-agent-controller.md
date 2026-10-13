# C19 — Agent exploration controller

**Status:** Not started. **Prerequisites:** C01, C06, C14, C17.

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

## Copy-and-paste prompts

**Planning only:** “Review C19 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C19-agent-controller.md, prerequisite handoffs C01/C06/C14/C17 and the current checkout. Refine this component's plan only; do not implement. Preserve unrelated work and record unresolved decisions.”

**Implementation:** “Implement only C19. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C19-agent-controller.md and prerequisite handoffs C01/C06/C14/C17; reconcile them with the current checkout. Follow checkpoints, run required local checks, update STATUS.md and handoffs/C19.md after each checkpoint, and preserve unrelated work. Do not advance components, provision, deploy or run paid/live evaluations.”

**Resume:** “Resume only C19 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C19-agent-controller.md, handoffs/C19.md and prerequisite handoffs C01/C06/C14/C17. Reconcile the checkout and evidence, continue the first unfinished checkpoint, and update status/handoff. Preserve unrelated work; no automatic advance, provisioning, deployment or paid/live evaluations.”
