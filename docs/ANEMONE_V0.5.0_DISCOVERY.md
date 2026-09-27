# ANEMONE full-catalogue investigation — 2026-09-17

Status: catalogue enumeration, acquisition of all 45,144 files, integrity checks,
processed-table profiling and current-validator audit are complete. No data has
been imported into OCEAN production.

This follows the user's authorization to download all accessible data and use
external storage. It updates the assumptions in the [v0.5.0 plan](ANEMONE_V0.5.0_PLAN.md).
Machine-readable counts are in [discovery metrics](ANEMONE_V0.5.0_DISCOVERY_METRICS.json).

## Archive scope and location

The authenticated [`/dist/` catalogue](https://db.anemone.bio/dist/) exposes
one locus (`MiFish`), one team (`ANEMONE`), ten projects and 19 sequencing runs.
All 3,498 sample directories were enumerated successfully, with no unvisited
branches or files found outside sample directories in the observed hierarchy.

| File type | Files | Compressed/file bytes |
| --- | ---: | ---: |
| Processed TSVs | 17,490 | 25,974,844 |
| Paired FASTQ files | 6,996 | 28,778,157,936 |
| Wordcloud PNGs | 20,490 | 6,751,836,829 |
| Provider README files | 168 | 10,752 |
| **Total** | **45,144** | **35,555,980,361** |

Total payload is **35.56 decimal GB / approximately 33.11 GiB**, excluding
OCEAN's manifests and investigation outputs. Every sample directory contains
five interpreted TSVs and two FASTQ files. Six wordcloud images are listed for
3,415 directories; 83 directories have none. No nontarget TSVs are exposed by
this catalogue, despite their inclusion in the provider's general documentation.
Their absence here is a coverage fact, not a download failure.

The archive destination is
`/Volumes/VIDEOS/ANEMONE-OCEAN/2026-09-17/dist/`, preserving provider-relative paths.
The `VIDEOS` volume and `LaCie` share external storage; LaCie's root ACL prevents
creating new directories, so its permissions were left intact. The new folder
on `VIDEOS` was used with the user's storage authorization.

All 45,144 source files are stored there. The TSV, PNG and README destination
SHA-256 hashes were checked against acquisition hashes before removing this
task's duplicate cache files. Acquisition state and source-listing copies are
retained under the ignored `.cache/anemone-v050/` directory and exported beside
the archive. The archive root includes `README.md`, `manifest.jsonl.gz`,
`archive-summary.json`, catalogue listing evidence, audit summaries and SQLite
ledger backups. The manifest records every source URL, relative path, byte size,
locally computed SHA-256 and available HTTP version headers. Its own SHA-256 is
recorded in the summary and repository metrics. These are local integrity hashes,
not provider-published checksums. No password is stored in these archive artifacts,
repository documents or manifests.

This is a copy of the accessible distribution tree, not a claim of access to
ANEMONE's unpublished or internal database. The provider's public homepage
marks ANEMONE data CC0; preserve attribution and acquisition provenance.

## What the complete processed dataset contains

| Measure | Result | Interpretation |
| --- | ---: | --- |
| Provider sample/run occurrences | 3,498 | Unique directory/source identifiers, not necessarily independent physical samples |
| Distinct `samp_name` values | 3,318 | 180 names occur twice across source occurrences; equivalence needs explicit modeling |
| Collection dates in UTC | 2017-12-18 through 2023-12-16 | Collection time, not download or publication time |
| Records with coordinates | 3,174 | All also supply an eight-character `worldmesh` value |
| Metadata labeled `blank sample` | 323 | Explicit provider blank evidence |
| Negative-control README notices | 168 | 148 overlap the blank metadata; 20 have generic `metagenome` metadata |
| Union of explicit blank/negative-control evidence | 343 | Source records with control evidence; does not automatically approve classification in OCEAN |
| Sequencing platforms | 1,809 MiSeq; 1,689 NextSeq 500 | Retain assay/protocol distinctions |

The original user-provided reference TSV exactly matches the decompressed
archived QCauto+3-NN table for the Ishinomaki Kotakehama sample: both SHA-256
values are `e9923f5b0251ec30d61c6b22347c0b0040d6aec4f444e83f0e67975a61defb16`.
Its actual sample, experiment and standard files are now available alongside it;
no synthetic companion metadata is needed for a future real import.

| UTC collection year | Source occurrences | Distinct reported sample names | Occurrences with explicit control evidence |
| --- | ---: | ---: | ---: |
| 2017 | 2 | 2 | 0 |
| 2018 | 12 | 12 | 1 |
| 2019 | 178 | 177 | 35 |
| 2020 | 946 | 901 | 81 |
| 2021 | 1,051 | 1,049 | 115 |
| 2022 | 944 | 812 | 70 |
| 2023 | 365 | 365 | 41 |

Use collection metadata for time filtering: project/run labels are not reliable
substitutes for collection year.

All 20 README-labeled records with generic `metagenome` metadata also lack an
`NC` suffix in their sample names. The generic metadata is not an environmental
classification. Importing such records as environmental based on name or that
label would overlook the provider's explicit negative-control notice.

All 180 repeated-name pairs have matching collection-time and coordinate metadata;
45 pairs were sequenced on different platforms. Only one pair has identical
sequence/read-count sets, and both of those target tables are empty. Thus the
repeated names cannot be removed as identical-file duplicates. Preserve their
separate assay/run evidence while confirming the physical-sample linkage. Every
nonempty table's `samplename` matches its source directory identifier.

Of the 324 records lacking coordinates, 323 are metadata-labeled blanks and
one is a generic metagenome record. Keep them as source evidence even when they
cannot participate in spatial analyses. A filename is not a replacement for
missing coordinates.

All coordinate values match centres of a regular grid with latitude step 1/12
degree and longitude step 1/8 degree. This is an observed numeric pattern,
consistent with the accompanying `worldmesh` field; the provider's intended
precision/disclosure semantics remain unconfirmed. Do not assume exact sample
positions or use precise nearest-station distances without accounting for that
uncertainty. Bounds are 17.45833333–45.54166667 latitude and
123.8125–148.6875 longitude; these bounds do not establish uniform coverage of
the enclosed region. The 3,174 coordinate-bearing records describe 216 distinct
reported coordinate/grid-cell values, not necessarily 216 exact stations.

Optional environmental metadata also needs field-level validation. `salinity`
is present in 2,132 records: 2,130 numeric values range from 0.01 to 4.2, while
two raw values are malformed (`3..44` and `3..39`). Units have not been confirmed;
do not assume CTD-compatible units or automatically multiply these values by ten.
Preserve the source strings, mark the malformed fields invalid, and obtain the
provider's unit definitions before cross-source comparison. The `temp` key occurs
in 2,796 records with numeric values from -1.7 to 34.5; its unit convention should
also be recorded explicitly. These metadata issues are separate from TSV syntax
and read/concentration validation.

## Sequence assignments and concentration data

Each assignment method contains **174,819 sequence rows and 157,426,611 reads**.
Across all 3,498 paired tables, QCauto and QCauto+3-NN have identical sets of
sequence/read-count pairs. They are alternative taxonomic assignments of the
same underlying read evidence. Their sum is 349,638 database assignment rows,
not twice the number of independent detections or organisms.

Applying OCEAN's existing taxonomy interpretation policy to the complete tables
yields 880 distinct usable species labels for QCauto+3-NN and 527 for QCauto.
These counts include controls and repeated source occurrences, are based on
provider names rather than independently validated taxon IDs, and must not be
presented as verified environmental species richness. The higher-resolution
method's label count is not itself proof of greater scientific accuracy.

The audit deliberately reused `preprocessing/edna_taxonomy.py`. A naive count
of non-placeholder strings gives 881 and 528 species labels instead, and also
overcounts family labels because repeated ancestor names do not establish a
lower-rank assignment. The user-supplied taxonomy regression policy remains
relevant across the full dataset.

Two community-table schemas occur:

- **3,489 source occurrences:** 40 columns, including `ncopiesperml`.
- **Nine source occurrences:** 39 columns, with that column absent. Their
  internal-standard tables are empty.

For each method, 171,250 rows have positive provider concentration values;
3,246 rows have missing values in an existing concentration column; another
323 rows belong to tables without that column. There are no recorded numeric
zero concentrations. Missing/absent concentration must not be replaced with zero.

There are 83 empty target tables per method. One of those belongs to the
39-column schema; among the 40-column schema, 82 tables are empty, 123 nonempty
tables have all concentrations missing, and 3,284 have concentrations present
throughout. Empty target results and unavailable source files are different states.

Internal-standard row counts vary: 3,479 records have four standards, six have
one, two have two, two have three, and nine have none. Their 13,932 rows carry
442,404,272 reads, kept separate from biological target totals. Six distinct
`pcr_standard_conc` metadata strings occur, and that key is absent from 46
experiment records. Standards and provider concentrations require protocol-aware
interpretation; these checks do not validate calibration or infer abundance.

## What fails in the existing pilot integration

The actual current `_validate_interpreted_file` function was run read-only
against all 17,490 downloaded TSVs. Its first reported failure per file was:

| Current validation error | Files |
| --- | ---: |
| Missing required metadata keys | 324 |
| Row count below the current minimum | 173 |
| Header does not match the fixed contract | 18 |

Those failures affect 335 sample directories. The 168 README files are also
outside the current acquisition contract; including that file-policy check,
**355 directories have at least one known pilot incompatibility**. These are
largely limitations of the pilot assumptions, not evidence of malformed source
data. Counts are not additive because conditions overlap and validation stops
at the first failure within a file.

None of the 3,498 sample metadata tables contains one of the current classifier's
recognized keys (`sample_type`, `sample_category`, `control_type`). Without a
new evidence mapping or a retained review, these records remain unknown in the
existing classifier—even though explicit blank/negative-control evidence exists.

Full-corpus materialization would also exceed all three pilot limits:

- 3,498 source sample records versus a 2,000-sample limit;
- at least one assay per occurrence versus a 2,000-assay limit;
- 349,638 method-specific assignment rows versus a 250,000-detection limit.

Current provenance publication loads all retained normalized bundles and caps
them at 20. A 19-run initial import would leave almost no room for subsequent
versions. Merely downloading the archive or raising one row limit does not solve
publication, identity, classification and historical-lineage handling.

## Verification results

Completed:

- Full hierarchy/file enumeration and exact listing sizes; all directories
  have five TSVs and two raw-read files, with missing images explicitly counted.
- Full XZ decompression and row profiling of every TSV, with zero decompression,
  malformed-row, invalid-read-count or invalid-concentration failures.
- No duplicate metadata keys, repeated sequences within individual community
  tables, or source-identifier collisions across directories were found.
- All 3,498 method pairs reconcile by sequence and read count.
- Current pilot-validator replay and reuse of OCEAN's taxonomy policy.
- Hash-verified consolidation of all 38,148 non-FASTQ files on external storage.

All **6,996 raw FASTQ files** passed compressed-byte SHA-256 checks and full XZ
decompression/integrity checks. Their streams contain 460,098,792,796 expanded
bytes (read in memory in bounded chunks, not retained as extracted files).
Full-stream line counts are divisible by four and imply **616,159,469 paired
records**, with matching forward/reverse counts in all 3,498 pairs. Inspection of
up to the first 1,000 records per file covered 6,972,912 records: sampled FASTQ
structure, sequence/quality lengths and quality ASCII ranges passed, and sampled
read IDs agree across every pair. Full record counts assume four-line FASTQ;
record structure and ID agreement beyond the sampled prefix were not checked.
These checks are not a complete sequencing-quality analysis or a repeat of the
provider's denoising pipeline.

All **20,490 PNGs** passed signature, required-chunk, per-chunk CRC and end-of-file
checks, with zero failures. All report dimensions of 1,500 × 1,000 pixels. This
validates their container integrity, not the scientific meaning of the images.

Two transient HTTP 522 responses during PNG transfer succeeded on retry.
A local SQLite manifest lock during concurrent audit/acquisition was resolved
by enabling WAL and releasing the long-lived reader. Acquisition resumed from
committed file checkpoints; these are acquisition-process events, not production
database failures. No failed or pending transfers or integrity checks remain.

## Consequences for v0.5.0

1. Base the first full integration on the five actually available TSV types,
   plus a bounded provider-note role. Retain future nontarget support in the
   design, but do not fabricate missing nontarget tables or block this catalogue
   because they are absent.
2. Separate provider occurrences, physical sampling events and assays. The
   180 repeated names need evidence-based linkage, not automatic deduplication
   or counting every sequencing run as a new biological sample.
3. Support both concentration schemas, valid empty tables and missing coordinates.
   Preserve unavailable concentrations and explicit exclusion reasons.
4. Define and review a deterministic classification policy for provider blank
   metadata and negative-control notices. Preserve source text and policy version;
   generic `metagenome` alone must not imply environmental eligibility.
5. Account for coordinate precision before environmental joins, and retain
   assay/platform/calibration context for comparisons. Validate optional numeric
   metadata and confirm salinity/temperature units rather than silently repairing
   provider strings or assuming compatibility with other OCEAN data sources.
6. Replace pilot-wide in-memory publication and all-history staging with bounded,
   versioned processing and publication. Use structured queries for complete
   counts, taxon filters and temporal comparisons.
7. Start with weekly discovery checks and monthly validated publication, then
   revise cadence using observed changes. Listed modification dates occur in
   December 2024 and September 2025; one observation cannot establish a weekly
   update frequency. A renewable download credential is still required for
   reliable unattended operation.

For the later discussion with the ANEMONE developer, prioritize a versioned
manifest and bulk processed-data export: the entire processed payload is only
26 MB but currently requires 17,490 individual file requests, in addition to
directory discovery. Also request identity/resequencing semantics, coordinate
precision, environmental units, classification/calibration conventions, change/withdrawal records,
and supported machine authentication.
