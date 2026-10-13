# C21 — Evidence and answer synthesis

**Status:** Not started. **Prerequisites:** C05, C06, C07, C13, C19, C20.

## Objective and boundaries

Turn completed catalogue operations into traceable answers whose coverage, scientific authority and limitations remain clear. A researcher must be able to reopen the evidence for a claim after publication changes, subject to current access and retention rules.

Include observation receipts, synthesis packing, citations, published-result integration, scoped documentary RAG and partial answers. Exclude new data adapters, experiment execution and automatic publication. C13 supplies the scientific meaning of published objects; C19 supplies completion status.

## Verified entry points and contracts

Inspect [published result packing](../../../../orchestration/published_results.py), [citation handling](../../../../orchestration/citations.py), [answer audit](../../../../orchestration/answer_audit.py), [retention](../../../../db/retention.py) and [evidence navigation](../../../../frontend/components/EvidenceNavigator.tsx).

Persist immutable receipts containing operation and parameters, snapshot/context revision, input identities, operation version, result hash, executed scope, completeness and limitations. Store large tables separately with bounded previews. A limited preview never means the exact query used only those rows.

Pack only permitted observations into synthesis; citations may target only evidence actually supplied. Keep critical qualifiers attached when compacting observations. Exact results, published analyses and experimental outputs retain distinct authority. Citation syntax validity cannot establish factual correctness. Scoped RAG retrieves supporting documentation, while C14/C19 inventory and exact operations establish membership and totals.

Keep transcripts separate across chats. Reusing another chat's result requires explicitly attaching its retained receipt; generated prose does not become scientific evidence. Downloads use C07 serialization and recheck permissions. Retention/holds from C03 apply transitively through prerequisite completion.

## Resumable checkpoints

1. Define receipt identity, payload/storage boundaries and owner-scoped reopening; connect the C20 event stream without copying full tables into each event.
2. Integrate exact/published/documentary evidence packing and provider-independent synthesis; reject truncated responses and unsupported citations.
3. Wire answer cards and citation navigation to retained evidence, with complete/partial scope disclosures and safe exports. Preserve legacy link behavior.

## Future verification and acceptance

Existing regressions: `python -m pytest tests/test_research_chat.py tests/test_prompt_builder.py tests/test_retention.py tests/test_model_runtime.py -q`; frontend: `npm --prefix frontend test` and `npm --prefix frontend run typecheck`.

Add focused receipt/synthesis tests during implementation. Cover data changes after a run, revoked access, protected retention, result tampering, citation to unseen material, truncation, unknown coverage, count-versus-preview confusion and unverified relationship language. Verify old citation links still resolve and experimental evidence cannot acquire published authority through summaries. Use synthetic data and fake model responses; live-model checks need explicit authorization.

## Compatibility, rollback and handoff

Version new receipts separately from historical Chat records. Rollback disables new synthesis routing while preserving retained artifacts and old links. Update [status](../STATUS.md) and `handoffs/C21.md` with receipt versions, storage/retention behavior, verification and incomplete cases after every checkpoint.

## Copy-and-paste prompts

**Planning only:** “Review only C21 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C21-evidence-synthesis.md, prerequisite handoffs C05/C06/C07/C13/C19/C20 and the current checkout. Refine documentation without implementation; preserve unrelated work.”

**Implementation:** “Implement only C21. Read docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C21-evidence-synthesis.md and prerequisite handoffs C05/C06/C07/C13/C19/C20; reconcile the checkout. Follow checkpoints, run required local checks, and update STATUS.md and handoffs/C21.md throughout. Preserve unrelated work; do not advance components, provision, deploy or run paid/live evaluations.”

**Resume:** “Resume only C21 using docs/plans/ocean-v1/README.md, MASTER_PLAN.md, DECISIONS.md, STATUS.md, components/C21-evidence-synthesis.md, handoffs/C21.md and prerequisite handoffs C05/C06/C07/C13/C19/C20. Reconcile checkout and evidence, continue the next unfinished checkpoint, and update status/handoff. Preserve unrelated work; no automatic advance, provisioning, deployment or paid/live evaluations.”
