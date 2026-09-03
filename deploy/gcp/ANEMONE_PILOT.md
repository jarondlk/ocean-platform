# ANEMONE pilot operations

Status: the bounded unknown-classification pilot is deployed in `v0.4.0`;
see the [verified operations record](../../docs/RELEASE_0.4.0_OPERATIONS.md).
Full classification/scientific acceptance remains deferred. Use with
`docs/ANEMONE_PR5_PLAN.md`. This runbook does not approve
a download, paid execution, migration, deployment, or release.

Release scope update, 2026-09-03: the user approved keeping classification
unknown for `v0.4.0` and completing the workflow in the
[next patch](../../docs/ANEMONE_NEXT_PATCH.md). For this release, validate
retained source evidence, citations and explicit unknown-sample exclusions.
The full classified environmental/model-answer acceptance described below is
deferred, not passed. Backup, migrations, authorization, artifact integrity,
cost bounds and deployment verification still apply.

The first bounded real-data local canary is recorded in
[`../../docs/ANEMONE_PILOT_2026-09-03.md`](../../docs/ANEMONE_PILOT_2026-09-03.md).
It confirms storage/citation behavior; classification remains unknown under the
limited release scope above. The user confirmed JPY 20,000/month total. The canary record includes the
read-only billing check: JPY 10,000 project and JPY 4,000 SQL alert budgets,
plus a JPY 2,250 Cloud Run spend cap. Visibility is resolved; refresh posted
charges and headroom before paid execution. Do not raise these controls implicitly.

## Preconditions

- Approve one explicit sample, followed by at most one named sequencing run.
  Review provider use, attribution, export/redistribution and retention terms.
- Set file/byte, staging-memory, model-request, latency and cloud-spend bounds.
  Current canary defaults: 20 files, 64 MiB selected download. Hard acquisition
  maxima: 2,000 files and 512 MiB; decompressed TSV maximum: 64 MiB per file.
  Contract revision 2 inventories QCauto/3-NN non-target TSVs as metadata-only,
  like FASTQ/images: count them toward the file limit, but do not download or
  analyze them. The five required target/metadata TSVs are unchanged. Preserve
  `data_contracts/history/anemone_mifish_v1.json` in deployed images; historical
  snapshots resolve that exact approved contract by hash, never a guessed revision.
- Regenerate the short-lived download password outside chat. Store username
  and password in Secret Manager; record numeric versions and expiry, never
  values. A previously pasted credential is not a deployment credential.
- Record the application commit and build digest, existing deployed revisions,
  schema head, current artifact/provenance pointers, and bucket configuration.
- Rehearse database backup/isolated restore and migrations before a live import.
  A fresh isolated database needs `bootstrap_database.py` to create legacy
  corpus tables as well as applying Alembic migrations; Alembic alone is not
  a complete bootstrap.
  `bootstrap_database.py --check-only` must report every required table,
  including `corpus_publication` and `edna_sample.classification_review_json`.
  The classification follow-up adds migration `20260903_0008`; apply it before
  importing v2 normalizations. Earlier pilot records used head `20260902_0007`.

## Storage and identities

`EDNA_ARTIFACT_URI=gs://<approved-bucket>/edna` selects registered object storage.
An absolute `file://` URI exercises the same protocol without contacting GCP.
Leave it blank to keep the existing local filesystem mode.

`EDNA_CACHE_DIR` must be local POSIX storage, normally `/tmp/ocean-edna-cache`.
Never put it on a GCS FUSE mount. With object storage selected, raw and
normalized ANEMONE paths use this cache automatically; legacy sources can
remain on the read-only `DATA_DIR=/mnt/ocean-data` mount.

Objects are create-only, hashed, and pinned to storage generations. A verified
receipt is registered through a conditional index update. Every analysis run
is retained; no automatic cleanup or retention deletion is enabled. Cache and
staging files are disposable, but bucket artifacts are research records.
The serving retrieval cache is capped at 512 MiB and concurrent cache fills are
serialized locally. A full cache fails explicitly; replace only the disposable
cache or serving instance after review, never remove registered bucket records.
Job memory/staging capacity must be measured on the approved pilot; template
resource values are starting limits, not evidence of sufficient capacity.

Review least-privilege IAM before creating/applying jobs:

- `ocean-anemone-sync`: access only its two secret versions and the artifact
  `raw/` and `operations/` prefixes. No Cloud SQL or Vertex permissions.
- Processing identity: approved artifact/provenance access and Cloud SQL access;
  no ANEMONE download secrets. Review existing `ocean-jobs` grants rather than
  granting project-wide roles for convenience.
- Serving identity: read-only registered artifacts/provenance; no acquisition
  secrets, artifact writes or batch execution from requests.
- Embedding/model calls remain separate bounded jobs with reviewed model IAM.

Create-only uploads and conditional pointer replacement use Cloud Storage
generation preconditions. No directory rename is performed on the bucket.
[Google storage preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions)
File-mounted credentials follow Cloud Run's secret-volume mechanism.
[Google job secret configuration](https://docs.cloud.google.com/run/docs/configuring/jobs/secrets)

## Templates

`render_gcp_templates.py --include-anemone` additionally requires:

- `--anemone-image-digest sha256:<64-hex-digest>`;
- `--anemone-username-version <positive-integer>`;
- `--anemone-password-version <positive-integer>`.

These are identifiers, not secret values. Existing renderer options still
apply. No GCP API is called by rendering. The two new job templates have one
task, parallelism one, zero automatic retries, a 1,800-second timeout and an
offline-plan default. Applying a template or executing a job is a separate
operator action. The process job's scientific-data mount is read-only.

## Stages

The following is an offline plan and performs no authentication or network I/O:

```bash
python scripts/run_anemone_job.py --stage inventory
```

After preconditions are approved, the operator adds `--execute` to authorize
one named stage. `--validate-only` on an import performs the exact SQL merge
inside a rolled-back transaction; it does not alter publication readiness.
Do not mistake the outer `--execute` flag for permission to omit review.

1. `inventory --execute --scope-url <approved-url>`: list/check scope and sizes;
   no scientific files downloaded. Inspect all validation issues.
2. `acquire --execute --scope-url <approved-url> --max-files <limit>
   --max-bytes <limit>`: download interpreted files only and publish a raw
   transport artifact. Save both its artifact ID and source snapshot ID.
3. `normalize --execute --artifact-id <raw-artifact-id>`: restore/verify source
   bytes locally, normalize, and publish a normalized transport artifact.
   Transport IDs hash the complete transported files; they are distinct from
   source snapshot IDs and normalization IDs. Do not interchange them.
4. `import --execute --validate-only --artifact-id <normalized-artifact-id>`:
   inspect inserted/updated/unchanged/inactivated counts using an isolated DB.
5. `import --execute --artifact-id <normalized-artifact-id>`: approved eDNA-only
   merge. No legacy corpus or user/chat tables are loaded or reset. Publication
   becomes pending before canonical changes commit; materialization is required
   even when replaying an import.
6. `materialize --execute`: build all active eDNA documents within pilot limits,
   upload/verify objects, commit their DB generation, and conditionally mark
   that exact generation ready. Maxima: 2,000 samples, 2,000 assays and 250,000
   detection rows. Excess input fails instead of truncating.
7. Run the existing separately approved embedding job with a bounded document
   limit. Confirm provider/model/dimension and unchanged legacy embeddings.
8. From the reviewed local files, `recipe --execute --recipe <reviewed-json>`
   (optionally `--environment <reviewed-json>`) publishes an immutable recipe
   artifact. The cloud job uses `analyze --execute --artifact-id <recipe-artifact-id>`
   to read that exact configuration and generate method-separated results.
   Direct local `analyze --recipe` is also supported. Recipe/environment limits
   are 1/16 MiB; analysis bundles are at most 128 MiB. Recipe publication does
   not constitute scientific approval. Do not bake provider data or credentials
   into an image to supply them.
9. `provenance --execute --validate-only`, then `provenance --execute` after
   inspecting the result. This restores retained normalized pilot artifacts
   needed for traces (at most 20 bundles and 512 MiB aggregate) and includes all
   registered historical analyses. Legacy artifacts must be available through
   the read-only mount. Do not publish a partial manifest to bypass missing data.

Every executed stage records a credential-free operation report locally and
in the `operations/` object namespace. Reports contain stage, IDs, counts,
timestamps, available Cloud Run execution IDs and optional `SOURCE_COMMIT`.
Errors expose only a type, not arbitrary HTTP/exception bodies. Inspect the
safe component diagnostics and operation status when repairing a failure.
Failure to publish the report returns failure even if the stage committed;
do not assume that failure means the database rolled back.

For generation-capable stages `--validate-only` validates/computes without
publication. Normalization itself is artifact publication, not a DB import.
The acquisition and processing stages are separate: never invoke the entire
legacy pipeline simply to load ANEMONE.

## Scientific review and saved-answer checks

Record independently checked composition/diversity/method values, control
classification, missing data, source units and limitations. Do not claim read
counts measure abundance or that method agreement proves accuracy.

Some real provider samples lack explicit supported classification metadata.
Keep those samples `unknown`; do not infer environmental/non-control status
solely from a name, collection device or coordinates. Obtain a source-backed
review through the [classification workflow](../../docs/ANEMONE_CLASSIFICATION_REVIEW.md)
before including them in environmental-only analyses. It provides a non-executable
draft, exact source-row verification and registered review delivery. A reviewer
attestation is still required; implementation does not classify the real pilot.
Never edit immutable source files or canonical rows to make a pilot appear eligible.

Use an authenticated preview/candidate revision to run the six questions in
`evaluation/edna_research_cases.json`. Save complete request/response JSON and
case-specific analysis IDs. Additional generic retrieval, mixed-source,
historical navigation and role/export checks remain on the release checklist.
Keep live observations separate from synthetic negative-control cases.

Each record in a JSON array has:

```json
{
  "case_id": "method_dependence",
  "kind": "live",
  "latency_ms": 1000,
  "request": {"query": "<exact case question>", "analysis_id": "<full analysis ID>"},
  "response": {"<complete ChatResponse fields>": "<saved values>"},
  "review": {
    "verdict": "accepted",
    "reviewer": "<researcher>",
    "reviewed_at": "<ISO date/time>",
    "notes": "<source/table checks and limitations>",
    "source_values_checked": true,
    "unsupported_scientific_claims": false
  }
}
```

The example is a shape, not an accepted record. Do not fill in an acceptance
verdict until a researcher has performed that review.

```bash
python scripts/evaluate_edna_pilot.py --records <saved-records.json> --max-latency-ms 120000
```

The checker recomputes citation validity, resolves provenance, checks exact
analysis/result IDs, reports missing/duplicate cases and latency failures,
and requires explicit human review. It performs no model calls. At least one
accepted live case is required; all-synthetic validation cannot pass the live
pilot gate. Reviewer identity and live/synthetic labels are operator assertions,
not cryptographically authenticated attestations. This is not an automated
scientific-accuracy evaluator or deployment authorization.

## Recovery and release

- A failed acquisition/upload leaves unregistered objects unserved. Replay is
  create-only; differing bytes or generations produce a conflict, not overwrite.
- If import commits but materialization fails, eDNA remains unavailable.
  Inspect the report and rerun materialization under its existing DB lock. Do
  not force an old ready pointer over new canonical data.
- PostgreSQL retrieval requires the object-store ready pointer to match the
  recorded DB generation. Fallback reads reject pending/mismatched bundles.
- A CAS conflict requires a fresh read/review, not an unconditional overwrite.
- Old analyses remain readable/citable, but historical or unverifiable inputs
  are not injected as current analysis context. Pre-registry local analyses
  must be reproduced from verified inputs; there is no trust-existing-folder
  shortcut. Preserve old artifacts for audit until reviewed migration is done.
- Retain the previous application revision and database backup. Avoid automatic
  schema downgrades or restoring over new user/chat metadata. Rehearse recovery
  in isolation and record a consistent corpus/embedding/provenance state.

No live CTD/SST profile is enabled by this implementation. Source-specific
extraction, site/unit/coverage review and actual temporal/spatial overlap must
precede environmental linking. Missing overlap does not block ANEMONE-only
research; it does block claims of validated live cross-source integration.

Release `v0.4.0` only after the operational checks for the limited scope above:
real source/GCS integrity, backup/restore, authenticated UI/API/export checks,
correct unknown-sample exclusions, approved spend, a committed image build
and deployment verification. The broader classified scientific/model-output
acceptance remains next-patch work, not a completed gate.
