# C01 — Scientific scope validation

**Status:** Complete (local checks passed 2026-10-14 JST). **Prerequisites:** P00. **Contract:** shared scientific scope v1.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

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

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c01). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Completion receipt

All three checkpoints are complete. The required suites, shared-contract matrix
and publication regressions pass 319 tests at the [recorded source hashes](../evidence/C01/verification.json).
See [C01 handoff](../handoffs/C01.md) for the typed contract, compatible question
boundary, original red regressions, history/row compatibility and remaining
v1 scientific/integration/release gates. No deployment or provider call occurred.
