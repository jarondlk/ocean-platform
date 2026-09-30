# v0.5.0 release and deployment record

**Current status (2026-09-30 JST): deployed to production and verified.** The chronological preparation notes below retain earlier pending states; the completed rollout record is at the end.

Started 2026-09-27 JST. The user requested a one-time **GitHub-first release**, followed by manual GCP deployment when authentication permits. No GitHub deployment workflow or workload federation is being reinstated.

## GitHub preparation

Source branch: `gcp-dev`; target: protected `main`. API/frontend versions are 0.5.0. CI now explicitly runs the catalogue and exact-aggregate PostgreSQL suites, alongside the existing integration suites, on PostgreSQL 16/pgvector.

[PR #69](https://github.com/jarondlk/ocean-platform/pull/69) merged with required CI passing. The immutable release commit is `914778b8144550932dfc9c831f2e9a4228cfe1c1`. [v0.5.0](https://github.com/jarondlk/ocean-platform/releases/tag/v0.5.0) is published with **GCP deployment pending** in its title and notes. PostgreSQL 16 CI passed all 29 integration tests; the post-merge checks and CodeQL passed.

Local checks on 2026-09-27:

- Ruff and diff whitespace checks passed.
- All 40 frontend tests, typecheck and production build passed.
- Python dependency consistency passed; Alembic has one head, `20260925_0013`.
- Backend regression: **862 passed, 29 environment-gated skips**, with **79.13% coverage**, above the 70% gate. Dedicated CI exercises the PostgreSQL-gated suites.
- The first sandboxed backend attempt could not bind loopback HTTP fixture servers. It is not counted as a successful regression run; the suite was rerun with loopback access.

## GCP status

**v0.5.0 production deployment remains pending as of 2026-09-29 JST.** Production was freshly verified running v0.4.5; the full catalogue rehearsal uses a separate PostgreSQL database and private artifact prefix on the existing infrastructure.

Cloud Build succeeded from an archive of the exact release commit, including backend/frontend checks. The immutable images are:

- API: `sha256:7272abda181730f4c4df2e6e7a0bcebef2612c42a062949ec4bb1a333309b5d0`.
- Frontend: `sha256:c8987c7cfcf40c0be2298b1b736ee700caac07f5d32a4d55515e378eb0bc3d44`.

The pre-staging backup was restored and verified across all 27 tables, including application history. Its SHA-256 is `e706c9dbb6378d6ceb0ef28935daf95455e803337c09897d9ce743f8d038cf29`. The isolated copy must never be restored wholesale over later production history. A fresh backup is required immediately before production cutover.

The frozen processed candidate package was uploaded and checksum-verified: 110,821,843 compressed bytes, 18,011 files, SHA-256 `e3eb67bc569118712152cb23f64acdacec66c111d888774b07cfff8c9dd68eb6`. It contains the selected raw TSVs, normalized bundles and manifests. FASTQ data and provider credentials are excluded.

### Staging migration invocation and credential recovery

The first migration invocation failed because Alembic's interpolating configuration parser rejected the percent-encoded socket URL. Its exception included the database credential. The credential was rotated under the user's explicit recovery approval; the old secret version was disabled after the replacement database connection and refreshed v0.4.5 service passed checks. Production schema and corpus were unchanged. Subsequent operator diagnostics redact connection-string credentials. The original protected cloud log remains subject to its retention policy; the exposed credential is no longer valid.

The corrected operator invocation uses `RawConfigParser` and successfully applied the staging migrations. This changes the invocation, not the immutable release source or image. The refreshed v0.4.5 service passed candidate readiness, login/session HTTP checks and anonymous protected-route rejection before receiving all production traffic.

### Import optimization and remaining gates

The first micro-tier cloud trials exceeded their runtime budgets. Index deferral and COPY alone were insufficient; the final importer combines typed temporary-table COPY, one match-classification pass, conditional updates and primary-key conflict handling. It passed 30 targeted local tests, cloud PostgreSQL 16 value/merge/rollback checks, and the full backend regression (862 passed, 32 environment-gated skips). The capacity fallback and successful full-catalogue results are recorded below; earlier trial failures are retained in the [performance recovery plan](ANEMONE_IMPORT_PERFORMANCE_PLAN.md).

Remaining checks are complete cloud provenance, actual hybrid/model questions, manual citation assessment, authenticated v0.5.0 interface checks, and coordinated production cutover/recovery. No full-catalogue production data or schema promotion is claimed yet. See [the release plan](RELEASE_0.5.0_PLAN.md).

The final source-built images passed zero-traffic staging revision readiness at API 2 CPU / 2 GiB and frontend 1 CPU / 512 MiB. Login/session endpoints returned 200 and anonymous protected API requests returned 401. Staging uses an explicit database-name override and isolated artifact prefixes; both must be restored to production values at cutover. Authenticated production browser access also passed and displayed its unchanged 325-document corpus, healthy database and ready publication. Production traffic remains entirely on v0.4.5.

No new IAM grants, automatic deployments or ingestion schedules were introduced.

### Capacity recovery update (2026-09-29 JST)

The second optimized rehearsal stopped itself after 15 of 39 units when measured throughput projected beyond the one-hour budget. Cleanup succeeded, preserving the pilot baseline and all 22 indexes. It did not complete a full import.

A fresh Cloud SQL backup completed successfully before a resize request from `db-f1-micro` to `db-custom-1-4096` (1 dedicated vCPU, 4 GiB RAM). The resize completed successfully. After renewed authentication, the instance was verified RUNNABLE on the selected tier, all compared recovery/network/storage settings were preserved, and read-only production/staging schema and pilot-count checks passed. The estimated database compute plus existing 10 GiB SSD cost is approximately JPY 10,835/month, excluding other project costs, backups, networking and taxes; see the performance recovery plan for the pricing basis.

Public login/session endpoints also responded and protected API access rejected anonymous requests. Production traffic remains entirely on v0.4.5. The same optimized full rehearsal passed on the new tier: all 39 units / 349,638 assignment rows, all indexes rebuilt, and rollback verified. Import elapsed time was 313.71 seconds (6 minutes 53 seconds total execution). The committed staging import also passed: 338.38 seconds of import work and 7 minutes 13 seconds total execution, with 3,498 samples/assays, 349,638 assignments, 13,932 standard rows and 7,319 retrieval documents. Subsequent history checks preserved all 325 prior document IDs, the pilot sample/assay IDs, and the exact content of all 323 non-ANEMONE documents. All 6,996 ANEMONE embeddings completed with the configured Vertex model. An unchanged full replay with all indexes retained passed in 245.25 seconds: zero data/document changes, identical publication IDs, and exact preservation of all 7,319 embedding vectors and metadata. Provenance publication and serving QA remain pending. Production catalogue promotion remains gated on that result and the remaining acceptance checks.

### Import optimization source

The tested importer and regression tests are committed as `4016d78a5b8eaabdf113b6ee6902fb68ffbd86df` on `gcp-dev`, with [draft PR #71](https://github.com/jarondlk/ocean-platform/pull/71). GitHub CI and CodeQL passed, and a fresh Cloud Build from an archive of this exact commit succeeded. Its immutable API digest is `sha256:76f06c92eec16431b8676b107789cd3a2d1a8141063c032987da849f60b87b36`; frontend digest is `sha256:a50dada34a50f9d40f47d288d5dc5c2d2ef07a61e24dc8a3d679e6702686cc57`. The earlier benchmark image contained the identical importer file over the released API base. The existing v0.5.0 tag and original image digests remain unchanged; production must use an explicitly recorded, validated deployment amendment.

## Answer-quality follow-up

[Issue #70](https://github.com/jarondlk/ocean-platform/issues/70) was created before GCP deployment with `bug` and `logic` labels. It records the confirmed local routing and response-focus limitations. Production reproduction remains pending; the staging checks must distinguish accepted wording limitations from blocking numeric, retrieval, citation or scientific-support failures.

## Staging answer QA and accepted deferral (2026-09-30)

Staging provenance publication completed. Thirty real hybrid/model/API cases completed with HTTP 200 at a 2 GiB job limit (peak process RSS 971.2 MiB). Answered cases had valid citation identifiers, successful traces and matching aggregate export hashes. This is not a 30/30 answer-quality pass. Supported exact counts passed; polite-summary, abundance-interpretation and Japanese count routing remain defective. Manual review also found a rare-taxon false denial caused by a top-ten assay summary omitting the requested taxon, and an unsupported freshness claim inferred from sampling dates. The canonical rare-taxon QCauto result is one occurrence, one assignment and 122 reads.

The user explicitly accepted deferring these scoped chat defects to issue #70 while continuing deployment and testing. They affect answer reliability for particular requests, not canonical data integrity. Unfinished chat fixes were preserved outside the deployment source. The validated runtime remains commit `4016d78`; citation syntax alone does not establish scientific support. Additional interpretation repetitions, fresh backup, production publication and authenticated v0.5.0 browser checks remain outstanding. The manual processing job was restored to its normal 4 GiB setting after QA.

## Production rollout completed (2026-09-30 JST)

Production now serves the validated v0.5.0 deployment amendment at `https://oceaninfobio.com/`, with all traffic on `ocean-platform-v050-prod0930`. Runtime commit `4016d78a5b8eaabdf113b6ee6902fb68ffbd86df` was built from an exact Git archive. PR #71 merged as `2be74fb8ff01a3e629308710aa9c2b9b11a059e9`; only documentation differs between that merge and the runtime source. Required PR and post-merge checks passed. The original v0.5.0 tag remains unchanged. API/frontend immutable image digests are those listed in the optimization-source section above.

The rollout used a verified maintenance revision, removed old candidate routes, and drained existing requests before a fresh backup. The new backup restored successfully in isolation across all 27 tables, including 118 existing chat interactions. Its SHA-256 is `8211d9f386818acd289020035075b2f814e33b0f58b33fa23f896fd6452eb36f`. Backup locations and execution identifiers are retained in the private operator record.

The production import passed in 346.69 seconds of import work (7 minutes 10 seconds total execution). It applied schema head `20260925_0013` and reconciled 3,498 source occurrences/assays, 349,638 assignment rows, 13,932 standard rows, 6,996 ANEMONE documents and 323 other documents. All 22 indexes are valid. The 6,996 ANEMONE embeddings were copied from staging only where document identity, title, text and source-row hash matched exactly; no embedding refresh candidates remained. Production provenance published as `v050-production-provenance`.

Before QA writes or reopening traffic, exact fingerprints verified all 14 checked application-history and other-scientific-source tables unchanged. All 325 previous document IDs, pilot sample/assay IDs and exact content of all 323 non-ANEMONE documents were preserved. Authentication settings, runtime identities and resource limits were retained. Both containers' staging/maintenance command overrides were cleared, and production artifact locations explicitly restored. All existing manual jobs now use the validated API image; the ANEMONE job is back at its normal 4 GiB limit. No automatic deployment or ingestion schedule was enabled.

### Production acceptance and remaining limitations

- Ten additional staging interpretation requests completed with no automated citation/trace/export failures, at a 981.2 MiB process peak under a 2 GiB limit. Their main scientific cautions held, but scope wording and unmatched method-comparison examples still need improvement.
- Eight production API questions completed with HTTP 200, correct supported exact metrics, valid citation IDs, successful traces and hash-verified exports. Peak process RSS was 959.1 MiB. Manual review reproduced the accepted rare-taxon false denial and unsupported freshness claim; this is **not an eight-of-eight semantic-quality pass**. Issue #70 remains open.
- The production revision passed readiness/health checks; anonymous health/stats access returned 401. An authenticated browser showed 7,319 total documents, 6,996 eDNA documents and healthy database/model/publication signals. An old pre-deployment tab retained stale sign-in state; a fresh tab opened normally with the existing authenticated session.
- Authenticated live chat answered the catalogue-count question with 3,498 occurrences/assays, explicit unresolved physical identity, no model invocation, seven valid citations and zero invalid citations. The citation inspector, actual JSON download and aggregate provenance page passed. Downloaded payload SHA-256 matched aggregate ID `032dff2467276e8df96c4c36e7a88e7a92df443bb61883b4227d7e0333c0f111`. The provenance page resolved the same canonical generation.

The older Overview “Registered samples” and raw-registry counters remain separate legacy registries; they are not the ANEMONE source-occurrence total. Use canonical catalogue counts for ANEMONE coverage. The observation remains the accessible 2026-09-17 catalogue, not a claim of current provider freshness or resolved physical-sample identity.

Recovery must account for the now-published v4 catalogue and migrations. Do not point traffic to an incompatible v0.4.5 reader, downgrade populated history migrations, or overwrite later user activity with the pre-cutover backup. Retain the maintenance revision for controlled recovery and prefer forward repair of the current publication.
