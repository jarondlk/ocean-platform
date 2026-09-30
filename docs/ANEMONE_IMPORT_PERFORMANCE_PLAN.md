# ANEMONE cloud import performance recovery plan

Prepared 2026-09-28. The user authorized optimization-first execution and increased the current total monthly project ceiling to JPY 100,000. This supplements the v0.5.0 release plan; production remains on v0.4.5. The performance remedy is not yet proven. Keep the existing database capacity for the initial experiment.

## Evidence and uncertainty

- The first cloud transactional rehearsal exceeded its 1,800-second deadline. Local import took about 117 seconds; different hardware and database state mean this is not a controlled comparison.
- Instrumented cloud runs measured some approximately 10,000-row detection merges taking 67–70 seconds, disk reads and temporary-file activity. CPU readings alone do not establish adequate capacity.
- Cloud SQL is PostgreSQL 16 on db-f1-micro, with about 0.6 GiB RAM and 10 GB SSD. Staging is a separate database on the production instance: data is isolated, compute and I/O are shared.
- Cancelled transactions left dead rows. Staging cleanup completed successfully, verified all 22 detection indexes, and retained the original 1 sample, 1 assay, 70 detections, 4 standards and 325 retrieval documents. Cleanup reduces experimental interference; it does not prove the original bottleneck is fixed.
- The importer uses pandas `to_sql(method="multi", chunksize=500)` for intermediate tables. These are ordinary tables despite their temporary naming. Each unit then performs multiple matching/count/update/insert joins. Intermediate-table indexes and ANALYZE already exist; recommendations must account for that.
- Maintaining detection indexes, repeated target scans and limited memory are plausible contributors. No clean full run has yet established their relative contributions or a successful remedy.

## 1. One bounded operational experiment

Use the cleaned staging baseline and the exact released source and frozen candidate. Run the prepared transactional rehearsal that defers 18 non-unique detection indexes, preserves all integrity constraints and required assay indexes, refreshes target statistics, rebuilds the identical indexes, validates data, and rolls back. Capture elapsed time by unit and phase, including index rebuilding and document generation, plus database waits, I/O, memory and production health.

Proposed decision gates:

- At 10 units or 15 minutes, assess observed throughput and its trend. Projection is only an early-stop aid: unit sizes differ and rebuilding/publication add work.
- Use a 60-minute hard execution cap and aim for completion within 45 minutes to leave headroom. These are proposed engineering limits, not an established acceptable production maintenance window.
- Stop if throughput predicts missing the cap or production health deteriorates. Verify rollback and cleanup before another run. Do not run competing import experiments.
- A pass requires all 39 units, exact candidate accounting, rebuilt/valid indexes and verified rollback. Rehearse committed staging import separately: dry-run does not exercise retrieval writes or external publication.

If this passes, use the same tested procedure for committed staging and measure unchanged re-import. Deferring indexes is a first-load maintenance technique, not the default strategy for routine online refreshes.

## 2. Targeted importer improvements if the experiment fails

Profile a representative subset and largest units before another full run. Change one factor at a time:

1. Replace intermediate batched INSERTs with PostgreSQL COPY into explicitly typed, session-local temporary tables. Preserve nulls, JSON, Unicode, numeric precision, hashes and connection/transaction lifetime. Keep non-PostgreSQL paths where required.
2. Consolidate repeated match classifications and avoid unnecessary target scans or writes, based on actual query plans. Preserve scientific-correction versus provenance-refresh accounting, first-seen identifiers, review retention and withdrawal scope.
3. Retain intermediate-table ANALYZE and add measured target-statistics refreshes. Do not globally force join strategies or raise per-operation memory on this small shared instance without a measured memory budget.
4. Use durable, reviewed import options rather than depending indefinitely on an ignored deployment wrapper.

Run PostgreSQL 16 integration tests for pilot overlap, duplicates, corrections, unchanged import, review/history retention, rollback after injected failure and identical published data. Then repeat the complete cloud rehearsal. Any source change needs a new immutable commit/build and versioned release amendment or patch; never silently move the existing v0.5.0 tag.

## 3. Capacity fallback with a separate cost decision

If measured results still show a capacity bottleneck, compare a temporary dedicated-core instance for isolated benchmarking against resizing the existing shared production instance. Price the exact Tokyo-region configuration and operating duration, including storage, backups and overlap, against the current JPY 100,000 monthly project ceiling (increased by the user on 2026-09-28). This ceiling is not a spending target. Record cleanup/scale-down steps and any restart downtime before a capacity decision.

Do not assume extra Cloud Run CPU helps a database-bound operation. Do not enlarge storage reflexively, disable integrity checks, or weaken recovery logging. A temporary import upgrade is insufficient evidence for scaling down: test full-catalogue chat, retrieval and aggregation at the intended final database size too.

## 4. Release and recurring-ingestion acceptance

Require 349,638 assignment rows, 6,996 ANEMONE documents and the reconciled total of 7,319 retrieval documents; check per-method counts without summing alternative assignments. Preserve pilot IDs, other corpus sources, reviews, chats and historical citations. Verify unchanged re-import, complete matching embeddings, ready provenance publication, real answer/citation QA, authenticated UI and runtime resource use.

Set the production maintenance window from measured committed-import and publication times, with recovery headroom. Take a fresh backup and rehearse recovery; do not restore staging over production user history. Explicitly remove the staging database command wrapper and restore production artifact prefixes when deploying the production candidate.

For future refreshes, separately assess manifest-based unchanged-unit skipping and checkpointed preparation outside serving tables. Publication must remain coherent; committing partial units into the currently served catalogue is not a safe shortcut. Weekly/monthly scheduling remains deferred.

## References

- [PostgreSQL 16 bulk-loading guidance](https://www.postgresql.org/docs/16/populate.html): COPY, index rebuilding tradeoffs and statistics refresh.
- [Cloud SQL machine series](https://docs.cloud.google.com/sql/docs/postgres/machine-series-overview): shared-core machine capacity.
- [Cloud SQL pricing](https://cloud.google.com/sql/pricing): obtain region-specific estimates before a capacity decision.

## Execution evidence (2026-09-28)

The index-only clean-baseline trial was cancelled after reaching at least 12 units because later throughput projected beyond the one-hour budget. A later unit took about 130 seconds and target-table ANALYZE took 62.25 seconds. This does not establish that indexes were the sole bottleneck. Cleanup verified the original pilot counts, all 22 indexes and zero canonical dead rows.

The first source optimization now replaces eDNA intermediate-table batched INSERTs with bounded COPY into typed temporary tables. The existing comparison, merge, reconciliation and publication rules are unchanged. Twenty-nine targeted local tests passed, including two added integration tests for lossless serialization, session isolation, automatic cleanup and rollback after a later COPY batch fails. The actual PostgreSQL 16 cloud instance passed a separate 6,000-row correctness check and late-batch failure test using the immutable experimental image.

A rolled-back re-import of the complete existing local catalogue passed in 36.59 seconds: 349,638 detections, 6,996 documents, and zero inserts, updates or inactivations. This is a different workload from a first cloud load and is not evidence of a particular cloud speedup. The full cloud COPY rehearsal exceeded its one-hour deadline after 28 of 39 units (228,328 completed detection rows). Staging rollback/cleanup subsequently verified the original data and all 22 detection indexes. COPY alone did not resolve the performance problem. Production and database capacity remain unchanged. The optimization source is not yet committed or released; the existing v0.5.0 tag and published images remain immutable.

The next optimization combines the three match-classification joins into one aggregate query, skips UPDATE when no matching records changed, and uses primary-key `ON CONFLICT DO NOTHING` instead of an insert anti-join over the growing target. It verifies affected-row accounting and still rejects non-primary scientific-identity conflicts. Thirty targeted tests passed; a full unchanged local re-import passed in 33.75 seconds. A separate cloud PostgreSQL 16 test verified mixed correction/provenance/reactivation/new-row accounting and duplicate rejection. The full backend regression passed 862 tests, with 32 environment-gated skips; those skips are not counted as passes.

The immutable second optimization image underwent a full staging rehearsal that stopped at its throughput guard (see the capacity decision below). The wrapper includes automatic row-weighted time-budget checks as well as the one-hour execution cap. A paused operator therefore no longer leaves an obviously over-budget trial running until its deadline. No full cloud rehearsal is claimed successful until all units, index restoration and rollback assertions complete.

## Capacity decision after optimization trials (2026-09-29 JST)

The combined optimization trial reached 15 units / 96,538 detection rows in 400.51 seconds. Its recent throughput projected 4,325 seconds including the index-rebuild allowance, so it stopped itself and rolled back. Cleanup verified the original data, all 22 indexes and zero canonical dead rows. Correctness checks passed, but no complete cloud rehearsal has yet passed on the shared-core tier. No further identical micro-tier retries are planned.

The next benchmark will retain the tested code and use Enterprise zonal `db-custom-1-4096` (1 dedicated vCPU, 4 GiB RAM), preserving PostgreSQL 16, region, 10 GiB SSD, networking, backups and recovery settings. This follows the user's JPY 100,000 ceiling and optimization-first instruction. A fresh manual backup precedes the resize. The change briefly interrupts database connections; production availability must be checked afterward. This is a capacity experiment, not a claim that deployment has completed.

Google's public Cloud Billing catalogue was retrieved in JPY for `asia-northeast1`, with rates effective 2026-09-28 07:00 UTC: CPU JPY 8.558437499/vCPU-hour, RAM JPY 1.450312499/GiB-hour, SSD JPY 35.221874999/GiB-month. At 730 hours, the selected database compute plus 10 GiB SSD is approximately JPY 10,835/month, versus JPY 1,981 for the current micro tier, an increase of about JPY 8,854/month. These are list-price estimates excluding backups, networking, app/model usage, other project usage and taxes; they are not a measurement of the whole project's current bill. There is no committed-use purchase or storage expansion.

Compare full import and serving performance at this tier before choosing any further capacity. Retain a tested scale-down path, but do not scale back automatically if the intended serving workload or refreshes need the extra resources.

The fresh backup was verified successful and the resize completed without errors. After renewed authentication, the instance was verified RUNNABLE on the selected tier with storage, networking, backups, PITR and other compared settings preserved. Read-only production/staging checks passed with the original schemas and pilot counts; shared_buffers increased to 1,306 MB. Production remains on v0.4.5. The identical bounded rehearsal passed on the dedicated tier: all 39 units and 349,638 assignment rows, all 18 deferred indexes rebuilt, and the original 22-index set and pilot baseline verified after rollback. The import phase took 313.71 seconds; total cloud execution took 6 minutes 53 seconds. This establishes a full transactional rehearsal pass, not a committed import or serving-performance pass.

The committed staging load then passed (338.38 seconds import; 7 minutes 13 seconds total), with all expected canonical rows and 7,319 documents. History checks preserved all pilot IDs and 323 non-ANEMONE documents. After generating all 6,996 ANEMONE embeddings, an unchanged full replay with indexes retained passed in 245.25 seconds, made zero data/document changes, and preserved all 7,319 vectors and metadata exactly. This is evidence for unchanged replay, not a benchmark of a changed future provider release. Serving and citation QA remain required.
