# ANEMONE PR2 — Canonical Schema and Ingestion Plan

> Status: implemented, merged, and deployed in `v0.4.0`. This document retains
> the PR2 implementation contract and verification history.
> Dependency: ANEMONE PR1 acquisition contract
> Scope: normalization, canonical storage, provenance, and transactional upsert

## 1. Outcome

PR2 converts one completed PR1 ANEMONE snapshot into deterministic canonical
eDNA artifacts and loads them into PostgreSQL with complete source-row
traceability. It preserves both assignment methods, all samples and controls,
full taxonomy, sequences, read counts, supplied copies/mL, assay metadata, and
immutable source provenance.

PR2 does not add retrieval documents, embeddings, API routes, frontend views,
biodiversity analyses, cross-source CTD/SST claims, GCP jobs, live data, or a
production deployment.

## 2. Fixed Scientific Decisions

- Canonical source family: `edna_metabarcoding`.
- Provider: `anemone`.
- `community_qc_target.tsv.xz` maps to assignment method `qcauto_target`.
- `community_qc3nn_target.tsv.xz` maps to
  `qcauto_95pct_3nn_target`.
- Assignment methods remain separate in every key, row, validation report,
  and export.
- `read_count` is a sequencing count. It is not abundance, biomass, or
  concentration.
- `copies_per_ml` is nullable and is populated only from a valid supplied
  `ncopiesperml` value. It is never derived from reads.
- Full taxonomic rank data is preserved. Common ranks are also stored in
  indexed columns.
- Unrecognized sample/control classification is stored as `unknown`; the
  normalizer does not guess from a sample name alone.
- Controls are retained. They are not silently excluded from canonical data.
- Only confidently classified environmental samples with valid source
  coordinates and collection time/date receive anchor events.

## 3. Data Flow

```text
completed PR1 snapshot
  -> verify manifest, contract hash, file hashes, and selected roles
  -> parse key/value metadata and community tables
  -> normalize identifiers, dates, coordinates, taxonomy, and numeric values
  -> validate cross-table consistency and control status
  -> write immutable normalized bundle plus validation manifest
  -> optional explicit activation pointer
  -> read-only PostgreSQL upsert plan
  -> explicit transactional PostgreSQL upsert and scope reconciliation
```

The normalizer requires an exact PR1 snapshot ID. It never selects an
incomplete staging directory or inventory manifest.

## 4. PostgreSQL Model

### 4.1 `external_source_snapshot`

One immutable row per completed PR1 collection.

Core fields:

- `snapshot_id` — 64-character PR1 collection SHA-256 primary key;
- `provider`, `source_family`, `scope_url`, and `scope_level`;
- `source_collection_sha256`, `contract_version`, and `contract_sha256`;
- `selection_policy`, `generated_at`, `file_count`,
  `selected_file_count`, `total_bytes`, and `status`;
- `manifest_sha256` and a sanitized manifest summary JSON.

An existing snapshot row is append-only. A conflicting row with the same ID
fails the transaction.

### 4.2 `external_source_file`

One immutable row for every file in the PR1 manifest, including FASTQ and PNG
metadata-only records.

Core fields:

- `source_file_id` — SHA-256 of provider, snapshot, relative path, and source
  file content identity (downloaded SHA-256 when present; otherwise the
  recorded remote validators and size);
- `snapshot_id`, `relative_path`, `source_url`, `sample_name`, and `role`;
- `selection_status`, `size_bytes`, `etag`, `last_modified`, `sha256`,
  `validation_status`, and `row_count`;
- unique `(snapshot_id, relative_path)`.

Selected interpreted files in a completed snapshot require a SHA-256 and valid
status. Metadata-only files may have no content hash because PR1 does not
download them.

### 4.3 `edna_sample`

One current canonical row per provider sample identity.

Core fields:

- `sample_id` — deterministic SHA-256 of provider and provider sample ID;
- `provider` and exact `provider_sample_id`;
- provider project and sequencing-run identifiers from the validated scope;
- `project_name` and the original sample label;
- `sample_kind` — `environmental`, `negative_control`, `positive_control`,
  `mock_community`, or `unknown`;
- nullable `is_control` and `classification_basis`;
- collection date/time, temporal precision, latitude, longitude, and nullable
  source environmental measurements;
- `raw_metadata_json` for all key/value metadata, including unrecognized keys;
- nullable `anchor_event_id`;
- `source_snapshot_id`, `source_file_id`, and source row locators;
- `active`, `first_seen_snapshot_id`, and `last_seen_snapshot_id`;
- `scientific_content_sha256` and `source_row_hash`.

Database checks cover coordinate ranges and allowed sample classifications.
Provider sample identity is unique.

### 4.4 `edna_assay`

PR2 models the single contracted `experiment.tsv.xz` record set for each
sample as one assay. Future multi-assay files require a contract revision.

Core fields:

- `assay_id` — deterministic SHA-256 of provider, provider sample ID, and the
  contracted experiment role;
- `sample_id` foreign key;
- target gene, primer set, sequencing method, library layout, instrument, and
  other reviewed method fields;
- `raw_metadata_json` preserving all experiment keys;
- source snapshot/file/row locators and lifecycle/hash fields matching
  `edna_sample`.

The required raw keys remain `target_gene`, `pcr_primers`, and `seq_meth`.

### 4.5 `edna_detection`

One current row per assay, assignment method, and unique amplicon sequence.

Core fields:

- `detection_id` — SHA-256 of assay ID, assignment method, and sequence hash;
- `assay_id`, `assignment_method`, `sequence`, and `sequence_sha256`;
- `read_count` and nullable `copies_per_ml`;
- indexed `superkingdom`, `kingdom`, `phylum`, `class`, `order`, `family`,
  `genus`, `species`, and `subspecies`;
- `assigned_taxon_name` and `assigned_taxon_rank`, selected from the deepest
  populated source rank without taxonomic reinterpretation;
- `taxonomy_json` containing every rank from the PR1 community contract;
- exact source snapshot/file/row locator, lifecycle fields, and both hashes.

Unique `(assay_id, assignment_method, sequence_sha256)` prevents silent
aggregation. Duplicate source keys fail normalization instead of summing read
counts.

### 4.6 `edna_internal_standard`

One current row per assay, standard label, and standard sequence.

Core fields:

- deterministic `internal_standard_id`;
- `assay_id`, `standard_name`, `sequence`, `sequence_sha256`, and
  `read_count`;
- exact source snapshot/file/row locator, lifecycle fields, and both hashes.

Internal-standard reads remain separate from biological detections.

## 5. Identity and Hashing

All canonical IDs use full lowercase SHA-256 values generated from canonical
JSON arrays with explicit field order and Unicode normalization. The unhashed
provider identifiers remain in dedicated columns.

| Record | Stable identity components |
| --- | --- |
| Sample | provider, provider sample ID |
| Assay | provider, provider sample ID, contracted experiment role |
| Detection | assay ID, assignment method, uppercase sequence SHA-256 |
| Internal standard | assay ID, standard label, uppercase sequence SHA-256 |
| Anchor event | source family, provider, provider sample ID |
| Source file | provider, snapshot ID, normalized relative path, source content identity |

`scientific_content_sha256` covers normalized scientific values and excludes
activation timestamps. `source_row_hash` additionally covers the exact source
snapshot, source file, and row locator. A new snapshot with identical science
can therefore refresh provenance without being reported as a scientific
correction.

## 6. Normalization Contract

Add `preprocessing/anemone.py` and `scripts/normalize_anemone.py`.

The CLI shape is:

```bash
python scripts/normalize_anemone.py \
  --snapshot-id SNAPSHOT_ID

python scripts/normalize_anemone.py \
  --snapshot-id SNAPSHOT_ID \
  --execute

python scripts/normalize_anemone.py \
  --snapshot-id SNAPSHOT_ID \
  --execute \
  --activate
```

Default mode validates and reports the planned artifacts without writing them.
`--execute` publishes an immutable normalized bundle. `--activate` atomically
updates the local current pointer and is valid only with `--execute`.

Before parsing, the normalizer rechecks:

- manifest schema, complete status, provider, source family, and selection
  policy;
- contract version and contract SHA-256;
- snapshot directory confinement and absence of symlinks;
- every selected file's existence, byte size, SHA-256, role, and valid status;
- exactly one required interpreted file per sample;
- sample directory and TSV sample-name agreement.

Normalization then:

1. pivots sample and experiment key/value rows without discarding unknown keys;
2. parses `lat_lon` as source latitude then longitude and validates ranges;
3. parses the confirmed UTC collection date/time keys without inventing time
   precision or timezone offsets;
4. normalizes sequences to uppercase and hashes them;
5. maps each community file role to its fixed assignment method;
6. converts blank/`NA`/`N/A` copies-per-mL values to null;
7. keeps zero reads and zero supplied copies as valid numeric values;
8. derives deepest supplied taxon name/rank only from the ordered source ranks;
9. classifies controls only through reviewed metadata mappings;
10. sorts every output by its stable key before hashing and writing.

Unrecognized metadata keys remain in JSON and produce a review warning, not
data loss. Duplicate identities, inconsistent sample sets, impossible numeric
values, and malformed non-null coordinates/dates are errors. A reviewed control
or unknown sample may retain a null spatiotemporal value with an explicit issue;
it is preserved and receives no anchor event.

## 7. Normalized Bundle

Write immutable bundles under:

```text
data/normalized/anemone/snapshots/<normalization-id>/
  external_source_snapshot.parquet
  external_source_file.parquet
  edna_sample.parquet
  edna_assay.parquet
  edna_detection.parquet
  edna_internal_standard.parquet
  edna_anchor_event.parquet
  normalization_manifest.json

data/normalized/anemone/current.json
```

The normalization ID hashes the raw snapshot ID, contract SHA-256,
normalization schema version, output schema hashes, and ordered scientific row
hashes. Generation time is excluded. Repeating the same normalization is
idempotent; an existing ID with different content is a conflict.

The manifest records input snapshot and file hashes, normalization version,
artifact paths/hashes/schemas/row counts, sample and control counts, assignment
method counts, warnings, and validation results. Paths are relative to the
bundle. Credentials and request headers are never present.

## 8. Anchor Events

Add an eDNA anchor builder without changing existing CTD/SST identity rules.

- Event ID is deterministic from source family, provider, and provider sample
  ID.
- Source type is `edna_metabarcoding`.
- Date-only input remains date precision; the normalizer does not synthesize a
  midnight observation.
- Coordinates come only from the ANEMONE source metadata.
- Environmental depth is used only when supplied with a defined unit.
- Controls and unknown classifications receive no anchor event.
- No CTD or SST cross-source link is created in PR2.

## 9. Migration and Database Ownership

Add manual Alembic revision `20260901_0005_anemone_edna_corpus.py`, revising
`20260825_0004`. It creates the six new corpus tables with foreign keys, check
constraints, unique constraints, and indexes. `db.models` defines the same
tables for `CorpusBase.metadata.create_all()` and corpus reset behavior.

This matches the repository's bootstrap order: Alembic upgrades first, then
`init_db()` reconciles corpus metadata. The migration remains explicit because
Alembic's configured target metadata currently owns application tables only.
PR2 does not convert existing corpus tables to Alembic ownership.

Update `scripts/bootstrap_database.py::REQUIRED_TABLES` so readiness fails if
any eDNA or external-source table is absent.

## 10. Transactional Upsert and Corrections

Extend `scripts/load_db.py` with an optional exact normalization ID. Without an
explicit ID, it may use `current.json`; if neither exists, existing non-eDNA
loads continue and report eDNA as skipped.

PR2 uses the existing corpus advisory transaction lock but a dedicated eDNA
merge path:

1. insert immutable source snapshot and file rows;
2. reject any conflicting immutable row;
3. merge anchor events;
4. merge samples and assays by stable ID;
5. merge detections and standards by stable ID;
6. preserve `first_seen_snapshot_id`;
7. update `last_seen_snapshot_id`, source locators, current values, and hashes;
8. report scientific corrections separately from provenance-only refreshes;
9. mark records missing from the newly authoritative scope `active=false`;
10. never delete canonical or provenance rows.

For sample scope, reconciliation is limited to that provider sample. For run
scope, it is limited to that provider project/run. It cannot affect another
provider or run. Source `generated_at` is not treated as scientific observation
recency. A mutating load normally accepts only the operator-activated
normalization pointer; loading a different explicit bundle requires a separate
`--allow-anemone-noncurrent` flag and is reported as an override.

The dry-run plan reports inserts, unchanged rows, scientific corrections,
provenance refreshes, planned inactivations, and scope. Any duplicate key,
foreign-key mismatch, immutable-provenance conflict, or validation error rolls
back the complete eDNA transaction.

## 11. Lineage

Extend `ingestion/lineage.py` to include:

- PR1 ANEMONE snapshot and source-file records;
- every normalized eDNA artifact and its schema/content hash;
- source snapshot/file and source row locator for canonical records;
- eDNA table keys in the upsert dry-run plan;
- normalization manifest identity and activation state.

Every canonical row must trace to one selected interpreted file and a completed
PR1 snapshot. Aggregated sample/assay metadata records retain the contributing
source row-number list. Detection and standard rows retain one exact TSV row
number.

PR2 does not create retrieval-document or embedding traces.

## 12. Planned Files

| File | Change |
| --- | --- |
| `config.py` | Normalized ANEMONE bundle paths and normalization version |
| `preprocessing/anemone.py` | Manifest verification, normalization, validation, IDs, hashes, and bundle publication |
| `schema/anchor_event.py` | Deterministic eDNA anchor construction |
| `scripts/normalize_anemone.py` | Validate-only default and explicit publish/activate CLI |
| `db/models.py` | External-source and eDNA corpus models |
| `migrations/versions/20260901_0005_anemone_edna_corpus.py` | Additive schema migration |
| `scripts/bootstrap_database.py` | Required-table readiness checks |
| `scripts/load_db.py` | eDNA dry-run, transactional merge, and scoped inactivation |
| `ingestion/lineage.py` | Raw-to-normalized-to-database lineage and upsert planning |
| `tests/fixtures/anemone/` | Expanded sample, run, control, correction, and malformed fixtures |
| `tests/test_anemone_normalization.py` | Deterministic unit and bundle tests |
| `tests/test_load_db_upsert.py` | eDNA merge-plan and unit tests |
| `tests/test_lineage.py` | eDNA source-row trace tests |
| `tests/test_bootstrap_database.py` | Required-table and bootstrap checks |
| `tests/integration/test_anemone_postgres.py` | Migration, constraints, idempotency, correction, rollback, and inactivation |
| `docs/TESTING.md` | PR2 verification commands |
| `docs/ANEMONE_INTEGRATION_PLAN.md` | PR2 status and boundary |
| `handoff.md` | Implementation status and PR3 handoff |

No PR2 change belongs in retrieval, prompts, answer audit, API schemas/routes,
frontend, analysis/reliability, deploy templates, or GCP configuration.

## 13. Implementation Sequence

1. Expand synthetic fixtures with two samples, one explicit control, both
   assignment methods, null copies/mL, and unknown metadata.
2. Implement stable ID/hash helpers and PR1 snapshot verification.
3. Implement sample and assay metadata normalization.
4. Implement detection, taxonomy, and internal-standard normalization.
5. Implement cross-table validation, control handling, and eDNA anchors.
6. Publish deterministic immutable bundles and the optional active pointer.
7. Add ORM models and the additive migration.
8. Add external-source loading and dedicated eDNA transactional merge.
9. Add scoped non-destructive reconciliation and correction reporting.
10. Extend lineage and read-only upsert planning.
11. Run focused, full backend, migration, Ruff, dependency, and diff gates.

## 14. Test Matrix

Unit and local artifact tests must cover:

- manifest tampering, wrong contract hash, missing file, bad file hash, unsafe
  path, and symlink rejection;
- sample and run snapshots;
- stable IDs under input-row reordering;
- exact sample/assay joins and provider-qualified identities;
- coordinate/date parsing and precision preservation;
- environmental, explicit-control, and unknown classification;
- preservation of every control and unknown metadata key;
- separate QCauto and 95%-3NN detections;
- null, zero, negative, and malformed reads/copies behavior;
- full taxonomy JSON and deepest supplied rank selection;
- duplicate detection/standard key rejection without aggregation;
- deterministic bundle identity and atomic conflict handling;
- no writes in validate-only mode;
- anchor creation only for qualified environmental samples;
- exact source file and row locators in lineage.

Disposable PostgreSQL integration tests must cover:

- upgrade from revision `20260825_0004` and downgrade of PR2 tables;
- model/migration column, constraint, foreign-key, and index parity;
- first insert and identical second upsert;
- scientific correction with stable ID and changed scientific hash;
- provenance-only refresh without a scientific correction count;
- missing detection/sample handling through scoped `active=false`;
- preservation of unrelated providers/runs;
- immutable source snapshot/file conflict rejection;
- duplicate and foreign-key failure rollback;
- no deletion of prior provenance rows;
- bootstrap readiness and dry-run accuracy.

CI continues to use synthetic data and never contacts ANEMONE.

## 15. Acceptance Criteria

PR2 is complete when:

1. A valid completed PR1 sample or run snapshot produces the seven contracted
   normalized Parquet artifacts and one deterministic manifest.
2. Repeated normalization and repeated database upsert are idempotent.
3. Every canonical row has stable provider-qualified identity, scientific and
   source hashes, and exact snapshot/file/row lineage.
4. Both assignment methods and all controls are preserved separately.
5. Reads are never labeled or transformed as abundance; copies/mL remains
   source-supplied and nullable.
6. Corrections update stable current rows, provenance-only refreshes are
   distinguished, and missing scoped rows become inactive without deletion.
7. Malformed non-null coordinates/dates, impossible numeric values, invalid
   source hashes or relationships, and duplicate identities fail closed before
   partial publication or commit; missing control metadata remains explicit.
8. Migration/bootstrap checks pass on a disposable PostgreSQL/pgvector
   database and rollback leaves pre-PR2 tables intact.
9. The full backend coverage gate, Ruff, `pip check`, single Alembic head, and
   `git diff --check` pass.
10. The PR contains no retrieval, embedding, API, frontend, analysis, GCP,
    production-data, or credential mutation.

## 16. Non-Blocking Decisions for Later PRs

- The default presentation assignment method remains a PR3/PR4 decision; both
  are stored now.
- Detection and control thresholds remain a PR4 decision.
- CTD/SST spatial and temporal matching thresholds remain a PR4 decision.
- The initial production cohort and credential renewal process remain PR5
  decisions.
- Any source-specific control vocabulary not confirmed by fixtures remains
  `unknown` until reviewed. This does not block lossless PR2 ingestion but must
  be resolved before control-excluding analyses are enabled.
