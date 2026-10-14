# C05 deferred metagenome rebuild

Updated: 2026-10-15 JST. This procedure is prepared for later execution against
an explicitly selected isolated v1 store. C05 acceptance used synthetic documents
and owned disposable databases; the real serving files and live indexes have
not been regenerated.

## Inventory and mapping

[The read-only inventory](evidence/C05/synthetic-rebuild.json) binds the local
serving inputs by SHA256. `retrieval_documents.parquet` has 323 documents:
162 CTD, 82 metagenome and 79 remote-sensing. All 82 legacy `meta_<sample_id>`
documents include the MetaEuk label and omit the Kraken taxa label. They have no
mapping/source/document-version metadata. This is a local file inventory, not a
claim about any production database. The inventory includes every affected ID.

The retained context has 207 rows, including 82 with both methods present.
The historical merge put Kraken on the left (`top_genus_10_json_x`) and MetaEuk
on the right (`top_genus_10_json_y`). The named compatibility adapter validates
this complete pair. Canonical producer fields are `top_kraken_genera_json`,
`top_metaeuk_genera_json` and `top_kraken_upper_groups_json`.
Incomplete pairs, mixed layouts, ambiguous unsuffixed summaries, malformed
JSON and payloads contradicting coverage fail visibly.

## Staged document generation

1. Select the frozen context and previous document inventory; record their
   SHA256 hashes, source snapshot, target database identity and intended sample
   IDs. Preserve the old Parquet/JSONL outputs and database evidence.
2. In a separate staging directory, use `build_metagenome_docs` followed by
   `documents_to_dataframe` and `documents_to_jsonl`. Limit the context to the
   intended sample IDs. The builder validates retained layouts through
   `adapt_legacy_metagenome_context`; it does not need a model provider or DB.
3. Compare taxa and method labels with the frozen inputs, repeat the build and
   compare IDs, text, metadata and serialized hashes. Validate the frame with
   `metagenome_replacement_scope`. Review all missing/contradictory fields.
   No partial malformed input should reach the upsert.

Example generation after selecting the actual paths and sample scope:

```python
from pathlib import Path
import pandas as pd
from preprocessing.metagenome_contract import metagenome_replacement_scope
from retrieval.document_builder import (
    build_metagenome_docs, documents_to_dataframe, documents_to_jsonl,
)

context_path = Path("SELECTED_FROZEN_CONTEXT.parquet")
staging = Path("SELECTED_STAGING_DIRECTORY")
selected_samples = {"SELECTED_SAMPLE_ID"}
context = pd.read_parquet(context_path)
context = context[context["sample_id"].isin(selected_samples)].copy()
assert set(context["sample_id"]) == selected_samples
documents = build_metagenome_docs(context)
assert documents == build_metagenome_docs(context)
frame = documents_to_dataframe(documents)
assert set(metagenome_replacement_scope(frame)) == selected_samples
staging.mkdir(parents=True, exist_ok=True)
frame.to_parquet(staging / "metagenome_replacements.parquet", index=False)
documents_to_jsonl(documents, staging / "metagenome_replacements.jsonl")
```

The broad `scripts/build_retrieval_docs.py` command also rewrites anchors,
links, CTD and SST outputs. Use the scoped builder above for a C05-only rebuild.
New IDs are `meta_<sample_id>_v2_<generation_hash[:32]>`. Metadata records the
full generation hash, canonical source-row SHA256, field mapping version,
document version, title/text content hash and legacy ID. The generation hash
binds the complete generated scientific/provenance fields and metadata witness.
Changing that evidence requires a fresh ID even when rendered text is unchanged.

## Dry run and transactional replacement

1. Verify the isolated target's database/role/server identity and take a retained
   snapshot of the affected rows, including embeddings and all identity fields.
2. Point the selected loader input at the reviewed staged candidate. For a
   corpus-wide loader input, retain all unrelated document families; replace
   only the selected metagenome entries with their reviewed v2 rows. Keep old
   objects in the preserved historical export rather than the incoming active
   candidate. Record each legacy-to-v2 ID pair.
3. With an explicit target URL, run the existing read-only loader planner:
   `python scripts/load_db.py --upsert --dry-run --json`. Review planned inserts,
   scoped inactivations and stale rows. Its refresh estimate covers inserted or
   changed document text; separately count embeddings requiring the selected
   provider/model/dimension, including unchanged rows with missing identities.
4. Execute the reviewed upsert only when that target and candidate are selected
   for mutation. Do not use `--reset` or `--embed`. `upsert_corpus` validates v2
   identity before writing, takes the existing corpus advisory transaction lock,
   inserts replacements and inactivates older metagenome rows for represented
   samples in one transaction. Older rows, text, metadata and embeddings remain
   stored; unrelated samples and source families remain active.
5. Verify the actual stored metadata hashes and legacy-to-v2 mapping. New rows
   start unembedded. Repeat the same upsert: IDs and scientific evidence should
   remain unchanged and any new compatible embeddings should be retained.
   Replaying an older candidate can select that older generation again; always
   bind the loader to the chosen frozen candidate and generation, not an
   unversioned filesystem cache.

## Embedding refresh and retrieval acceptance

Document generation and upsert require no provider calls. Choose the exact
provider, model, dimension and allowed call budget separately before embedding.
Use `embedding_refresh_candidate_count(source_type="metagenome", sample_id=...)`
to inspect the selected sample scope without a model call. If refresh is selected,
`update_document_embeddings` supports the same scope and a canary `limit`.
The generic embedding CLI's `--dry-run` counts all active candidates; its normal
mode is broader than this scoped rebuild.

After embedding, test both PostgreSQL entry points: only active matching
provider/model/dimension rows can rank; same-dimensional different-model and
missing-identity rows remain excluded. New unembedded documents can participate
in authorized FTS. Compare result IDs, labels and scoped diagnostics. A database
column with a different physical vector width requires a separate schema plan;
C05 does not change it, and hybrid retrieval reports vector unavailability while
its independent FTS transaction can still return authorized documents.

## Rollback

On transaction failure the new generation and old-row inactivation roll back
together. After a committed replacement, retain both generations and choose the
reviewed active generation under the same transaction lock. Do not delete old
rows, copy old vectors onto new text, rewrite stored embedding identity or restore
mixed-model ranking. Disable the vector branch and retain scoped FTS while an
embedding problem is investigated. This runbook does not establish scientific
approval, a production migration or release acceptance.
