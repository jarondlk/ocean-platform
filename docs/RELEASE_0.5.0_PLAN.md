# v0.5.0 GitHub release and GCP deployment plan

Prepared 2026-09-26; sequence revised by the user on 2026-09-27. **Execution authorized: complete GitHub work first, then GCP deployment as authentication allows.** Proposed source branch: `gcp-dev`, integrated through a reviewed PR to `main`. Deployment remains manual; do not restore the canceled GitHub deployment/federation setup.

## Scope and current evidence

Release the full **accessible ANEMONE catalogue observed on 2026-09-17**, its canonical ingestion and refresh machinery, filters, exact chat aggregation, and retained aggregate citations. This is a dated observation, not a claim of continuous synchronization or access to unpublished provider data.

- Frozen candidate: `a6411a26f46c098769298d11dfcafbf2dd85a141dbe5ccbdfafb581acc8bdc46`.
- 39 source units; 3,498 source occurrences and assays; 349,638 assignment rows; 6,996 ANEMONE retrieval documents.
- Each assignment method has 174,819 rows and 157,426,611 reads. Alternative assignment methods must not be added as independent observations.
- 343 explicit negative controls, 3,155 unknown classifications, and no automatically classified environmental occurrences. Physical sample identity remains unresolved.
- Preserve the existing non-ANEMONE corpus, pilot identifiers, reviews, analysis records, chat history and historical citations. Reconcile the pilot overlap explicitly; the new production corpus total cannot be inferred by simply adding 6,996 documents to the old total.

The release preparation updates application versions to 0.5.0. The implementation must be committed and verified by CI before merging. GitHub's latest published release was verified as [v0.4.5](https://github.com/jarondlk/ocean-platform/releases/tag/v0.4.5) during this planning session. [The previous deployment record](RELEASE_0.4.5_OPERATIONS.md) describes production as last verified on September 16; it is not a fresh GCP inspection.

Local aggregate QA found 17 numerically correct answers with valid, reproducible citations; two routing failures and presentation shortcomings remain. **Candidate embeddings are 0/6,996, and live hybrid/model QA is incomplete.** Accepting the known wording/routing limitations does not establish deployment readiness. See [the question-quality report](ANEMONE_QUESTION_QUALITY_2026-09-26.md).

Recommended scope boundary: ship the manual refresh capability, then activate weekly observation and monthly reviewed publication separately after renewable provider access, monitoring and runtime budgets are settled. This is a proposed deferral of the earlier scheduling gate, not a claim that scheduled ingestion has shipped.

## 1. Prepare the GitHub candidate

1. Review the complete working-tree diff and migration/data-contract changes. Keep archives, caches, credentials, database dumps and raw QA responses out of Git. Retain reproducible tests and sanitized QA reports.
2. Add `test_anemone_catalogue_postgres.py` and `test_edna_aggregate_postgres.py` to the CI workflow's explicit PostgreSQL integration list; they are currently absent. Test against deployed PostgreSQL 16 as well as the existing local results from PostgreSQL 18.3.
3. Bump API and frontend package/lockfile versions to 0.5.0. Prepare release notes with the observation date, features, scientific limitations and known chat limitations.
4. Run required backend/coverage, PostgreSQL migration and integration, frontend test/typecheck/build, lint and security checks. Preserve separately reported test runs rather than adding their counts into an artificial full-suite result.
5. Commit and push `gcp-dev`, open the PR to `main`, and merge only after required checks and review. Publish the GitHub `v0.5.0` release against the exact merged commit, explicitly marked **GCP deployment pending** in its title/body. File the answer-quality issue before starting GCP work. Subsequently build immutable API/frontend images from that commit and record both digests. Any code change requires a new build and relevant revalidation.

One-time sequence exception requested by the user: the GitHub source release precedes GCP deployment because the user is away from their computer. Publishing the release does not waive any cloud deployment acceptance gate. Release notes must explicitly distinguish released source code from the currently deployed service. Do not request an interactive GCP sign-in until GitHub work is complete; if sign-in is then required, retain a precise handoff for later.

## 2. GCP preflight and isolated rehearsal

Renew operator GCP authentication when execution starts. Read the actual service revision, job images, schema, publication generations, database major version, free storage, resource limits, access permissions and spend before choosing commands. The existing deployment uses Cloud Run, Cloud SQL, Cloud Storage and Vertex; reuse its established identities and secrets where possible. The user increased the total monthly project ceiling from JPY 20,000 to JPY 100,000 on 2026-09-28 and requested optimization first. Check current spend and projected total costs before extra capacity or persistent staging resources; the ceiling is not a spending target. See the [import performance recovery plan](ANEMONE_IMPORT_PERFORMANCE_PLAN.md).

Rehearse against an **isolated database and artifact prefix** on the deployed PostgreSQL major version. A zero-traffic Cloud Run revision connected to production is not an isolated data rehearsal. Verify a fresh backup restores successfully and includes application history and aggregate evidence, not only corpus tables.

The existing ANEMONE job is oriented around the pilot/classification workflow. Prepare and test the cloud invocation for the new directory-based candidate importer, with explicit database selection, bounded job duration/retries and sufficient memory/disk. Do not assume the existing job configuration already performs a full catalogue import. Review any required permissions individually; this plan does not authorize new IAM grants.

Upload/register the candidate manifests, normalized bundles and source artifacts required by provenance in immutable storage. Verify hashes after transfer and resolve all registered artifact references from the cloud runtime. Keep sequencing reads out of the database and container image. The local full archive is approximately 35.56 GB; raw-read cloud archival should be a separate retention/cost decision from the processed serving pipeline.

Rehearsal sequence:

1. Apply migrations `20260924_0012` and `20260925_0013`; verify runtime reads of canonical data and writes of retained aggregate evidence.
2. Run a transactional candidate dry run, then import with explicit expected previous generation and retrieval publication. Reconcile pilot overlap, preserved reviews and other corpus sources.
3. Register and publish complete provenance artifacts. Check the canonical database generation, retrieval binding and external serving pointer agree and are ready. The database transaction and external pointer are separate operations; rehearse recovery from a pending pointer.
4. Populate all 6,996 ANEMONE document embeddings with the serving model/provider/dimension and current document hashes. Preserve valid embeddings for other sources. Rebuild or invalidate only where content/model identity requires it.
5. Verify normalized data, retrieval, embeddings, provenance and historical citations through the actual candidate cloud services. Rerun the importer unchanged to demonstrate idempotence.

## 3. Release acceptance

| Area | Required evidence |
| --- | --- |
| Data completeness | Frozen candidate row/read/table counts reconcile; all intended source units represented; no accidental pilot duplication or loss of other sources/reviews. |
| Serving readiness | Complete matching embeddings, resolvable cloud artifacts, ready publication pointers and tested cross-process serving. No silent truncation to fit resource limits. |
| Exact chat answers | Representative total, method, control, empty-table, missing-value and rare-taxon questions reproduce expected scoped numbers; invalid/empty scopes remain safe. |
| Ordinary chat | Run the pending questions through real hybrid retrieval and Vertex. The known rare-taxon row must be discoverable. Interpretation answers must be supported or explicitly limited when evidence is insufficient. |
| Citation quality | Check claim-to-source support manually, beyond syntactic citation validity. Open provenance and downloads; verify hashes and scope. Preserve historical aggregate traces after publication. |
| UI and access | Authenticated browser chat, data filters, citation navigation and downloads work; anonymous protected API requests are rejected. |
| Operations | Tested restore/recovery path, acceptable measured latency/memory, no unexplained errors, preserved history and bounded cost. |

Use [the 30-question matrix](../evaluation/qa/anemone_v050_questions.json) and [QA report](ANEMONE_QUESTION_QUALITY_2026-09-26.md), retaining actual responses and per-case verdicts. Repeat high-risk interpretation questions to assess variability. The current runner is loopback-only: use it for the isolated local candidate and an appropriately authenticated harness/browser for cloud checks; do not weaken its host restriction merely to point it at production.

Known follow-up limitations can remain with explicit disclosure: unnecessary clarification for an ordinary summary paraphrase, interpretation questions captured by the count route, poorly focused templates, classification-zero context and unverified Japanese routing. These are not an excuse for wrong counts, fabricated scientific claims, broken citations, missing searchable evidence, authentication failures or data loss. Newly discovered failures in those areas block release. Do not describe all 30 questions as passing if known failures remain.

## 4. Production cutover and recovery

Prefer a **controlled maintenance window** for the first full import unless rehearsal proves the old and new readers can safely coexist with the new schema, document format and publication lifecycle. A traffic-only canary cannot isolate changes to a shared production database.

- Record the current revision, image digests, schema and paired publication/artifact generations. Pause ingestion and affected writers for the cutover; take and verify a fresh backup. Preserve all existing rollback artifacts.
- Deploy the tested images to a candidate revision. Apply the rehearsed migrations and import/embedding/provenance sequence with the actual observed previous generation. Complete embeddings/publication before reopening affected queries. Reuse staged embeddings only if their exact content/model identity and transfer mechanism have been verified.
- Check counts, pilot reconciliation, history, authentication and citation exports on the production candidate. Promote traffic only when these checks pass, then verify the public domain through an authenticated session.
- Observe errors, latency, model failures and citation failures during an initial operational window, and review again the following day. Record actual timestamps and results in a deployment report. Schedule no automation during this planning step.

Rehearse rollback before cutover. Restore the previous application revision only if compatibility with the resulting schema/data/pointers has been demonstrated. Otherwise keep affected access paused and use the tested publication recovery or a forward repair. **Traffic rollback does not undo corpus changes.** Do not downgrade populated aggregate-history migrations or overwrite later chat/review records with an old database backup. Restore backups into isolation first and use a separately reviewed recovery procedure if data restoration is necessary.

## 5. GitHub-first publication and later deployment status update

Complete this GitHub work immediately after step 1, before steps 2–4: publish `v0.5.0` at the verified source commit with **GCP deployment pending**, then create a new GitHub issue from [the prepared draft](ISSUE_ANEMONE_CHAT_QUALITY_DRAFT.md), using the existing `bug` and `logic` labels. State that reproductions are from the local candidate and production reproduction is pending. After deployment acceptance, add actual image/revision evidence to the operations record, update the release deployment status, and reproduce the issue cases against production. Clearly distinguish confirmed production results from local-only observations. Link the report and exact request matrix; omit credentials, private operational identifiers and raw user histories. Add the new issue link to the release notes. Keep closed issue [#59](https://github.com/jarondlk/ocean-platform/issues/59) closed; this is a distinct follow-up.

Suggested next patch: v0.5.1 for routing and response focus, subject to prioritization. Weekly/monthly ingestion activation remains separate work requiring provider credentials, alerting and a tested review/promotion process.

## Completion record

Execution is finished only when the merged commit and tag, successful checks, image digests, migrations, candidate/publication manifests, complete embedding coverage, live question/citation results, backup/recovery evidence, production traffic verification and follow-up issue URL have been recorded. None of those future execution steps is marked complete by this plan.
