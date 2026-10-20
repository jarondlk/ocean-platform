# C21 — Evidence and answer synthesis

**Status:** In progress; reviewed implementation/local acceptance pass, exact-source hosted delivery pending after a CI time allowance amendment. **Prerequisites:** C05, C06, C07, C13, C19, C20.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

Implementation contract: [evidence and structured synthesis](../C21_EVIDENCE_SYNTHESIS_CONTRACT.md).

## Objective and boundaries

Turn completed catalogue operations into traceable answers whose coverage, scientific authority and limitations remain clear. A researcher must be able to reopen the evidence for a claim after publication changes, subject to current access and retention rules.

Include observation receipts, synthesis packing, citations, published-result integration, scoped documentary RAG and partial answers. Exclude new data adapters, experiment execution and automatic publication. C13 supplies the scientific meaning of published objects; C19 supplies completion status.

## Verified entry points and contracts

Inspect [published result packing](../../../../orchestration/published_results.py), [citation handling](../../../../orchestration/citations.py), [answer audit](../../../../orchestration/answer_audit.py), [retention](../../../../db/retention.py) and [evidence navigation](../../../../frontend/components/EvidenceNavigator.tsx).

Persist immutable receipts containing operation and parameters, snapshot/context revision, input identities, operation version, result hash, executed scope, completeness and limitations. Store large tables separately with bounded previews. A limited preview never means the exact query used only those rows.

Pack only permitted observations into synthesis; citations may target only evidence actually supplied. Keep critical qualifiers attached when compacting observations. Exact results, published analyses and experimental outputs retain distinct authority. Citation syntax validity cannot establish factual correctness. Scoped RAG retrieves supporting documentation, while C14/C19 inventory and exact operations establish membership and totals.

Keep transcripts separate across chats. Reusing another chat's result requires explicitly attaching its retained receipt; generated prose does not become scientific evidence. Downloads use C07 serialization and recheck permissions. Retention/holds from C03 apply transitively through prerequisite completion.

## Independent evidence and UI integration

Integrate answer/evidence panels in frontend-v1, preserving P00's reviewed UX and
C18's runtime boundary. Receipts and artifacts live in v1 stores; origin provenance
from approved copies does not grant legacy access. Legacy citation/history links
remain on the legacy site. Do not add an automatic cross-site history reader.
Run the new frontend's actual scripts for its evidence behavior; legacy tests
remain supplementary compatibility regressions.

## Resumable checkpoints

1. Define receipt identity, payload/storage boundaries and owner-scoped reopening; connect the C20 event stream without copying full tables into each event.
2. Integrate exact/published/documentary evidence packing and provider-independent synthesis; reject truncated responses and unsupported citations.
3. Wire answer cards and citation navigation to retained evidence, with complete/partial scope disclosures and safe exports. Preserve legacy link behavior.

## Future verification and acceptance

Existing regressions: `python -m pytest tests/test_research_chat.py tests/test_prompt_builder.py tests/test_retention.py tests/test_model_runtime.py -q`; frontend: `npm --prefix frontend-v1 test` and `npm --prefix frontend-v1 run typecheck`.

Add focused receipt/synthesis tests during implementation. Cover data changes after a run, revoked access, protected retention, result tampering, citation to unseen material, truncation, unknown coverage, count-versus-preview confusion and unverified relationship language. Verify old citation links still resolve and experimental evidence cannot acquire published authority through summaries. Use synthetic data and fake model responses; live-model checks need explicit authorization.

## Compatibility, rollback and handoff

Version new receipts separately from historical Chat records. Rollback disables new synthesis routing while preserving retained artifacts and old links. Update [status](../STATUS.md) and `handoffs/C21.md` with receipt versions, storage/retention behavior, verification and incomplete cases after every checkpoint.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c21). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.
