# ANEMONE PR3 — Retrieval and Evidence Navigation Plan

> Status: implemented locally; review follow-ups open (2026-09-02)
> Dependency: ANEMONE PR1 acquisition and PR2 canonical ingestion
> Scope: retrieval documents, filtering, answer audit, read APIs, compact Data
> view, evidence navigation, provenance, and evidence export

## Implementation and verification

Follow-up review found three gaps: structured eDNA scope is not passed into
analysis-context selection, date-only end filters omit timestamped observations
on that date, and fallback artifact publication is not coordinated with the
committed database generation. Details and the prerequisite repair package are
in [the PR4 review and plan](ANEMONE_PR4_PLAN.md#1-pr3-review-and-entry-gate).
The existing tests pass but do not cover these cases; resolve them before
merge/acceptance or adding scientific analyses. No fixes were implemented in
the planning turn.

The builder, additive migration `20260902_0006`, database-wide materializer,
PostgreSQL/local filters, source-qualified prompt/audit behavior, read APIs,
CSV export, eDNA Data view, citation routes, and provenance validation are
implemented. The materializer has a dry-run default and is an explicit
post-load pipeline stage before embedding refresh and provenance publication.

Local verification: 524 backend tests passed with 6 service-gated skips and
75.39% aggregate coverage; all 6 PostgreSQL integration tests passed separately
on a clean, disposable pgvector/PostgreSQL 16 container. Frontend tests (12),
typecheck, production build, production dependency audit (zero vulnerabilities),
Ruff, `pip check`, and the single Alembic head passed. Synthetic browser checks
covered both-method default display, exact detection navigation, refresh,
Back/Forward, and invalid/missing destinations. No live source was downloaded,
no production migration or GCP change occurred, and no commit or push was made.

The eDNA API requires the migrated canonical database. Local retrieval remains
available from materialized fallback artifacts; the structured Data view does
not pretend to contain live data when that database is unavailable. PR4 and
PR5 remain deferred as listed below.

## 1. Outcome

PR3 makes the active ANEMONE MiFish corpus searchable, citable, inspectable,
and exportable as the distinct source family `edna_metabarcoding`.

The retrieval unit is one bounded community-summary document per active
sample, assay, and assignment method. PR2 currently contracts one assay per
sample, so this is one document per sample and method today while remaining
safe for future multi-assay data. Structured detections remain in PostgreSQL
and are not embedded one row at a time. A citation opens the exact eDNA sample,
assay, assignment method, contributing detection records, and immutable
source-file provenance.

PR3 does not calculate biodiversity indices, compare assignment methods,
apply control thresholds, infer absence, create CTD/SST links, download live
ANEMONE data, run a GCP job, or deploy production. Those remain PR4 and PR5.

## 2. Fixed Scientific and Product Decisions

- Source type is `edna_metabarcoding`; provider is `anemone`.
- It is never aliased to the existing shotgun `metagenome` source.
- `qcauto_target` and `qcauto_95pct_3nn_target` remain separate retrieval
  documents, filters, tables, URL states, citations, and exports.
- PR3 has no hidden default assignment method. When neither method is
  selected, both are returned and visibly labeled as separate records.
- Controls remain visible and labeled. No retrieval or Data-view default
  silently excludes them. `is_control = null` remains `unknown`.
- `read_count` is labeled **read count**, never abundance, biomass,
  concentration, or organism count.
- `copies_per_ml` is labeled **source-supplied copies/mL**, remains nullable,
  and is never computed or summed by PR3.
- A taxonomic assignment is called a detection record or assigned taxon. PR3
  does not convert a missing row into biological absence.
- Taxon filters are case-insensitive exact matches across the supplied common
  ranks and `assigned_taxon_name`. PR3 performs no synonym resolution or
  taxonomic reinterpretation.
- Only active PR2 canonical rows are exposed by research APIs and retrieval.
  Historical inactive rows remain available through administrative database
  and immutable provenance records.
- UI text is academic, direct, and minimal. Do not add marketing copy,
  introductory blurbs, redundant subheaders, or an “Evidence Navigator” label.

## 3. Retrieval Document Contract

### 3.1 Granularity and identity

Create one document for each active `(assay_id, assignment_method)` pair that
has at least one active detection. This is future-safe if ANEMONE later exposes
more than one assay for a sample.

```text
doc_id = edna_<assay_id>_<assignment_method>
source_type = edna_metabarcoding
sample_id = edna_sample.sample_id
event_id = edna_sample.anchor_event_id, when present
```

The current method names keep the identifier below the existing 128-character
database limit. Document ordering and content are deterministic.

### 3.2 Text content

Each document contains only source-supported facts:

- provider sample, project, and run identifiers;
- collection date/time and coordinates when supplied;
- sample kind and explicit control state;
- assay target gene, primer set, and sequencing method;
- exact assignment method;
- number of active detection rows;
- sum of source `read_count` values, labeled as such;
- number of detection rows with source-supplied copies/mL;
- a bounded list of the top 10 detection rows, ordered by `read_count`
  descending and then `detection_id`, with assigned taxon/rank and read count;
- direct limitations: read counts are not abundance, the two assignment
  methods are separate, and non-detection is not absence.

Do not calculate richness, diversity, similarity, occurrence, control
contamination, or ecological interpretation in this document. The embedded
text is bounded; the full structured detection set remains accessible through
the API.

### 3.3 Structured metadata

Extend the retrieval-document representation with:

- `active`;
- `provider`;
- `provider_project_id`;
- `provider_run_id`;
- `assay_id`;
- `assignment_method`;
- `sample_kind`;
- nullable `is_control`;
- `source_snapshot_id`;
- `metadata_json`.

`metadata_json` is deterministic canonical JSON and contains the document
format version, source-family label, source file IDs, a bounded list of the
featured detection IDs, and a sorted de-duplicated taxon term index for the
local fallback retriever. It contains no credential, Authorization value,
cookie, or local credential path.

The document format starts at `edna_retrieval_document_version = 1`. That
version participates in the document `source_row_hash`. The materializer
compares the prior and incoming title/text content separately, so a formatting
or semantic contract change invalidates the old embedding while a
provenance-only refresh does not trigger unnecessary embedding work.

### 3.4 Materialization and lifecycle

Do not build the production eDNA corpus from only `current.json`. PR2 permits
multiple authoritative sample/run scopes, while that pointer identifies only
one normalized bundle.

Add a database-backed materializer that:

1. reads all active eDNA samples, assays, and detections in one consistent
   database snapshot;
2. builds deterministic documents with a pure DataFrame/domain builder;
3. acquires the existing corpus advisory transaction lock;
4. upserts changed documents, preserves embeddings when only provenance
   metadata changes, and clears an embedding when its title/text changes;
5. marks only missing `source_type = 'edna_metabarcoding'` documents inactive;
6. refreshes FTS only for inserted or changed active documents;
7. atomically writes all active eDNA documents to separate local Parquet and
   JSONL fallback artifacts after the database transaction commits.

No canonical scientific or provenance row is deleted. Inactive derived
retrieval documents may retain their previous embedding, but every retrieval
path must filter `active = true`.

The default manual pipeline order becomes:

```text
validate -> ingest -> legacy retrieval docs -> analyses -> reliability
-> database backup -> canonical database upsert
-> eDNA retrieval materialization -> embedding refresh -> provenance publish
```

This ensures new or changed eDNA documents receive embeddings before the
provenance snapshot is published. If no active eDNA corpus exists, the
materializer writes an empty valid artifact and does not affect legacy docs.

## 4. Database Migration

Add one additive Alembic revision after `20260901_0005` and mirror it in
`db/models.py`.

Changes to `retrieval_document`:

- add the nullable metadata/filter columns in section 3.3;
- add `active BOOLEAN NOT NULL DEFAULT TRUE`;
- add indexes for `active`, `provider`, `assignment_method`, `assay_id`, and
  `(source_type, active, provider_project_id, provider_run_id)`;
- preserve every existing row as active during upgrade;
- remove only the new columns and indexes during downgrade.

Do not add an embedding or retrieval row per detection. Taxon filtering in
PostgreSQL uses an `EXISTS` query against active `edna_detection` rows joined
through the document's `assay_id` and `assignment_method`. The JSON taxon index
exists only to provide equivalent exact filtering in local fallback mode.

## 5. Retrieval and Prompt Behavior

### 5.1 Filter contract

Add the following optional filters consistently to `RetrieveRequest`,
`ChatRequest`, `/documents`, PostgreSQL retrieval, and local retrieval:

- `sample_id`;
- `provider`;
- `provider_project_id`;
- `provider_run_id`;
- `assignment_method`;
- `taxon`;
- `sample_kind`;
- nullable `is_control`;
- `lat_min`, `lat_max`, `lon_min`, and `lon_max`;
- existing `source_type`, `bay`, `time_from`, and `time_to`.

Coordinates must form a valid ordered bounding box when supplied. Identifiers
and assignment methods use strict allowlists or bounded identifier validation.
If an explicitly non-eDNA `source_type` is combined with an eDNA-only filter,
reject the request instead of silently ignoring the filter (HTTP 400 for
query endpoints; HTTP 422 for Pydantic-validated retrieve/chat bodies).

`provider=anemone` or any other eDNA-only filter constrains retrieval to
`edna_metabarcoding` even when `source_type` is omitted. Controls are included
unless `is_control` or `sample_kind` is explicitly supplied.

### 5.2 Source inference and answer audit

Register eDNA-specific terms such as `eDNA`, `environmental DNA`, `ANEMONE`,
`MiFish`, `metabarcoding`, `amplicon`, `QCauto`, `3NN`, `primer`, and `assay`.

Inference precedence is explicit:

- an eDNA-specific term requires `edna_metabarcoding`;
- Kraken, MetaEuk, shotgun, or explicit metagenome wording requires
  `metagenome`;
- if eDNA-specific wording is present, generic `taxa`, `taxonomy`, or
  `community` terms do not additionally require metagenome evidence;
- a question that explicitly names both source families may require both.

Apply the same vocabulary to answer-audit source coverage. Update the system
prompt to distinguish targeted MiFish eDNA detection records from shotgun
metagenome summaries and repeat the read-count limitation.

Existing metagenome analysis/reliability context must not be injected into an
eDNA-specific question merely because it contains words such as “diversity” or
“community.” PR4 will add source-qualified eDNA analyses.

### 5.3 Cross-source expansion boundary

PR3 must not create eDNA cross-source links. Until PR4 supplies reviewed
spatial, temporal, and methodological rules, linked-evidence expansion excludes
eDNA documents both as an origin and a target. Retrieval diagnostics state
that no reviewed cross-source expansion is available; they do not imply an
absence of related environmental data.

## 6. API Contract

All routes remain under the existing `data:read`, `evidence:search`, or
`provenance:read` permissions. Queries are parameterized, pagination is
bounded, sort fields are allowlisted, and sequences are omitted from list
responses unless explicitly requested.

### 6.1 eDNA data routes

| Route | Purpose |
| --- | --- |
| `GET /data/edna/catalog` | Active counts and filter values for providers, projects, runs, methods, sample kinds, time extent, and coordinate extent |
| `GET /data/edna/samples` | Paginated active sample rows with assay/detection counts separated by method |
| `GET /data/edna/samples/{sample_id}` | Exact sample metadata, control state, assays, method summaries, and source provenance |
| `GET /data/edna/assays/{assay_id}` | Exact assay method metadata, internal standards, method-separated counts, and provenance |
| `GET /data/edna/detections` | Paginated active detection records filtered by sample, assay, method, provider scope, taxon, control state, place, and time |
| `GET /data/edna/detections/{detection_id}` | One exact detection, full taxonomy and sequence, and source-row provenance |
| `GET /data/edna/controls` | Active known controls; unknown classifications remain separate and are not coerced into this result |
| `GET /data/edna/export` | Bounded CSV evidence export using the same explicit filters |

List endpoints default to 100 rows and cap at 500. Export is capped at 25,000
detection rows, returns `X-Export-Truncated`, and never silently exports a
different assignment method than requested.

The detection export includes:

- provider, project, run, sample, sample kind, and control state;
- collection date/time and coordinates;
- assay ID, target gene, primer set, and sequencing method;
- assignment method, detection ID, sequence hash, taxonomic ranks, assigned
  taxon/rank, read count, and nullable source-supplied copies/mL;
- snapshot ID, source file ID, source URL, source SHA-256, and source row
  locator.

No authentication secret or request header is included.
CSV columns remain stable for empty results. Formula-like source strings are
escaped for spreadsheet safety; numeric values retain their original types.

### 6.2 Retrieval response fields

Extend `SourceDocument` in Python and TypeScript with nullable:

- `provider`;
- `provider_project_id`;
- `provider_run_id`;
- `assay_id`;
- `assignment_method`;
- `sample_kind`;
- `is_control`;
- `source_snapshot_id`.

This keeps the citation drawer and deep-link builder independent of parsing
the narrative text.

## 7. Data View and Evidence Navigation

Add an `eDNA` tab to `/data`. It is a compact structured browser, not an
analysis dashboard.

The first view contains:

- direct filters for provider/project/run, assignment method, sample kind,
  taxon, collection date, and coordinate bounds;
- a small count strip for samples, assays, detection rows, and known controls;
- a paginated sample table;
- the selected sample and assay metadata;
- method-separated detection tables with read count and nullable
  source-supplied copies/mL;
- direct actions: `Provenance`, `Source`, and `Export CSV`.

Do not add richness charts, diversity charts, method-agreement scores, control
pass/fail badges, or ecological conclusions in PR3.

Bookmarkable URL state uses:

```text
/data?view=edna&sample_id=<sample_id>&assay_id=<assay_id>
  &assignment_method=<method>&detection_id=<detection_id>&taxon=<taxon>
```

Invalid identifiers, unsupported methods, inactive records, and missing
records display a direct error and never fall back to another sample or to the
metagenome Taxa view. Cold load, refresh, Back, and Forward must restore the
same supported state.

For an eDNA citation, `evidenceDeepLinks` returns:

1. `Provenance` for the retrieval document;
2. `eDNA sample` for the exact sample, assay, and assignment method;
3. `Detections` for the same method and any featured detection when present.

It must not emit the existing `Taxa profile` metagenome route. Keep the drawer
header concise: title, source type, method, sample/control state, and actions;
do not restore the removed “Evidence Navigator” heading or explanatory copy.

## 8. Provenance Contract

Extend lineage generation and the published provenance snapshot so every eDNA
retrieval document traces:

```text
citation/doc_id
  -> active retrieval document and document-format version
  -> canonical sample + assay + assignment-method detection set
  -> immutable normalized ANEMONE artifacts
  -> external source snapshot and exact source files
  -> source URL + SHA-256 + row locators
  -> embedding provider/model/dimension/time
```

The provenance trace must expose the source file IDs represented in the
document and the featured detection IDs. A missing referenced snapshot, file,
hash, or canonical record blocks provenance publication rather than producing
a partial successful trace.

The separate active eDNA retrieval Parquet/JSONL artifacts are included in the
manifest fingerprint and snapshot verification. Local and snapshot-backed
trace APIs must return equivalent identifiers and source hashes.

## 9. Implementation Work Packages

### A. Document builder and lifecycle

- Add a pure eDNA community-document builder with deterministic fixtures.
- Persist structured retrieval metadata and document version.
- Add the retrieval-document migration and indexes.
- Add database-backed all-active materialization and eDNA-only inactivation.
- Add separate local Parquet/JSONL fallback artifacts.
- Add the materialization and embedding stages to the default pipeline order.

### B. Retrieval, prompt, and audit

- Add eDNA filters to PostgreSQL and local retrieval.
- Exclude inactive documents in every search/list/count path.
- Add source inference precedence and source-qualified context gating.
- Update prompt semantics and deterministic answer-audit vocabulary.
- Block unsupported eDNA linked-evidence expansion until PR4.

### C. Read API and export

- Add strict Pydantic request/response models.
- Add catalog, sample, assay, detection, control, and detail queries.
- Add bounded, provenance-complete CSV export.
- Extend generic document/retrieve/chat responses with structured eDNA fields.

### D. Frontend and navigation

- Add API clients and TypeScript types.
- Add the compact `/data?view=edna` browser.
- Add exact sample/method/detection URL restoration and validation.
- Add eDNA citation links and concise evidence details.
- Preserve direct academic labeling and accessibility.

### E. Provenance and documentation

- Extend document lineage and published snapshot validation.
- Add eDNA trace rendering without exposing credentials.
- Update testing, security, roadmap, and handoff documentation.

## 10. Expected File Map

Likely new files:

- `retrieval/edna_document_builder.py`
- `scripts/materialize_edna_retrieval.py`
- `migrations/versions/20260902_0006_anemone_retrieval.py`
- `api/edna.py` or `api/edna_service.py`
- `tests/test_edna_document_builder.py`
- `tests/test_edna_retrieval.py`
- `tests/test_api_edna.py`
- `tests/integration/test_anemone_retrieval_postgres.py`
- `frontend/components/EdnaDataView.tsx`

Likely modified files:

- `db/models.py`
- `retrieval/document_builder.py`
- `retrieval/hybrid_retriever.py`
- `retrieval/local_retriever.py`
- `orchestration/unified.py`
- `orchestration/answer_audit.py`
- `api/schemas.py`
- `api/main.py`
- `api/provenance_snapshot_service.py`
- `ingestion/lineage.py`
- `scripts/load_db.py`
- `scripts/run_pipeline.py`
- `frontend/types.ts`
- `frontend/lib/api.ts`
- `frontend/lib/citation-navigation.ts`
- `frontend/lib/citation-navigation.test.ts`
- `frontend/app/data/page.tsx`
- `docs/ANEMONE_INTEGRATION_PLAN.md`
- `docs/ROADMAP.md`
- `docs/SECURITY.md`
- `docs/TESTING.md`
- `handoff.md`

Keep the eDNA database queries in a focused service module instead of further
growing `api/main.py`; route registration may remain in `api/main.py` if a new
router would cause unnecessary authorization-policy churn.

## 11. Test Matrix

### Unit and scientific-contract tests

- exactly one document per active assay/method and none for an empty method;
- stable IDs, ordering, hashes, and JSON across shuffled inputs;
- controls and unknown classifications remain visible and labeled;
- assignment methods never merge;
- top-10 detection ordering is deterministic;
- read count and supplied copies/mL wording is exact;
- no richness, abundance, biomass, absence, or ecological inference wording;
- malformed method, taxon, ID, date, or coordinate filters fail closed.

### PostgreSQL integration tests

- upgrade, downgrade, and re-upgrade from the current Alembic head;
- legacy retrieval rows remain active after migration;
- materialization across at least two provider scopes retains both scopes;
- repeated materialization is idempotent and preserves embeddings;
- a scientific correction changes text/hash and clears only that embedding;
- provenance-only changes refresh metadata and the document hash as specified;
- canonical inactivation makes only corresponding eDNA documents inactive;
- all SQL retrieval modes exclude inactive rows;
- provider/method/taxon/control/bounding-box/time filters return exact rows;
- taxon matches a non-featured detection through the structured table join;
- eDNA documents are never returned as cross-source linked evidence in PR3.

### API tests

- catalog counts and filter values use active rows only;
- list pagination, allowlisted sorting, and validation boundaries;
- exact sample, assay, detection, controls, and 404 behavior;
- no silent method or control filtering;
- CSV headers, row counts, truncation header, URL/hash/locator fields, and
  credential absence;
- retrieve/chat filters propagate to both backends;
- eDNA-specific questions produce the correct expected source family;
- metagenome-only and explicit mixed-source questions remain correct;
- eDNA questions do not receive unrelated metagenome analysis context;
- answer audit resolves eDNA citations and reports missing eDNA evidence.

### Frontend tests

- citation deep links target `view=edna`, never `view=taxa`;
- valid sample/assay/method/detection URL state survives cold load and refresh;
- invalid or inactive targets show a direct error without fallback;
- browser Back/Forward restores filters and selected evidence;
- both assignment methods and controls are visibly distinguished;
- table pagination and export retain active filters;
- keyboard focus, labels, and narrow-viewport overflow remain usable;
- no redundant evidence, Data-view, or promotional copy is introduced.

### Regression gates

- full backend tests and coverage threshold;
- focused disposable pgvector/PostgreSQL integration tests;
- Ruff and `pip check`;
- one Alembic head;
- frontend tests, typecheck, production build, and production dependency audit;
- `git diff --check` and secret-pattern scan;
- CI remains synthetic and makes no ANEMONE or GCP network request.

## 12. Acceptance Criteria

PR3 is complete only when:

1. Active ANEMONE evidence is retrievable as `edna_metabarcoding` in both
   PostgreSQL and local fallback modes.
2. One bounded document exists per active assay/method; no detection-level
   embedding explosion occurs.
3. Both assignment methods and all control states remain explicit with no
   hidden default.
4. Provider, project/run, method, taxon, control, place, and time filters are
   consistent across documents, retrieve, chat, API, export, and URL state.
5. A cited eDNA document opens the exact sample/method evidence and complete
   source snapshot/file/hash/row provenance.
6. Bookmarkable eDNA destinations pass cold-load, refresh, Back, and Forward
   browser tests and never route to the metagenome Taxa view.
7. Answer inference, prompt wording, and trust audit distinguish eDNA from
   shotgun metagenome evidence.
8. Inactive canonical rows and derived documents cannot appear in research
   search, APIs, counts, or exports.
9. No PR4 analysis or unreviewed cross-source link is introduced.
10. No live ANEMONE download, database migration execution, GCP mutation, or
    production deployment occurs as part of the PR.
11. All unit, integration, API, browser, security, migration, and regression
    gates in section 11 pass.

## 13. Explicitly Deferred to PR4 and PR5

PR4 owns richness/diversity/similarity calculations, assignment-method
agreement, control/internal-standard interpretation, detection history,
environmental association, and reviewed spatial/temporal CTD/SST linkage.

PR5 owns credential regeneration, bounded live inventory/download, Cloud Run
Job and Secret Manager configuration, pilot-cohort approval, Cloud SQL
migration/load, embedding/evaluation execution, deployment, and release
`v0.4.0`.
