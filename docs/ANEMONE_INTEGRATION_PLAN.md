# ANEMONE eDNA Integration Plan

> Status: PR1–PR5 completed and deployed in `v0.4.0` on 2026-09-03. This is the
> implementation plan and historical decision record; deployment evidence is in
> [`RELEASE_0.4.0_OPERATIONS.md`](RELEASE_0.4.0_OPERATIONS.md). Classification
> and full researcher acceptance remain next-patch work.
> Released: `v0.4.0`
> Source family: `edna_metabarcoding`
> Initial provider: `anemone`

## 1. Objective

Integrate ANEMONE DB MiFish environmental-DNA metabarcoding evidence into
OCEAN Platform as a scientifically distinct source family. The integration
must preserve sampling, laboratory, taxonomic-assignment, quality-control,
and file provenance so researchers can inspect and cite the evidence used in
analysis and generated answers.

ANEMONE data must not be merged into the existing `metagenome` source type.
The current source represents shotgun Kraken/MetaEuk summaries; ANEMONE uses
targeted MiFish metabarcoding. The canonical source type is therefore
`edna_metabarcoding`, while `anemone` identifies the provider.

## 2. Verified Source Shape

A bounded authenticated inspection on 2026-09-01 confirmed that an ANEMONE
MiFish sample directory contains:

| File role | Observed file |
| --- | --- |
| Forward reads | `*.forward.fastq.xz` |
| Reverse reads | `*.reverse.fastq.xz` |
| QCauto community | `community_qc_target.tsv.xz` |
| QCauto/95%-3NN community | `community_qc3nn_target.tsv.xz` |
| Internal standards | `community_standard.tsv.xz` |
| Experiment metadata | `experiment.tsv.xz` |
| Sample metadata | `sample.tsv.xz` |
| Derived presentation assets | Taxonomic word-cloud PNG files |

The community tables contain the sample name, a full taxonomic hierarchy,
amplicon sequence, read count, and nullable copies-per-milliliter value.
Sample metadata includes coordinates, local/UTC collection times, temperature,
salinity, sample volume, collection and filtration details, and storage
conditions. Experiment metadata includes the target gene, primers, PCR
conditions, library layout, sequencing instrument, methods, and quantitative
internal standards.

The inspected MiFish directory exposed one ANEMONE team, ten named project
directories from 2019 through 2023, and multiple sequencing runs. One inspected
run contained 80 sample/control directories. This is sufficient to design a
bounded adapter but not to estimate the size of the complete archive.

No credential value, authenticated response, or downloaded scientific source
file is committed to the repository. Any password shared during discovery must
be regenerated before implementation or deployment.

## 3. MVP Boundaries

### Included

- MiFish ANEMONE sample and experiment metadata.
- Both community taxonomic-assignment tables.
- Internal-standard records.
- Explicit sample/control classification.
- Immutable source manifests, ETags, Last-Modified values, sizes, and SHA-256
  hashes for downloaded files.
- Structured PostgreSQL data, analysis artifacts, retrieval documents,
  citations, evidence navigation, and research exports.
- Manual bounded execution locally and through Cloud Run Jobs.

### Excluded

- Bioinformatic processing of raw FASTQ reads.
- Default mirroring of FASTQ files.
- Unbounded recursive download of `/dist/`, a complete locus, team, or project.
- Automated password renewal or unattended scheduled synchronization.
- Treating read counts as organism abundance or biomass.
- Collapsing QCauto and 3NN results into one unversioned taxonomic assignment.
- Cross-source ecological claims without explicit spatial, temporal, and
  methodological qualification.

## 4. Delivery Sequence

| PR | Deliverable | Dependency | Release effect |
| --- | --- | --- | --- |
| PR1 | Secure bounded acquisition and executable raw-data contract | None | No database, retrieval, UI, or live-data mutation |
| PR2 | Canonical eDNA schema, normalization, provenance, and upsert | PR1 | New regenerable corpus tables and migrations |
| PR3 | Retrieval, trust audit, API, Data view, and evidence navigation | PR2 | ANEMONE evidence becomes searchable and citable |
| PR4 | Biodiversity analysis and reliability workflows | PR3 | Research analyses and qualified cross-source evidence |
| PR5 | GCP job, bounded pilot import, evaluation, deployment, and `v0.4.0` | PR1–PR4 | Production data-plane and release change |

## 5. PR1 — Secure Acquisition and Raw Contract

Implementation status (2026-09-01): the versioned contract, strict sample/run
inventory, credential-safe client, interpreted-file transfer and validation,
content-addressed snapshot publication, CLI, and synthetic test server are
implemented. PR1 does not include a live download or any database, retrieval,
frontend, GCP, or production mutation.

### Goal

Provide a safe, repeatable, read-only-by-default command that inventories and
downloads explicitly scoped ANEMONE interpreted files, verifies them, and
publishes a content-addressed local snapshot manifest. PR1 stops before
normalization or database loading.

### Operator flow

1. Regenerate a short-lived ANEMONE download password.
2. Store it outside the repository in a permission-restricted file or provide
   it interactively.
3. Inventory one exact sample or sequencing-run URL.
4. Review file roles, counts, byte estimates, and limits.
5. Execute the bounded interpreted-file download.
6. Verify the immutable snapshot manifest and rerun idempotently.

The command must be dry-run/inventory-only by default. A distinct `--execute`
flag is required before writing downloaded source files.

Example shape; exact flag names may change only if tests and this document are
updated together:

```bash
python scripts/sync_anemone.py \
  --scope-url https://db.anemone.bio/dist/MiFish/ANEMONE/PROJECT/RUN/SAMPLE/ \
  --inventory

python scripts/sync_anemone.py \
  --scope-url https://db.anemone.bio/dist/MiFish/ANEMONE/PROJECT/RUN/SAMPLE/ \
  --execute
```

The credential value must never be accepted as a command-line flag.

### Supported scope

PR1 supports exact sample and sequencing-run URLs beneath:

```text
https://db.anemone.bio/dist/MiFish/ANEMONE/
```

It rejects the `/dist/` root, locus root, team root, project root, another
origin, plain HTTP, query-bearing traversal links, and parent-directory links.
Project and complete-database acquisition remain later, operator-reviewed
extensions after a manifest-only size audit.

### Default file selection

Downloaded by default:

- `sample.tsv.xz`
- `experiment.tsv.xz`
- `community_standard.tsv.xz`
- `community_qc_target.tsv.xz`
- `community_qc3nn_target.tsv.xz`

Inventoried but not downloaded by default:

- paired FASTQ files
- word-cloud PNG files
- unknown files

An unexpected file is recorded in the inventory and blocks execution until a
contract update or explicit reviewed exclusion is supplied. FASTQ download is
not part of PR1's supported execution contract.

### Credential contract

Credential resolution order:

1. A password file path supplied through configuration; the path is not a
   secret and the file must not be inside the repository.
2. A protected environment variable for isolated local use.
3. An interactive non-echoing prompt when a TTY is available.

The production design target is a Secret Manager value mounted as a file.
Credentials must not appear in commands, exception messages, logs, manifests,
URLs, pipeline notes, test snapshots, or process listings. Authentication
failures report only the HTTP status and scope, never request headers.

Planned configuration names:

```text
ANEMONE_BASE_URL
ANEMONE_DOWNLOAD_USERNAME_FILE
ANEMONE_DOWNLOAD_PASSWORD_FILE
ANEMONE_DOWNLOAD_USERNAME
ANEMONE_DOWNLOAD_PASSWORD
ANEMONE_MAX_FILES
ANEMONE_MAX_BYTES
```

File-backed credentials are preferred. Direct environment values are a local
fallback and must not be included in debug/configuration payloads.

### Acquisition behavior

- Use HTTPS Basic authentication through a Python client; do not construct a
  shell command containing the username or password.
- Send a stable, descriptive user agent.
- Traverse only same-origin child links below the validated scope.
- Process sequentially with bounded retry/backoff; do not crawl concurrently.
- Stream downloads to `*.part` files.
- Resume only when the server confirms byte-range semantics and the source
  validator is unchanged.
- Validate XZ integrity before publishing a file.
- Parse TSV headers before publishing the snapshot.
- Reject path traversal, symlinks, absolute output paths, redirects to another
  origin, and duplicate normalized paths.
- Apply explicit maximum-file and maximum-byte limits before execution.
- Rename the completed staging directory atomically to its snapshot ID.
- Never replace or mutate an earlier complete snapshot.

### Raw contract

Add `data_contracts/anemone_mifish.json` with:

- supported contract version;
- allowed source origin and path prefix;
- supported scope levels;
- known file roles and required/optional status;
- expected compression and media type;
- required TSV columns;
- allowed nullable fields;
- identifier and date-time rules;
- numeric constraints for reads, copies/mL, coordinates, volumes,
  temperature, and salinity;
- known metadata keys and unit interpretations;
- supported assignment-method labels;
- snapshot limits and unexpected-file behavior.

PR1 validates structure only. Scientific normalization and decisions such as
control exclusion or choosing an assignment method belong to PR2 and PR4.

### Manifest contract

Each inventory and completed snapshot records:

```text
schema_version
source_provider
source_family
scope_url
generated_at
mode
contract_version
contract_sha256
selection_policy
limits
file_count
total_bytes
collection_sha256
files[]
  relative_path
  source_url
  role
  selection_status
  size_bytes
  etag
  last_modified
  sha256
  validation_status
  downloaded_at
issues[]
```

The manifest must not contain a username, password, Authorization header,
cookie, local credential path, or signed URL. Remote size may be unknown; the
downloaded byte count becomes authoritative after execution.

### Local paths

```text
data/raw/anemone/inventory/
data/raw/anemone/staging/
data/raw/anemone/snapshots/<snapshot-id>/
data/provenance/anemone/
```

Generated source snapshots remain ignored by git. Small synthetic fixtures
belong under `tests/fixtures/anemone/`.

### Expected code changes

| File | Planned change |
| --- | --- |
| `config.py` | ANEMONE paths, origin/prefix, safe limits, and credential-file configuration |
| `data_contracts/anemone_mifish.json` | Versioned source and TSV contract |
| `ingestion/anemone.py` | Scope validation, listing parser, downloader, XZ/TSV validation, manifest builder |
| `scripts/sync_anemone.py` | Read-only-default CLI and structured result output |
| `tests/test_anemone_ingestion.py` | Unit and local HTTP integration tests |
| `tests/fixtures/anemone/` | Synthetic directory listings and compressed TSV fixtures |
| `.env.example` | Names and safe descriptions only; no credential values |
| `.gitignore` | Generated ANEMONE inventories, staging files, and snapshots |
| `docs/SECURITY.md` | Credential and authenticated-download boundary |
| `docs/TESTING.md` | PR1 verification commands and fixture policy |
| `handoff.md` | Implementation status after the PR is complete |

PR1 does not modify database models, migrations, retrieval code, prompts,
frontend routes, GCP job definitions, or live data.

### Implementation order

1. Add synthetic directory/TSV fixtures and the versioned JSON contract.
2. Add configuration parsing and strict scope/link validation.
3. Implement deterministic directory inventory and file-role classification.
4. Implement credential-safe streaming transfer, limits, and resume handling.
5. Add XZ/TSV validation, collection hashing, and immutable snapshot publish.
6. Add the CLI, JSON result contract, documentation, and full negative tests.

Each step should leave the targeted tests passing. Live authenticated access is
an operator smoke test after local fixtures pass; it is not a CI dependency.

### Failure behavior

Execution fails closed on:

- missing or expired credentials;
- redirect outside the approved origin/prefix;
- unsupported scope;
- file/byte limit exceeded;
- missing required interpreted file;
- unexpected source file without a reviewed policy;
- decompression or TSV schema failure;
- partial transfer, source validator change during resume, or checksum failure;
- duplicate sample-relative path;
- attempted secret serialization.

Failure leaves prior snapshots unchanged. Staging files remain identifiable for
operator review or safe cleanup, but are never treated as complete evidence.

### Test plan

Tests use a local Basic-auth HTTP server and synthetic CC0-shaped fixtures.
CI must not contact ANEMONE or require a live credential.

Required coverage:

- exact sample and run scope acceptance;
- root/project/foreign-origin/path-traversal rejection;
- inventory parsing and deterministic ordering;
- default interpreted-file selection;
- FASTQ and PNG inventory-only behavior;
- Basic-auth success, 401/403 redaction, and no credential serialization;
- maximum-file and maximum-byte enforcement before mutation;
- interrupted download and valid/invalid resume behavior;
- XZ integrity and required TSV-column validation;
- unknown file and missing required file failures;
- ETag/Last-Modified change detection;
- deterministic collection hash;
- idempotent repeated execution;
- atomic snapshot publication and prior-snapshot preservation;
- JSON output suitable for later Cloud Run Job capture.

### Acceptance criteria

PR1 is complete only when:

1. Inventory mode performs no source-file writes.
2. Execution downloads only the five contracted interpreted TSV roles.
3. No credential can appear in `ps`, logs, exceptions, JSON, manifests,
   fixtures, git history, or `git grep` results.
4. A valid sample fixture produces a deterministic completed manifest.
5. A valid run fixture remains within explicit limits and produces one
   deterministic collection manifest.
6. Rerunning against unchanged validators performs no redundant download and
   produces the same collection hash.
7. Changed validators produce a new snapshot without overwriting the old one.
8. Every negative security and corruption test fails closed.
9. Backend tests, Ruff, `pip check`, and `git diff --check` pass.
10. The PR description states that it causes no database, GCP, retrieval, UI,
    or production data mutation.

## 6. PR2 — Canonical Schema and Ingestion

Implementation status (2026-09-02): deterministic normalization, immutable
bundle publication and activation, additive ORM/migration schema, exact
source-row lineage, read-only planning, transactional merge, correction
classification, and provider-scoped non-destructive inactivation are
implemented. The fixed PR2 specification is in
[`docs/ANEMONE_PR2_PLAN.md`](ANEMONE_PR2_PLAN.md). PR2 adds normalized
Parquet/PostgreSQL tables for:

- `edna_sample`
- `edna_assay`
- `edna_detection`
- `edna_internal_standard`
- external source-file/snapshot provenance

Stable IDs must include provider identity. Detection keys must preserve sample,
assay, assignment method, and sequence hash. QCauto and 3NN remain separate.
Taxonomic ranks most often queried directly receive indexed columns; the full
rank record remains preserved. Nullable copies/mL must not be derived from
reads unless a reviewed calibration implementation is added.

It also adds external snapshot/file provenance, scientific and source hashes,
exact source-row locators, deterministic anchor events, immutable normalized
bundles, and a dedicated transactional merge. Stable current rows are updated
for corrections; records missing from the newly authoritative sample/run scope
become inactive without deletion. Immutable raw snapshots remain the historical
record.

PR2 does not make ANEMONE retrievable or visible in the frontend.

Acceptance requires idempotent repeated upserts, correction-safe versioning,
control preservation, timestamp/coordinate validation, migration tests, and a
complete raw-to-row provenance trace.

## 7. PR3 — Retrieval and Evidence Navigation

The fixed implementation specification is in
[`docs/ANEMONE_PR3_PLAN.md`](ANEMONE_PR3_PLAN.md). Implemented and deployed:

- register `edna_metabarcoding` in source inference and answer auditing;
- build one community-summary retrieval document per sample/assignment method;
- retain structured species detections in tables instead of generating one
  embedding per sequence row by default;
- add provider, assignment-method, taxon, place, and time filters;
- add eDNA catalog, table, sample, assay, control, and detection APIs;
- add a compact eDNA Data view;
- link citations to exact sample/detection and provenance records;
- include ANEMONE source URL, snapshot, file hash, and method in exported
  evidence.

PR3 also adds the post-load materialization pipeline stage, content-aware local
embedding-cache invalidation, exact URL restoration and pagination, and a
publication gate for incomplete eDNA source/row/artifact provenance. Verification
results are recorded in the PR3 specification. The patch and its follow-up
repairs were subsequently deployed through PR5 in v0.4.0.

Acceptance requires source-specific retrieval tests, citation/trust-report
coverage, bookmarkable evidence destinations, cold-load/refresh browser tests,
and no silent routing of ANEMONE evidence to the existing metagenome view.

PR3 has no hidden default assignment method: both methods remain separate and
visible unless a researcher explicitly filters to one. It materializes the
retrieval corpus from all active canonical database rows rather than only the
latest normalized-bundle pointer, excludes inactive documents from every
search path, and does not enable eDNA cross-source expansion before PR4.

## 8. PR4 — Scientific Analysis and Reliability

The detailed recipe, mathematical definitions, control policy,
environmental gates, file map, and acceptance tests are in
[`ANEMONE_PR4_PLAN.md`](ANEMONE_PR4_PLAN.md). Its prerequisite PR3 fixes are
implemented with regression tests: structured source-qualified context, UTC
date intervals, and generation-safe fallback publication.

PR4 implements outputs for:

- occurrence and detection history;
- richness, Shannon, Simpson, and evenness;
- Jaccard presence/absence similarity;
- Bray-Curtis read-composition dissimilarity;
- spatial and temporal community turnover;
- QCauto/3NN agreement and taxonomic-resolution comparison;
- negative-control and internal-standard reports;
- environmental associations using ANEMONE metadata;
- qualified links to CTD and SST evidence.

Analyses remain separated by assignment method, assay/locus, and measurement
semantics. Read count is not labeled abundance or biomass. Copies/mL is used
only when supplied and valid. Control exclusion is explicit and reversible.

The dedicated eDNA linker measures spatial distance, requires reviewed
observation coordinates/depth/time/domain, verifies SST footprint/valid
coverage, and records qualification/rejection reasons. Typed observations
are supplied explicitly with `run_edna_analysis.py --environment`; legacy
time-only expansion remains disabled for eDNA. Nationwide ANEMONE records
cannot be linked to regional SST merely by date. No live profile is enabled.

Acceptance requires deterministic scientific fixtures, statistical tests,
method and limitation text in artifacts, exportable tables, and reviewed
evaluation questions.

Implemented scope refinement: PR4 provides descriptive read-composition metrics
and environmental effect sizes, not automatic significance/causal claims or
predictive reliability scores. Statistical implementations are verified with
analytic fixtures; study-specific inference, replicate models, rarefaction,
ordination, and automated contamination removal remain later research work.
Environmental linkage stays disabled without a reviewed profile and verified
position/time/coverage metadata. Missing matches do not block the other reports.

## 9. PR5 — GCP Pilot and v0.4.0 Release

The current audit, entry gates, implementation sequence, and release checklist
are in [`ANEMONE_PR5_PLAN.md`](ANEMONE_PR5_PLAN.md). Output-integrity,
historical-citation, and pre-ranking cohort-filter findings were fixed before
release. Storage-safe object publication, bounded job tooling, real provider/
GCS/Cloud Run checks, and limited-scope release approval were completed for
v0.4.0. Full classification and researcher acceptance remain deferred.
See [`../deploy/gcp/ANEMONE_PILOT.md`](../deploy/gcp/ANEMONE_PILOT.md).

PR5 delivered a manually executed `ocean-anemone-process` Cloud Run Job for
credential-free downstream processing. The separate acquisition template was
retained but not deployed or granted download credentials. The implementation
includes:

- a dedicated least-privilege job identity or reviewed `ocean-jobs` extension;
- Secret Manager-mounted username/password files;
- local staging and generation-conditional immutable publication to the
  scientific-data bucket; bucket mounts may serve immutable reads, not act as
  a POSIX publication mechanism;
- one task, zero automatic retries, explicit timeout, object/byte limits, and
  a safe inventory-only default;
- raw objects under `raw/anemone/` and immutable provenance snapshots;
- no in-process execution from the serving application.

Rollout order:

1. Inventory one approved sample and run.
2. Review total files/bytes and source-method metadata.
3. Download interpreted files only.
4. Run PR2 normalization and dry-run upsert.
5. Back up and migrate Cloud SQL.
6. Load a bounded geographic/project pilot.
7. Refresh embeddings separately.
8. Run ANEMONE-specific and cross-source evaluation questions.
9. Verify evidence navigation and research exports.
10. Deploy, record immutable build/job/revision evidence, and release `v0.4.0`.

The ten-day password lifetime makes this a manual operator workflow until
ANEMONE provides a suitable long-lived machine-access mechanism or an approved
credential-renewal procedure exists.

## 10. Cross-PR Decisions

The following decisions are fixed unless this plan is explicitly revised:

- Source type is `edna_metabarcoding`; provider is `anemone`.
- Interpreted data is the MVP ingestion boundary.
- FASTQ is referenced and inventoried, not mirrored or processed by default.
- Both taxonomic-assignment outputs are preserved.
- Source snapshots are immutable and content-addressed.
- Secrets never enter repository files, command arguments, manifests, or logs.
- Data acquisition and database mutation remain separate jobs.
- Structured taxon rows remain queryable without embedding every row.
- Scientific claims expose assignment method, controls, units, and linkage
  thresholds.
- UI labels remain academic, direct, and minimal.

## 11. Open Decisions Before PR4/PR5

- Initial pilot selection: Onagawa/Miyagi bounding region, one ANEMONE project,
  or another explicitly reviewed cohort.
- Reviewed thresholds for negative controls and low-read detections.
- Approved spatial and temporal thresholds for CTD/eDNA and SST/eDNA links.
- Whether selected FASTQ files require separate archival for a future
  reproducibility study.
- Full-download size, cost, rate-limit, and provider-contact review.
- Credential renewal ownership and operational schedule.

These decisions do not block PR3.
