# C05 — Retrieval correctness

**Status:** Complete locally (2026-10-15 JST). **Prerequisites:** P00. **Contract:** embedding identity and source-field mapping.

## Revised delivery boundary

Work on overhaul for the separate v1 system described in
[SITE_SEPARATION.md](../SITE_SEPARATION.md). The legacy site and its resources
remain unchanged. Existing entry points are reuse/regression references, not
permission to connect to production. P00 precedes backend implementation; its
prototype is not acceptance evidence for this component.

## Objective and boundaries

Repair audit F06 and F08 so optional documentary retrieval searches the active embedding space and faithfully represents metagenome source fields. Catalogue membership and exact counting must remain independent of this retrieval index in later components.

Included: provider/model/dimension predicates on vector searches, FTS fallback, explicit producer/consumer column mapping and affected-document rebuild instructions. Excluded: changing top-k defaults, new embedding providers, production reindexing, paid embedding calls and implementing catalogue browsing.

## Existing entry points

Verified sources are [hybrid retrieval](../../../../retrieval/hybrid_retriever.py), [vector search](../../../../db/vector_store.py) and [document generation](../../../../retrieval/document_builder.py). The initial metagenome builder read an unsuffixed Kraken field while merged inputs contained `_x`/`_y` variants. Inspect the producer before selecting canonical named fields. Existing tests include `tests/test_vector_store.py`, `tests/test_source_aware_retrieval.py` and `tests/test_hybrid_retrieval_contract.py`.

## Interface decisions

Filter candidates by stored provider, model and dimension matching the active query embedding identity, in addition to current active/source/scope filters. Same-dimensional vectors from different models are incompatible. Missing identity is ineligible for vector ranking; preserve scoped full-text fallback and report retrieval limitations rather than silently mixing spaces. Bind generated documents to source and mapping versions. Use explicit Kraken/MetaEuk fields at the producer boundary; tolerate old layouts only through a named, tested compatibility adapter, not guesswork over interchangeable fields.

## Resumable checkpoints and acceptance

1. **Embedding isolation:** add emitted-SQL and result tests for provider, model and dimension mismatches, including equal dimensions. Acceptance: both vector entry points exclude incompatible vectors and empty vector matches still permit authorized FTS results.
2. **Document fidelity:** establish named metagenome columns and update production/consumption together. Acceptance: representative merged rows include correct Kraken and MetaEuk taxa once, without exchanging method labels or losing one source.
3. **Rebuild readiness:** validate document hashes and synthetic rebuilding locally; identify affected legacy documents and supply explicit later reindex steps. Acceptance: a repeat build is deterministic and current identity filters cannot reactivate stale incompatible vectors. Do not actually reindex a live store.

Implementation validation: `python -m pytest tests/test_vector_store.py tests/test_source_aware_retrieval.py tests/test_hybrid_retrieval_contract.py tests/test_pr3_review_fixes.py tests/test_metagenome_document_contract.py`. The new contract suite covers producer-to-document fidelity and replacement identity. Real PostgreSQL vector behavior requires the existing disposable integration harness; report skipped integration rather than treating SQL inspection as equivalent.

## Compatibility, rollback and handoff

Preserve retrieval response shape and historical documents. Keep old objects traceable; replacements receive fresh version/hash evidence. Rollback may disable vector retrieval and retain FTS rather than restore mixed-space ranking. Record predicate locations, field contract, synthetic validation and deferred live rebuild in `handoffs/C05.md`; checkpoint `STATUS.md`. Completion covers repair and local acceptance, not a production index migration.

## Exact prompts

Use the independent planning, implementation or resume prompt in
[PROMPTS.md](../PROMPTS.md#c05). Read the current site-separation
plan, UX brief and listed prerequisite handoffs as well as this specification.

## Local acceptance — 2026-10-15 JST

142 required cases pass. Actual disposable PostgreSQL/pgvector validates 10 fixed-code
cases plus two exact historical bug probes; all 39 existing PostgreSQL regressions
and two idempotent corpus upserts pass. The full backend has 1,806 passes,
63 explicit integration-gated skips and 81.77% coverage. Independent review, Ruff,
source/preservation checks and deterministic synthetic export hashes pass.
See [handoff](../handoffs/C05.md), [receipt](../evidence/C05/verification.json) and
[deferred rebuild runbook](../C05_REBUILD_RUNBOOK.md). Real/live rebuild and provider
calls remain deferred; C05 is uncommitted and no hosted C05 acceptance is claimed.
