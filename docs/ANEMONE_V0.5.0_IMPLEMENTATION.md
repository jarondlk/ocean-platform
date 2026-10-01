# ANEMONE v0.5.0 implementation and local QA

**Dated local implementation record.** The catalogue was subsequently deployed
on 2026-09-30. The release-gate list below describes the state at local QA,
not current production. See the [v0.5.0 operations record](RELEASE_0.5.0_OPERATIONS.md)
for rollout results and [issue #70](https://github.com/jarondlk/ocean-platform/issues/70)
for accepted answer-quality follow-up. Recurring ingestion is still disabled.

Implemented 2026-09-24; final checks completed 2026-09-25 JST. Branch: `gcp-dev`. This is a locally validated implementation
against the complete **2026-09-17 accessible catalogue**, not a production release
or a newer provider observation. Production services, scheduling and GCP IAM were
not changed. Release version remains 0.4.5 until the release gates below pass.

## Archive and implementation

The primary working archive is now on the main device:

`../.cache/anemone-archive/2026-09-17/`

All **45,144 files / 35,555,980,361 bytes** were copied and checked against their
recorded SHA-256 hashes. `local-copy-verification.json` records the check. The
original `/Volumes/VIDEOS/ANEMONE-OCEAN/2026-09-17` remains a backup. No source
files were deleted. Archive content and credentials are not Git source files.

Archive manifest SHA-256:
`9a4a871adb65a78c02ea395b08d9b6b642e364dc89fcaab92e8fc98bd04c3912`.

Implemented:

- A separate catalogue contract, leaving the historical pilot contracts readable.
  It accepts valid empty communities/standards, the observed 39-column community
  layout, bounded provider notes, and optional nontarget tables. Unsupported
  roles, conflicting interpreted metadata and damaged files are quarantined.
- Explicit locus/team/project/run identity; existing pilot IDs remain unchanged.
  Repeated sequencing occurrences remain separate; physical sample identity is
  unresolved. All metadata rows are retained, including duplicate unknown keys.
- Separate assignment algorithm, target status and concentration availability.
  Provider values and raw taxonomy remain evidence; the user reference TSV is
  not a species whitelist. No concentrations, units or coordinates are invented.
- Explicit provider control evidence, conservative unknown classifications, and
  retention of matching applied reviews and their anchors. Changed sample bytes
  do not inherit an old review. Unconfirmed grid coordinates cannot establish
  precise environmental links.
- Bounded preparation in complete-occurrence units, a durable SQLite ledger,
  checksums, quarantine reports and immutable candidate manifests. Observation
  timestamps do not change an otherwise identical scientific candidate.
- Transactional imports with explicit database selection and expected-generation
  checks. Each unit reconciles only its own occurrences. Missing catalogue paths
  remain withdrawal candidates; they do not automatically delete canonical rows.
- Partitioned retrieval materialization, a single complete global merge, and
  version-4 source evidence for empty tables and provider control notices.
  `--publish-retrieval` commits canonical rows and retrieval rows together.
  Publication is serialized through a database advisory lock. Failed derivation
  rolls back; a pre-commit pointer failure restores the previous pointer.
- Reference-based restoration of normalized provenance, replacing the former
  limit of 20 retained bundles. Current provenance loads referenced source
  snapshots; earlier published provenance remains immutable.
- Locus/team/target filters in the data API and UI, four method choices, and
  `/data/edna/summary` for exact SQL counts independent of retrieval top-k.
  Read transactions pin page counts and rows to one database snapshot.
- A bounded refresh command: hierarchy discovery, changed-file acquisition,
  verified checkpoint reuse, listing rechecks, `Retry-After`, authentication
  failure handling and periodic forced content rechecks. It acquires processed
  files and inventories raw reads/images; it does not redownload the raw archive.

New entry points:
[`prepare_anemone_catalogue.py`](../scripts/prepare_anemone_catalogue.py),
[`import_anemone_catalogue.py`](../scripts/import_anemone_catalogue.py),
[`refresh_anemone_catalogue.py`](../scripts/refresh_anemone_catalogue.py), and
[`qa_anemone_catalogue.py`](../scripts/qa_anemone_catalogue.py).
Migrations: `20260924_0012` and `20260925_0013` (retained chat aggregate evidence).

Exact chat aggregation was subsequently completed and tested locally; see
[ANEMONE_CHAT_AGGREGATION_QA.md](ANEMONE_CHAT_AGGREGATION_QA.md) for the updated
test counts, supported questions, immutable citations and rollout requirements.

## Full-scale reconciliation

All 355 occurrences incompatible with the pilot rules now normalize. There are
**zero quarantined units** in this archived catalogue.

| Measure | Verified result |
| --- | ---: |
| Projects / runs | 10 / 19 |
| Bounded source units | 39 |
| Source occurrences / assays | 3,498 / 3,498 |
| Distinct reported sample names | 3,318 |
| Physical samples | Unresolved; not reported as 3,498 |
| Assignment rows | 349,638 |
| Rows per assignment method | 174,819 |
| Reads per assignment method | 157,426,611 |
| Internal standard rows | 13,932 |
| Explicit negative controls | 343 |
| Unknown classification | 3,155 |
| Automatically classified environmental occurrences | 0 |
| Empty community tables | 83 per method |
| Concentrations reported / missing / column absent | 342,500 / 6,492 / 646 |
| Retrieval documents and validated traces | 6,996 |
| Canonical citation hash mismatches | 0 |

Both assignment methods describe the same sequence evidence. Their read totals
must not be added as independent observations. No nontarget tables were exposed
in this catalogue; nontarget support was tested with synthetic fixtures.

Candidate:
`a6411a26f46c098769298d11dfcafbf2dd85a141dbe5ccbdfafb581acc8bdc46`.

Final retrieval generation:
`a01a472a74ea55ffbd2cee1e69822555af801a00dbcf8956414a942564011716`.

A complete canonical rerun made **zero inserts, updates or inactivations**. A
subsequent unchanged retrieval rerun retained all 6,996 documents, produced the
same generation and invalidated zero embeddings. No live embedding/model calls
were made during this QA.

## Verification and measured resources

- **826 Python regression tests passed.**
- **10 PostgreSQL integration tests passed**, including migration downgrade and
  re-upgrade, publication serialization, rollback, stale-generation rejection,
  empty-table filtering, namespace isolation and retained review anchors.
- **38 frontend tests** and TypeScript checks passed.
- Repository Ruff checks and `git diff --check` passed.
- Full source-row/read accounting, exact count endpoints, a rare-taxon query
  (`Ablabys taenianotus`, one QCauto assignment), and every retrieval document's
  canonical citation hash and provenance trace passed.
- Failed discovery, missing required files, changed remote bytes, authentication
  failure and budget exhaustion preserve the previous completed observation.
  Forced rehash and unchanged-validator reuse are covered by provider fixtures.

The combined import/publication took **116.74 seconds**, with approximately
**1.23 GB maximum resident memory for the Python process**. The full canonical
rerun took 92.29 seconds. These are Mac measurements, not Cloud Run timings or
cost estimates. The local candidate database occupied about **2.05 GB** after
retaining earlier QA source generations, excluding PostgreSQL cluster WAL and
other databases. PostgreSQL used 18.3 and pgvector 0.8.6 locally; the deployed
PostgreSQL major version must also be tested before rollout.

The current retrieval bundle is below the existing 128 MiB verification ceiling.
That ceiling remains enforced. Growth beyond it requires partitioned serving
artifacts; it must not be addressed by publishing a truncated generation.

Evidence remains under `../.cache/anemone-local/`: `full-catalogue-qa.json`,
`full-regression-tests.log`, `final-postgres-tests.log`, `full-rerun.log`,
`materialize-unchanged.log`, and frontend/lint logs. These are ignored local
artifacts. Some dependency deprecation/runtime warnings remain; tests passed. The temporary
PostgreSQL service was stopped after QA; its database files are retained. Local
restart instructions are in `../.cache/anemone-local/README.md`.

## Reproduction and recurring operation

Preparation is offline and does not need GCP or ANEMONE authentication:

```bash
.venv/bin/python scripts/prepare_anemone_catalogue.py \
  --archive .cache/anemone-archive/2026-09-17 \
  --work-dir .cache/anemone-candidate
```

For an isolated database migrated to head, use the importer with an explicit
`--database-url`, an isolated `DATA_DIR`, and `--publish-retrieval`. Without
`--execute`, the importer rolls back its database transaction. On later runs,
provide the observed `anemone-canonical` generation using `--expected-previous`.
Do not point this QA work directory at production as an incidental verification.

The refresh CLI accepts `--output`, `--previous`, `--max-requests`, `--max-bytes`,
`--min-interval` and `--rehash`. Credentials use the existing environment/secret
file mechanism. A request budget counts client operations; HTTP retries and
HEAD fallback may issue more than one HTTP request per operation. The default
512 MiB download allowance is for selected processed files. Failed observations
retain verified file checkpoints but never advance the completed pointer.

After a completed refresh, prepare a candidate, run import/QA in staging, and
promote only an accepted candidate. Start with weekly observations and monthly
reviewed publication as described in the plan. **No scheduler is enabled.** A
provider-supported renewable credential is still needed for reliable unattended
operation. Missing paths require separate withdrawal review.

## Remaining v0.5.0 release gates

This branch is not a claim that the entire release plan has shipped.

1. Stage on the deployed database major version; verify backup restoration,
   resource sizing and the complete cloud artifact/embedding/provenance pipeline.
   Register all candidate raw/normalized artifacts before cloud provenance jobs.
2. Deploy and verify the locally completed exact chat aggregation and immutable
   evidence migration in staging. Local browser/count/citation QA passed;
   authenticated cloud browser and ordinary model-assisted chat QA remain.
   Ordinary top-k retrieval is not proof of complete detection lists.
3. Exercise serving and rollback across cloud processes. The canonical and
   retrieval database updates are atomic, but the external pointer is a separate
   operation. A failure after commit leaves retrieval pending until an explicit
   successful rerun; API data and external search pointers are not a distributed
   transaction. Existing in-flight requests may retain their previous evidence.
4. Wire and test the scheduled job, monitoring and durable provider access after
   credentials and runtime budgets are settled. A completed local refresh is not
   a deployed recurring service.
5. Resolve or explicitly disclose provider scientific uncertainties: physical
   sample identity, grid precision, salinity units, calibration and upstream
   pipeline/reference versions. These do not justify silently excluding the
   accessible processed evidence from the catalogue.

## Acceptance questions and expected evidence

| Question | Expected result from this archived candidate |
| --- | --- |
| How many ANEMONE samples are included? | 3,498 source occurrences and assays; 3,318 reported names; physical count unresolved. |
| How many reads does each method report? Can I add them? | 157,426,611 per method; do not double-count shared evidence. |
| Are empty tables missing data? | 3,498 available target tables per method, including 83 valid empty tables per method. |
| Show QCauto detections of Ablabys taenianotus. | One exact filtered assignment; cite its source version and row. |
| How many records are environmental samples? | Zero automatically established in this unrevised full candidate; 343 controls and 3,155 unknowns. |
| Do missing concentrations mean zero? | No; distinguish 6,492 missing values from 646 rows whose column was absent. |
| Do these coordinates identify exact sampling points? | Grid precision is unconfirmed; do not claim precise environmental matches. |
| What happens if a download or import fails? | Previous completed data survive; no unrelated inactivation or partial candidate promotion. |

The data-layer expected results above were verified locally. They are not a claim
that a live language model has already answered these questions correctly.
