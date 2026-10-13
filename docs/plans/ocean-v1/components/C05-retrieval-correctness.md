# C05 — Retrieval correctness

**Status:** Not started. **Prerequisites:** None. **Contract:** embedding identity and source-field mapping.

## Objective and boundaries

Repair audit F06 and F08 so optional documentary retrieval searches the active embedding space and faithfully represents metagenome source fields. Catalogue membership and exact counting must remain independent of this retrieval index in later components.

Included: provider/model/dimension predicates on vector searches, FTS fallback, explicit producer/consumer column mapping and affected-document rebuild instructions. Excluded: changing top-k defaults, new embedding providers, production reindexing, paid embedding calls and implementing catalogue browsing.

## Existing entry points

Verified sources are [hybrid retrieval](../../../../retrieval/hybrid_retriever.py), [vector search](../../../../db/vector_store.py) and [document generation](../../../../retrieval/document_builder.py). The current metagenome builder reads an unsuffixed Kraken field while merged inputs contain `_x`/`_y` variants. Inspect the producer before selecting canonical named fields. Existing tests include `tests/test_vector_store.py`, `tests/test_source_aware_retrieval.py` and `tests/test_hybrid_retrieval_contract.py`.

## Interface decisions

Filter candidates by stored provider, model and dimension matching the active query embedding identity, in addition to current active/source/scope filters. Same-dimensional vectors from different models are incompatible. Missing identity is ineligible for vector ranking; preserve scoped full-text fallback and report retrieval limitations rather than silently mixing spaces. Bind generated documents to source and mapping versions. Use explicit Kraken/MetaEuk fields at the producer boundary; tolerate old layouts only through a named, tested compatibility adapter, not guesswork over interchangeable fields.

## Resumable checkpoints and acceptance

1. **Embedding isolation:** add emitted-SQL and result tests for provider, model and dimension mismatches, including equal dimensions. Acceptance: both vector entry points exclude incompatible vectors and empty vector matches still permit authorized FTS results.
2. **Document fidelity:** establish named metagenome columns and update production/consumption together. Acceptance: representative merged rows include correct Kraken and MetaEuk taxa once, without exchanging method labels or losing one source.
3. **Rebuild readiness:** validate document hashes and synthetic rebuilding locally; identify affected legacy documents and supply explicit later reindex steps. Acceptance: a repeat build is deterministic and current identity filters cannot reactivate stale incompatible vectors. Do not actually reindex a live store.

Implementation validation: `python -m pytest tests/test_vector_store.py tests/test_source_aware_retrieval.py tests/test_hybrid_retrieval_contract.py tests/test_pr3_review_fixes.py`. Add proposed `tests/test_metagenome_document_contract.py` for producer-to-document cases and run it once created. Real PostgreSQL vector behavior requires the existing disposable integration harness; report skipped integration rather than treating SQL inspection as equivalent.

## Compatibility, rollback and handoff

Preserve retrieval response shape and historical documents. Keep old objects traceable; replacements receive fresh version/hash evidence. Rollback may disable vector retrieval and retain FTS rather than restore mixed-space ranking. Record predicate locations, field contract, synthetic validation and deferred live rebuild in `handoffs/C05.md`; checkpoint `STATUS.md`. Completion covers repair and local acceptance, not a production index migration.

## Exact prompts

**Planning-only**
> Review C05 only, without implementation. Read docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C05-retrieval-correctness.md and relevant handoffs; no prerequisites apply. Inspect the checkout and actual producers/consumers. Report refinements without code edits, reindexing or beginning implementation without an explicit implementation request.

**Implementation**
> Implement only C05. Read the planning README, MASTER_PLAN, DECISIONS, STATUS, this C05 specification and relevant handoffs under docs/plans/ocean-v1; no prerequisites apply. Verify the checkout, preserve unrelated work and complete checkpoints. Update STATUS.md and handoffs/C05.md after each; run required tests before completion. Use synthetic local rebuilds only. Do not start another component, reindex production, publish, make cloud writes, provision, deploy or run paid model evaluation.

**Resume**
> Resume C05 only after reading docs/plans/ocean-v1/{README.md,MASTER_PLAN.md,DECISIONS.md,STATUS.md}, components/C05-retrieval-correctness.md and handoffs/C05.md; there are no prerequisites. Reconcile checkout/test evidence and continue the next unfinished checkpoint. Preserve unrelated work, test changes and update status/handoff. Keep live rebuilds pending. Do not start another component, publish, provision, deploy, make cloud writes or run paid model evaluation.
