# Provenance snapshot runbook

The hosted Provenance API serves a validated, immutable snapshot. It must not
scan raw files, recurse through the SST collection, read Parquet artifacts, or
query all embedding rows during an HTTP request.

## Safety contract

- `PROVENANCE_READ_MODE=build` retains the legacy local-development behavior.
- `PROVENANCE_READ_MODE=snapshot` reads only the published snapshot and has no
  dynamic-build fallback.
- Snapshot publication is explicit. Validation and legacy local writes do not
  update the production pointer.
- Every manifest object is immutable. Reusing a manifest ID fails.
- `latest.json` advances only after the stored manifest bytes are downloaded
  and verified.
- Cloud Storage generation preconditions reject competing pointer updates.

The GCP service and pipeline job use:

```text
PROVENANCE_SNAPSHOT_URI=gs://data-infra-infobio-prototype-data/provenance
```

The serving identity needs Storage Object Viewer. The pipeline identity needs
Storage Object User. Both use Application Default Credentials; no downloaded
key is required.

## Local validation

Build every document, validate schema v2, and print only integrity metadata:

```sh
python scripts/build_provenance_manifest.py \
  --validate-only \
  --run-id=local-validation-YYYYMMDD \
  --pipeline-run-id=local-validation \
  --no-embeddings
```

For a disposable local publication:

```sh
python scripts/build_provenance_manifest.py \
  --publish \
  --run-id=local-publication-YYYYMMDD \
  --pipeline-run-id=local-publication \
  --snapshot-uri=file:///tmp/onagawa-provenance
```

Do not point local tests at the production bucket.

## Cloud publication

`publish_provenance` is the final default pipeline stage. A real publication
requires a unique non-empty pipeline tag. Dry-run remains the stored Cloud Run
Job default and does not write objects.

Run a publication-only dry-run first:

```sh
gcloud run jobs execute onagawa-pipeline \
  --project=data-infra-infobio \
  --region=asia-northeast1 \
  --args=scripts/run_pipeline.py,--stages=publish_provenance,--dry-run,--no-embed,--tag=provenance-YYYYMMDDTHHMMSSZ \
  --wait
```

After reviewing the planned command and database/artifact preflight, replace
`--dry-run` with `--execute`. Do not reuse a prior tag.

Publication must follow any pipeline or standalone embedding operation that
changes corpus or embedding state. A corpus-changing operation is not complete
until its snapshot publication succeeds.

## Service rollout

1. Build and test an immutable image.
2. Run snapshot validation without publication.
3. Publish the first cloud snapshot.
4. Verify `latest.json`, object SHA-256, object size, schema version, 323
   prototype documents, and 323 embedded-document records.
5. Render the service with `PROVENANCE_READ_MODE=snapshot` and the GCS URI.
6. Deploy without changing traffic, then run authenticated manifest and trace
   checks against the candidate revision.
7. Repeat the bounded concurrent route test.
8. Move traffic only after the performance gates pass.

The serving cache lasts 60 seconds. A publication can therefore take up to one
cache interval to appear on a warm instance.

## Failure behavior

Missing pointers, missing manifests, invalid schemas, digest or size mismatch,
and inconsistent counts return HTTP 503 with code
`provenance_snapshot_unavailable`. The service never starts a corpus scan as a
fallback. Chat, retrieval, data, and health endpoints remain independent.

If publication fails before the pointer update, the prior snapshot stays live.
An unreferenced immutable object may remain. Record and review it; do not add a
blind age-based lifecycle rule because it could delete the current snapshot
when the corpus has not changed for a long period.

## Rollback

Route traffic to the preceding Cloud Run revision. Snapshot publication makes
no database changes and does not modify corpus objects, so rollback requires no
database downgrade. Preserve the failed pointer and manifest generations for
diagnosis before publishing a corrected unique manifest ID.

## Acceptance gates

- manifest warm p95 is at most 500 ms;
- manifest cold p95 is at most 2 seconds;
- document trace warm p95 is at most 300 ms;
- twelve concurrent manifest requests have p95 at most 2 seconds;
- one cold concurrent window performs one pointer load and one manifest load
  per API process;
- no raw scan, recursive SST traversal, Parquet read, artifact hash, or full
  embedding query occurs in the HTTP request path; and
- snapshot errors do not affect other routes.

The interactive upsert dry-run remains separate follow-up work. It should move
to an external pipeline result before broader Provenance use.
