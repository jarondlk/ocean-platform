# ANEMONE classification review

Release decision (2026-09-03): keep the pilot unknown for `v0.4.0`. The
operator primitives below are implemented, but completing and validating the
researcher workflow is [next-patch work](ANEMONE_NEXT_PATCH.md). No real
classification review is approved or applied; its absence no longer blocks
the limited v0.4.0 release.

Status (2026-09-06): the authenticated review domain, effect preview, and
controlled manual application path are deployed in `v0.4.1`. The fixed Cloud
Run workload identity is registered. Authenticated researcher acceptance
remains pending, and the real canary has **not** been classified or
scientifically accepted.
No review is inferred from a sample name, collection device, coordinates, or
permission to implement this workflow.

## Authenticated review domain

The `/classification-reviews` API stores drafts and append-only state events in
application metadata, separate from the replaceable scientific corpus.
Researchers may draft, revise, approve, reject, or supersede a decision. Admins
may only record operational application success or failure. These are separate
events even when one person operates through separate authorized accounts.

The API derives actor identity, role, and event time from the active
database-backed login. Client-supplied reviewer names or timestamps are rejected.
Each review binds the exact source snapshot and sample to compressed-file hashes,
TSV row locators, values, rationale, and a content digest. `unknown` is a valid
approved scientific outcome when evidence is inconclusive.

An `applied` API state is an operational receipt, not a scientific decision.
It is written by the controlled job only after canonical import and affected
publication complete. Do not call the application endpoint directly or describe
an approved but unapplied decision as visible in analysis or chat.

## Effect preview

Select an eDNA sample in Data, choose its classification review, set assignment
method, rank, minimum reads, and top-taxa count, then select **Preview effect**.
The same operation is available at:

```text
POST /classification-reviews/{review_id}/preview
```

The request must include the current `expected_version`. The response compares
the current and proposed classification using the same deterministic analysis
algorithm used for published eDNA analysis. It reports eligibility, exclusions,
method-level read/diversity values, composition, changed table counts, and a
preview digest.

Preview is read-only. It does not approve a draft, change `edna_sample`, create
an analysis bundle, update retrieval, or establish scientific validity. Draft,
approved, and failed reviews are previewable. Rejected, superseded, applied,
stale, tampered, oversized, or unverified inputs fail closed. Unknown and control
proposals remain excluded from environmental-only results.

## Scope and trust boundary

A review can classify an otherwise unknown sample as `environmental`,
`negative_control`, `positive_control`, or `mock_community`. It cannot override
any recognized provider classification, including recognized fields appearing
after an unrecognized field. Samples absent from the review remain unchanged.
Conflicting recognized provider fields require a provider correction, not this
review input. Controls remain excluded from environmental-only analyses.

The trusted operator supplies a researcher attestation, not an authenticated
electronic signature. The system checks the exact snapshot, sample, file hashes
and metadata rows. It cannot verify the reviewer's identity or determine whether
those rows scientifically justify the decision. The researcher must inspect the
provider record and protocol, select supporting evidence, and explain the
decision. If the available evidence is insufficient, keep the sample unknown.
There is no web approval endpoint, automatic approval, or background ingestion.

Evidence references only verified `sample_metadata` or `experiment_metadata`
TSVs in that same snapshot. URLs, arbitrary attachments and cross-snapshot
evidence are not accepted in this version. Do not put secrets in review fields.
Reviewer/rationale/evidence are research provenance visible to authorized data
and export readers, not confidential notes.

## Legacy operator-file workflow

The workflow below predates the authenticated API domain. It remains a tested
normalization input, but its editable reviewer fields are operator attestations,
not authenticated reviewer identity.

### Prepare and review

Use a verified local raw snapshot. The following prints a **draft** to stdout
without normalizing, importing, writing artifacts or contacting ANEMONE:

```bash
python scripts/normalize_anemone.py --snapshot-id <snapshot-id> \
  --raw-root <local-raw-root> --classification-review-template
```

Save the draft in a private working directory outside version control. The
draft includes candidate sample-metadata rows, not a scientific decision.
Select relevant rows (at most 32 per sample); additional experiment-metadata
rows can be entered from the verified TSV. `row_number` is the physical TSV
record number, including header row 1. `source_sha256` is the compressed source
file's SHA-256. `key` and `value` must match that row after whitespace trimming.

For each reviewed sample, supply `sample_kind`, `reviewer`, `reviewed_at` (ISO
timestamp with timezone), and a source-backed `rationale`. Only after review,
change the top-level `status` from `draft` to `approved`. The schema is strict:
no extra fields, duplicate JSON keys, duplicate samples or duplicate evidence
rows. Limits: 1 MiB, 200 decisions and 32 evidence rows per decision. Missing
evidence, stale snapshots, mismatched values/hashes and draft reviews fail closed.
There is no independent `is_control` override; it is derived from `sample_kind`.

Validate without publication:

```bash
python scripts/normalize_anemone.py --snapshot-id <snapshot-id> \
  --raw-root <local-raw-root> --classification-review <review.json>
```

After inspecting the report, `--execute --normalized-root <local-normalized-root>`
publishes a new immutable normalization. Activation requires a separate explicit
`--activate`; neither command imports PostgreSQL or runs a model.

## Registered job delivery

With an approved artifact store and working directory configured:

```bash
python scripts/run_anemone_job.py --stage classification-review --execute \
  --classification-review <review.json>
python scripts/run_anemone_job.py --stage normalize --execute \
  --artifact-id <raw-artifact-id> \
  --classification-review-artifact-id <review-artifact-id>
```

The first command registers the schema-validated review in the immutable
`classification-reviews` namespace. Registration is **not** evidence validation
or scientific acceptance: normalization verifies the review against the raw
snapshot. The second command resolves a registered, hash- and generation-checked
review, verifies its evidence, and publishes the normalized artifact. Direct
local normalization also accepts `--classification-review <review.json>`.
Review options on unrelated stages are rejected. All job stages default to an
offline plan unless `--execute` is supplied. Paid GCP work still requires the
budget and deployment gates in the [pilot runbook](../deploy/gcp/ANEMONE_PILOT.md).

## Controlled database-review application

Migration `20260905_0011` adds a resumable application ledger and append-only
stage receipts. Before the first production run, register the exact processing
service account through the dry-run-first command documented in the
[pilot runbook](../deploy/gcp/ANEMONE_PILOT.md). The job derives its operational
identity from that registration and the deployment environment; there is no
editable operator or reviewer field.

The existing processing job accepts one approved review UUID and executes:

1. immutable review-artifact registration;
2. exact raw-snapshot restoration and normalization;
3. transactional canonical import;
4. retrieval materialization and publication;
5. regeneration of registered analyses containing the affected sample;
6. refresh of missing or stale embeddings for that sample;
7. provenance publication; and
8. the final operational application receipt.

Every stage revalidates the approved record, content digest, source snapshot,
compressed-file hash, TSV row/value evidence, canonical sample, and review
history. The operation ID is the idempotency key. A completed replay returns the
existing receipt. A failed or interrupted replay resumes after completed stage
receipts; a stage that may have committed without its receipt is safely invoked
again through its existing immutable/upsert contract.

Rollback is a compensating application, not an unreviewed database restore. A
new approved review must explicitly supersede the applied review for the same
sample and the operator must pass the prior application UUID with
`--rollback-of`. `unknown` remains valid. Earlier application, normalization,
analysis, retrieval, and provenance identities remain retained for audit.

The API and browser do not launch Cloud Run. Production execution remains a
manual operator action. Failure records contain stage/error codes and fixed
recovery instructions, never arbitrary exception bodies.

## Persistence, migration and correction

- Apply Alembic head `20260905_0011` before controlled application. The earlier
  `20260903_0008` migration adds
  nullable `edna_sample.classification_review_json`; existing samples and raw
  metadata are unchanged. Bootstrap readiness checks the column; the importer
  rejects an unmigrated schema instead of dropping the review field.
- Normalization version 2 adds the review field to the canonical sample table.
  Review input is part of normalization identity. `classification_basis` stores
  `review:<SHA-256 of the sample review record>`; the complete record includes
  the original provider classification basis and whole-review digest.
- The manifest and canonical sample retain the attestation. Retrieval metadata,
  sample-detail API, canonical-row provenance and analysis input/export snapshots
  carry it forward. Chat evidence identifies researcher-reviewed classification
  rather than representing it as an explicit provider label.
- Sample/assay/detection identities remain stable. Raw metadata, source files,
  sequence assignments, read counts and units are not rewritten. A classification
  change updates the sample scientific hash and changes downstream identities;
  deterministic replay is unchanged. Earlier normalized and analysis bundles
  remain available by ID. Re-materialize, refresh affected embeddings as needed,
  rerun analyses and publish provenance after an approved canonical import.
  Provenance retains multiple normalizations of the same raw snapshot and links
  documents by exact canonical sample row hash, including reviewed variants.
- Correct a decision by submitting a new reviewed input against the same raw
  snapshot; it creates a new normalization. Reviews do not automatically carry
  to a later source snapshot. Explicitly importing an unreviewed/pre-v2 bundle
  clears a later review and restores unknown classification; this is a reviewed
  rollback operation, never an automatic fallback. Stale environmental anchors
  are inactivated. Preserve reviewed artifacts before any rollback.
- Dropping migration `0008` deletes the canonical review column. Do not downgrade
  it on a live database without backup and rollback review. No automatic review
  deletion, cleanup, retention policy or production migration is included.

## Real pilot

The retained `20171218T0103-KUM-Otomi-Surface` canary remains unknown. An
[environmental-water proposal](ANEMONE_PILOT_CLASSIFICATION_PROPOSAL.md) cites
five verified provider rows but remains unapproved. A qualified researcher must
confirm field water versus blank/control and supply their real review details.
Synthetic test attestations are not real scientific acceptance.

Templates and normalization resolve the exact acquisition contract from the
snapshot hash. The archived v1 contract keeps this pilot reproducible after
revision 2 added metadata-only non-target files. Neither the source nor its
classification is silently migrated. Draft review inputs remain non-executable.

Browser billing access and existing controls are now verified in the
[canary record](ANEMONE_PILOT_2026-09-03.md#billing-follow-up--2026-09-03).
Updated spend headroom, cloud execution, model-answer review, merge, deployment
and release remain separate gates.

Local verification: 620 backend tests passed (9 database-gated skips), 77.08%
coverage, and all 9 PostgreSQL integration tests passed separately. Migration,
replay/reversion, retained provenance and ZIP exports are covered. Full details
are in [Testing and CI](TESTING.md#anemone-classification-review--2026-09-03).
