# OCEAN Platform v0.5.0

**GCP deployment pending.** This is the GitHub source release. Production migration, catalogue import, embeddings, provenance publication and live acceptance will follow separately. Publishing this release does not trigger an automatic deployment.

## Included

- Full-catalogue ANEMONE ingestion for the accessible 2026-09-17 observation, with immutable manifests, bounded source units, resumable acquisition, checksum validation and transactional publication.
- Explicit locus/team/project/run identity; separate assignment methods, target status and concentration availability; valid empty community tables and conservative control classification.
- Catalogue filters and exact SQL summaries independent of retrieval top-k.
- Exact-count chat answers with retained, hash-verified aggregate citations, downloadable evidence and citation navigation. Historical aggregate evidence survives corpus refreshes.
- Safe refresh tooling: failed observations preserve the previous completed publication, and missing provider paths require withdrawal review.

The locally reconciled observation includes 3,498 source occurrences/assays, 349,638 assignment rows and 6,996 retrieval documents. Each assignment method accounts for 174,819 rows and 157,426,611 reads; those methods describe alternative assignments of the same evidence and must not be added as independent observations. Raw archives and credentials are not included in this source release.

## Known limitations

Chat can unnecessarily clarify ordinary summary paraphrases, mistake an interpretation question containing “count” for an aggregate request, and bury the requested metric in a general template. Environmental-only zero counts need clearer exclusion context. Japanese routing needs further evaluation. The [question-quality report](ANEMONE_QUESTION_QUALITY_2026-09-26.md) records exact requests and observed results; a separate `bug`/`logic` issue tracks this follow-up.

Physical sample identity remains unresolved. The observed catalogue contains 343 explicit negative controls and 3,155 unknown classifications, with no automatically classified environmental occurrences. Read counts and reported concentrations do not establish organism abundance, contamination clearance or independently verified taxonomy. No nontarget tables were exposed in this observation. Scheduled weekly/monthly ingestion is not enabled.

## Verification and deployment requirements

Local full-catalogue reconciliation, idempotent publication, exact-count QA and citation/export integrity are documented in [implementation QA](ANEMONE_V0.5.0_IMPLEMENTATION.md) and [aggregate QA](ANEMONE_CHAT_AGGREGATION_QA.md). Seventeen successful natural-language aggregate answers had expected numbers and valid citations; this is not a live-model quality pass. Release regression and CI results are recorded separately in [the release operations record](RELEASE_0.5.0_OPERATIONS.md).

Apply migrations `20260924_0012` and `20260925_0013` through a rehearsed, backed-up rollout. Preserve existing pilot identities, other corpus sources, reviews, analysis history and chat evidence. Complete all 6,996 candidate embeddings with the correct serving model and publish cloud-resolvable provenance before opening the new corpus to normal chat. At pre-release local QA, embedding coverage was 0/6,996 and ordinary hybrid/model acceptance was still pending.

Follow [the deployment plan](RELEASE_0.5.0_PLAN.md), including PostgreSQL 16 rehearsal, restore verification, live claim-to-citation assessment and production smoke checks. Database and external publication pointers require coordinated recovery; application traffic rollback alone does not undo corpus changes. Do not downgrade populated history migrations or overwrite later user records with a stale backup.
