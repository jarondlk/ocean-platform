# OCEAN Platform v0.5.0

**Deployed to GCP production on 2026-09-30.** The [live OCEAN service](https://oceaninfobio.com/) uses the validated importer amendment from commit `4016d78` on revision `ocean-platform-v050-prod0930`. The original v0.5.0 tag remains unchanged. Release publication does not trigger automatic deployment.

## Included

- Full-catalogue ANEMONE ingestion for the accessible 2026-09-17 observation, with immutable manifests, bounded source units, resumable acquisition, checksum validation and transactional publication.
- Explicit locus/team/project/run identity; separate assignment methods, target status and concentration availability; valid empty community tables and conservative control classification.
- Catalogue filters and exact SQL summaries independent of retrieval top-k.
- Exact-count chat answers with retained, hash-verified aggregate citations, downloadable evidence and citation navigation. Historical aggregate evidence survives corpus refreshes.
- Safe refresh tooling: failed observations preserve the previous completed publication, and missing provider paths require withdrawal review.

The production observation includes 3,498 source occurrences/assays, 349,638 assignment rows, 13,932 standard rows and 6,996 eDNA retrieval documents. The complete corpus has 7,319 documents and matching embeddings. Each assignment method accounts for 174,819 rows and 157,426,611 reads; those methods describe alternative assignments of the same evidence and must not be added as independent observations. Raw archives and credentials are not included in this source release.

## Known limitations

Chat can unnecessarily clarify ordinary summary paraphrases, mistake an interpretation question containing “count” for an aggregate request, and bury the requested metric in a general template. Manual live QA also reproduced a rare-taxon false denial and an unsupported freshness claim. Environmental-only zero counts need clearer exclusion context; Japanese routing needs further evaluation. The [question-quality report](ANEMONE_QUESTION_QUALITY_2026-09-26.md) records earlier requests and observed results; [issue #70](https://github.com/jarondlk/ocean-platform/issues/70) tracks the scoped follow-up.

Physical sample identity remains unresolved. The observed catalogue contains 343 explicit negative controls and 3,155 unknown classifications, with no automatically classified environmental occurrences. Read counts and reported concentrations do not establish organism abundance, contamination clearance or independently verified taxonomy. No nontarget tables were exposed in this observation. Scheduled weekly/monthly ingestion is not enabled.

## Verification and deployment

Local full-catalogue reconciliation, idempotent publication, exact-count QA and citation/export integrity are documented in [implementation QA](ANEMONE_V0.5.0_IMPLEMENTATION.md) and [aggregate QA](ANEMONE_CHAT_AGGREGATION_QA.md). The subsequent production rollout completed migrations, fresh backup and isolated restore, catalogue import, all 6,996 eDNA embeddings and provenance publication. Authenticated browser, chat, citation download/hash and provenance navigation passed. Eight production chat requests passed automated integrity checks; manual review found the scoped answer-quality defects above. The [release operations record](RELEASE_0.5.0_OPERATIONS.md) contains results and limits.

Production schema is at `20260925_0013` and provenance publication is `v050-production-provenance`. All prior document IDs, pilot identities, other corpus sources and checked application-history tables were preserved through the rollout.

The [deployment plan](RELEASE_0.5.0_PLAN.md) is retained as a historical checklist. Database and external publication pointers require coordinated recovery; application traffic rollback alone does not undo corpus changes. Do not route to an incompatible v0.4.5 reader, downgrade populated migrations or overwrite later user records with a stale backup.
