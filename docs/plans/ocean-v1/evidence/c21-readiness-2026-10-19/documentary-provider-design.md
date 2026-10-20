# Concrete frozen documentary retrieval for C21

Design preparation only; C21 remains unselected. A concrete provider, not just a
port/fake, belongs in the local implementation and actual sealed-store tests.

## Existing storage and policy reuse

`LocalCatalogueSnapshotStore.read(snapshot_id)` verifies the registered C09
manifest, exact object membership/hashes and current withdrawal/retirement state.
`ScientificCatalogueRegistration.require_current(store)` additionally verifies
retained index/child references. `load_registry(manifest, contents)` validates
C13's registry ownership, table content and schema; it deliberately rejects extra
objects outside the registry and declared scientific tables. Do not append an
unregistered documentary blob to an existing C13 manifest.

C13 already has `Definition(category="source_documentation")`, exact
`input_dataset_ids`, provenance and bounded `values` JSON. Reuse that metadata
container for a typed `c21-documentary-source-v1` section. Its immutable parent is
the existing `scientific:registry` object, whose bytes/hash are sealed by C09.
This adds a document index contract over explicit frozen metadata, not a new
scientific data adapter, acquisition path or automatic index rebuild.

The first provider searches explicitly registered source-documentation records.
It does not claim to search every paper or every string in a snapshot. A snapshot
without such records yields an honest empty documentary result; absent provider
configuration remains unavailable. Existing generic Definition records can remain
unchanged. Synthetic integration fixtures seal real C09/C13 snapshots containing
typed documentary records; they do not merely mock the provider return value.

## Typed source and result records

Suggested contents of a source-documentation Definition's `values`:

```text
schema_version: c21-documentary-source-v1
documents: [
  id, title:{en,ja}, language:en|ja, text, content_sha256
  input_bindings:[dataset_id, child_snapshot_id, source_id, source_family]
  applicability_scope: EvidenceScope
  qualifications:[...]
]
```

Every inner input must belong to the outer Definition's declared inputs and
match the exact C13 DatasetBinding. Require the declared input sets to agree;
neither an arbitrary string source ID nor the index's CTD storage carrier grants
scientific membership. IDs are namespaced by Definition ID to prevent collisions.
`content_sha256` hashes the decoded document's exact UTF-8 text bytes, separately
from the outer registry object hash. Preserve both.

The provider returns `DocumentarySearchReceipt` with operation/version,
question/query hash, frozen context/scope/input-manifest bindings, policy witness,
index snapshot/object hash, ranking version, limits and exact selected excerpts.
Each excerpt includes source/document identity, full text hash, byte start/end,
exact excerpt text/hash, input bindings, applicability and qualifications. An
excerpt ID hashes those identities/offsets, so later text cannot impersonate it.
Returned evidence is documentary quotation, never a published result or proof of
inventory counts, observed coverage, physical identity or scientific approval.

## Concrete provider and search

```text
FrozenDocumentaryProvider(
    store: explicit C09 v1 store,
    registration: ScientificCatalogueRegistration,
    catalogue: same actual C14 CatalogueService
).search(
    query, binding, effective_scope, permitted_input_manifest,
    current_actor, expected_policy_revision, limit, remaining_timeout
) -> DocumentarySearchReceipt
```

1. The C21 journal reserves one tool attempt before entering search. Queued waits
   consume no active time; registration/read/decode/policy/ranking work does.
2. Validate exact submitted snapshot and same-site dependencies. Check registration
   references and freshly resolve current C14 access; no `latest()` discovery.
3. Read and validate the sealed C13 registry. Obtain the complete currently
   authorized metadata-node set through C14's bounded opaque-cursor listing under
   the host's resolved question/pin scope. All internal pages belong to this one
   bounded search operation. Policy/cursor changes fail closed.
4. Extract typed documents only from visible source-documentation Definitions.
   Require every document input to belong to the host's actual permitted input
   manifest, current C14 scientific/source policy and exact frozen child binding.
   Validate documentary applicability against the effective scope with the shared
   scientific scope semantics; conflicting geography/date/product/method/taxa
   cannot become a relevant quotation merely because dataset IDs overlap.
5. Validate all document/index/body hashes and reject malformed, duplicate or
   oversized metadata. Do not silently skip invalid registered records and call
   the resulting index complete. Apply eligibility before ranking/top-k so denied
   document names/counts do not influence public results.
6. Deterministically rank all eligible documents using a versioned lexical score:
   normalized case-folded word tokens plus CJK character/bigram tokens, with
   explicit stable ties by canonical document ID. Embeddings are unnecessary.
   Normalization is only for ranking; offsets and quotations use original text.
7. Select bounded exact UTF-8 windows around deterministic matching positions.
   Never slice inside a multibyte character or insert ellipses into hashed excerpt
   text. Record omitted-prefix/suffix flags separately. Default top-k8/cap25 and
   bounded per-excerpt bytes are reasonable initial limits; input/index capacity
   limits reject honestly rather than pretending top-k establishes membership.
8. Recheck current registration/access/policy before returning or committing.
   Retain the exact receipt/documents through C21 storage, then pack only selected
   excerpt IDs for structured selection synthesis. Source text is quoted data,
   including any hostile instructions; the model cannot supply replacement text.

This path performs no legacy `scoped_retrieve` global-cache lookup, current
regional-publication supplement, embedding/provider call, network fetch or source
download. Source-aware ranking ideas and strict scopes can be reused without
calling those legacy runtime entry points.

## Required concrete acceptance

Use actual C09 local sealing, C13 registry loading and C14 current policy, plus a
real `FrozenDocumentaryProvider`. Cover EN/JA lexical queries, deterministic ties,
multi-byte offset/hash reopening, later-ranked documents, multiple metadata pages,
question/pin scope restrictions and two independent snapshots with changed text.
Verify input/source/child/hash mismatches, malformed metadata and tampered retained
bytes fail; denial/revocation and policy changes expose no protected names/counts.
Check that top-k/excerpt lengths never supply dataset totals or become zero
coverage. A fake provider remains useful only for timeout/crash/error injection.

Persist the original excerpt/document/index evidence and recheck current access
on reopening. The source receipt's C09 index and child dependencies must receive
C21 retention references before public use. Live corpus acquisition, transfer,
index publication or cloud resources remain separately authorized operations.
