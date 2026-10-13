# C01 — Scientific scope validation

**Status:** Not started. **Prerequisites:** None. **Contract:** shared scientific scope v1.

## Objective and boundaries

Reject incompatible published evidence before either exact rendering or model synthesis. In particular, a ready planner response must not authorize a Miyagi all-fish panel for Hokkaido or shark-specific questions (audit F10). Success means the same resolved scope produces the same eligibility decision in both routes.

Included: geography, dates, taxa/panel, assay protocol, assignment method, explicit exclusions and fixed workflow restrictions. Excluded: new taxonomic inference, new scientific datasets, a replacement planner, catalogue endpoints and live model evaluation. Unknown compatibility requires clarification, never a guessed mapping.

## Existing entry points

Verified sources are [question checks](../../../../orchestration/research_question.py), [planner constraints](../../../../orchestration/settings_planner.py) and [execution checks](../../../../orchestration/research_intents.py). Existing fixtures and tests are in `tests/test_auto_settings.py`, `tests/test_research_chat.py` and `docs/audits/repository-2026-10-12/scope_probes.py`; the probe is reference evidence, not a production command.

## Interface decisions

Introduce one typed scope-compatibility result with compatible, incompatible or unresolved outcomes, reason and field-level evidence. Resolve against registered geography, panel and method identities plus traceable question qualifiers; do not extend a place denylist as the solution. Explicit pins remain binding, but cannot erase contrary text. Unsupported new qualifiers must produce the existing clarification response. The executor independently validates the effective scope rather than trusting planner status. Preserve bilingual supported templates and legacy exact result shapes.

## Resumable checkpoints and acceptance

1. **Reproduce and specify:** add offline regression fixtures for the three F10 examples, accepted Miyagi questions, explicit pin contradictions and unknown qualifiers. Acceptance: the original defect is demonstrated with a stubbed ready proposal.
2. **Share validation:** route exact planning, synthesis planning and published execution through the contract. Acceptance: contradictory scope fails at both planning and execution, while supported manual templates remain valid.
3. **Complete parity:** cover dates, protocol, method, exclusions and fixed top-ten limitations in English and Japanese. Acceptance: no route silently drops an explicit constraint, and clarification preserves the user's selections.

Run from repository root during implementation: `python -m pytest tests/test_auto_settings.py tests/test_research_chat.py tests/test_chat_source_scope.py`. Extend these actual suites; add proposed `tests/test_publication_scope_contract.py` for shared-contract cases, then run it after creation. No tests were run for this documentation setup.

## Compatibility, rollback and handoff

Keep endpoint and saved-history compatibility. Reverting a validator must not restore unsafe automatic synthesis; disable affected synthesis eligibility instead. Record contract shape, regression commands/results and unresolved qualifier classes in `handoffs/C01.md`; update `STATUS.md` after every checkpoint. Complete only after all acceptance checks pass.

## Exact prompts

**Planning-only**
> Review C01 without implementing. From the repository root read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C01-scientific-scope.md and relevant handoffs; C01 has no prerequisites. Inspect the current checkout and reconcile any drift. Report refinements only. Do not edit application code, run mutations or begin implementation without my explicit implementation request.

**Implementation**
> Implement only C01. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C01-scientific-scope.md and relevant handoffs; there are no prerequisites. Verify the checkout, preserve unrelated work and follow the checkpoints. Update STATUS.md and handoffs/C01.md after each checkpoint. Run and record required tests before completion. Do not start another component, publish scientific outputs, make cloud writes, provision, deploy or run paid model evaluation.

**Resume**
> Resume C01 only. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this specification and docs/plans/ocean-v1/handoffs/C01.md; C01 has no prerequisites. Reconcile checkpoint claims with the current checkout and test evidence. Continue the first unfinished checkpoint, preserve unrelated work, and update status/handoff as work completes. Retest changes before completion. Do not start another component, publish, provision, deploy, make cloud writes or run paid model evaluation.
