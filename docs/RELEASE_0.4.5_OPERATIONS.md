# v0.4.5 release and deployment record

Verified on 2026-09-16 JST: [v0.4.5](https://github.com/jarondlk/ocean-platform/releases/tag/v0.4.5)
is published and serves 100% of production traffic at
[OCEAN](https://oceaninfobio.com). The eDNA retrieval, embedding, and provenance
refresh is complete. GitHub production deployment `6475587508` is successful.

## Release and build

- [PR #64](https://github.com/jarondlk/ocean-platform/pull/64) merged through
  protected `main`; release commit `cc3b3af3e2b4900e7ff8ed7ff26a42e91250faa5`.
- Cloud Build `50943356-0c01-4520-9da1-1de7cd92bd14` used an archive of that exact
  commit and completed all four steps successfully on 2026-09-15.
- Immutable API digest:
  `sha256:2e586c2e6d4d35ccc70dbe80e06f2a4d7aec25edbb33f3c9dfe131f23ad11538`.
- Immutable frontend digest:
  `sha256:2338f0d51c1d5f82859be7118f23b3a5ecf0ab3f0a61aed00ab3a569c228700a`.
- Backend, frontend, PostgreSQL integration, and CodeQL release checks passed.
  Cloud Build's Python stage reported 796 passed and 23 skipped: 13 service-gated
  tests and 10 tests requiring Node, absent from that Python container. The
  separate frontend gate passed 37 tests, TypeScript checking, and production
  build. PostgreSQL integration passed all 13 tests in its dedicated environment.
- Earlier local and candidate evidence, including 805 local backend passes and
  the final 56-test date-boundary subset, remains in the dated
  [fix QA report](ISSUE_59_FIX_QA_2026-09-15.md). Those counts describe distinct
  runs and must not be added together as a single full-suite result.

## Backup and deployment safeguards

Project `data-infra-infobio`, region `asia-northeast1`, service `ocean-platform`.

- Fresh backup job `ocean-pipeline-mpk7c` succeeded before data changes.
- Archive:
  `gs://data-infra-infobio-ocean-data/backups/20260916T060658Z-v0.4.5-pre-deploy-ocean_platform.dump`.
- Archive SHA-256:
  `caef74fa1ca31907acc2114650fd242ed8ffbb37bc4055c7e6744e166ff8b913`.
- All 27 tables were restored and compared in an isolated temporary database;
  the temporary database was removed after successful verification.
- Baseline audit `ocean-pipeline-m45jn` and read-only schema check
  `ocean-migrate-hj98t` passed. Schema remains `20260905_0011`; no migration ran.
- All five existing jobs (`ocean-migrate`, `ocean-pipeline`, `ocean-embedding`,
  `ocean-evaluation`, `ocean-anemone-process`) use the release API digest and
  source commit. Comparisons confirmed their commands, environment and secret
  references, resources, and retry limits were preserved.
- Candidate revision `ocean-platform-v045-cc3b3af` was checked with zero production
  traffic before promotion. Service configuration changed only for images and
  source-commit values. Minimum zero/maximum one instance, concurrency 20,
  required authentication, external job execution, and snapshot provenance
  reads remain unchanged. The generation output cap remains 1,600 tokens.

## Completed eDNA refresh

Refresh job `ocean-anemone-process-ndxhb` succeeded, followed by verification job
`ocean-anemone-process-krfwx`. This updated the two existing retrieval summaries
without reimporting or renormalizing canonical eDNA data.

- Two summaries updated to document version 3; zero inserts or inactivations.
- Exactly two invalidated embeddings replaced with 768-dimensional Vertex
  embeddings. The complete corpus contains 325 documents and 325 embeddings.
- Both summaries expose all four assay-level internal standards and their
  provenance. Standard reads remain separate from biological detection totals.
- One physical sample, one assay, 70 detections and four standards are retained.
  Each assignment method has 35 detections and 9,635 reads. The methods describe
  the same sample and must not be summed as independent samples or organisms.
- Before/after canonical checksums matched for samples, assays, detections, and
  internal standards. Source fields, taxonomic assignments and classification
  remain unchanged: `sample_kind=unknown`, `is_control=null`, and calibration
  `not_established`. No reference TSV sample was imported.
- Existing current and historical analysis records remain intact; no analysis
  rerun was needed because canonical records did not change.
- New retrieval generation:
  `0b8b8fcbc85a413df5ab867f3c5ea8dac76b2005fec89cf1c76bb875be757622`.
- Retrieval Parquet SHA-256:
  `91821ea68550e1ba2f0eb343d93f43a14aef9f2c27f56fb84a46c918de48aa29`.
- Retrieval JSONL SHA-256:
  `208c48f44ee1f8ddcbc18b76ab59041d7190e0e9ceec41691704a332b6a36f00`.
- Published provenance snapshot `v045-provenance`, SHA-256:
  `b0b2e0351a40e8690667d9852989255e69d500fac011812426dc001b6a0bdec3`.
- Both exact eDNA citation traces resolve to source files and embeddings.

## Deployment acceptance

The [compact QA results](RELEASE_0.4.5_DEPLOYMENT_QA.json) record 12 cases against
real Vertex generation and the refreshed production index, using the exact
release image. The harness used read-only production data and temporary local
chat history; it did not substitute preview eDNA summaries.

- Nine questions answered: original request, inventory, detailed methods,
  mixed-source context, controls, legacy context, unknown citation labels,
  Japanese eDNA, and a leading abundance question.
- Two empty-scope cases abstained as expected.
- One deliberate long-output case returned `502 / llm_output_limit`, with failed
  history and no successful partial answer, as expected.
- All 12 met their technical acceptance criteria. Source hashes matched the
  release, saved answers matched responses, and answers had zero invalid
  citations. The actual React renderer preserved citation IDs and order for
  all nine answers.
- Candidate and canonical anonymous checks returned 200 for login, session,
  and manifest assets; protected health, eDNA, and provenance APIs returned 401.
- After promotion, the authenticated production UI answered the original
  question with 54 valid citations, zero invalid citations, and zero warnings.
  Citation inspection showed the refreshed standard records. The provenance
  link opened a found, embedded eDNA document trace on `v045-provenance`.
- The UI explicitly displayed claim verification as **Not performed**.
- Production cutover became ready at `2026-09-16T06:15:15.775409Z`, with 100%
  traffic on `ocean-platform-v045-cc3b3af`. The final revision log check found
  zero ERROR-level or HTTP 5xx entries during the observed rollout window.

## Limits and rollback

These checks establish the software and deployment acceptance criteria for
issue #59; they do not establish scientific correctness of every generated
claim. Mixed-source QA still showed broad ecological interpretations and
occasional awkward or overconfident wording. Citation validity and coverage do
not verify entailment. Scientific review, sample/control classification and
calibration acceptance remain separate work. The bounded output-limit error
is intentional and still possible for sufficiently long requests.

Revision `ocean-platform-v044-d3aa6a9`, its immutable publication, and the fresh
backup remain available. The previous serving reader was verified against the
new v3 snapshot before cutover, but review corpus/publication compatibility for
any rollback. Do not downgrade the schema or overwrite later user/chat records.
No legacy resource was deleted during this release.

The release tag and deployed images remain pinned to the release source above.
Subsequent operations-documentation commits do not require another image build.
