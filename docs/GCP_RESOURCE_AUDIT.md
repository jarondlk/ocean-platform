# GCP resource audit

Last verified: 2026-08-25

Project: `data-infra-infobio` (`469489188516`), region
`asia-northeast1`.

## Active OCEAN Platform resources

| Component | Resource | State and guardrail |
| --- | --- | --- |
| Web application | Cloud Run `ocean-platform` | Revision `ocean-platform-00004-8tb`, 100% traffic, minimum 0 / maximum 1 instance, public invoker required for the authenticated frontend |
| Database | Cloud SQL `ocean-postgres` | PostgreSQL 16, `db-f1-micro`, 10 GB, RUNNABLE, deletion protection, seven backups and seven days of PITR |
| Scientific data | `gs://data-infra-infobio-ocean-data` | 113,841,102 live bytes at audit time, versioning and the reviewed scientific-data lifecycle enabled |
| Images | Artifact Registry `ocean-platform` | API and frontend images; keep five recent versions and delete versions older than 30 days |
| Runtime identities | `ocean-platform`, `ocean-jobs` | Enabled, keyless, and separated between serving and manual jobs |
| Secrets | Four `ocean-*` secrets | Access limited to the matching serving or job identity; no values are stored in deployment YAML |
| Batch definitions | Four `ocean-*` Cloud Run Jobs | Manual only, zero automatic retries, no scheduler or build trigger |
| Model runtime | Vertex AI managed models | Workload identity only; no custom model, endpoint, index, or index endpoint exists |

Authenticated validation after the audit passed for Overview, Data, Provenance,
Evaluation, and Admin/System. The application reported 323 retrieval documents,
207 samples, 162 CTD casts, 79 SST days, a healthy database, and an available
model runtime.

## Dormant legacy resources

The `onagawa-*` resources are a rollback set, not a second live environment:

- Cloud Run `onagawa-source-chat` has no public invoker, returns HTTP 403, has
  minimum scale zero, and received no request after the OCEAN cutover at
  2026-08-25 08:36 UTC.
- `onagawa-postgres` is STOPPED with activation policy `NEVER` and deletion
  protection enabled. Its final export is present in the OCEAN data bucket.
- The four `onagawa-*` jobs have no scheduler. Their last execution preceded
  cutover.
- `onagawa-app` and `onagawa-jobs` are disabled. They have no user-managed
  service-account keys, so the legacy service and jobs cannot start until an
  operator deliberately re-enables the identities.
- Artifact Registry `onagawa-source-chat` held approximately 4.1 GB at the
  start of the audit. The reviewed keep-five/delete-after-30-days policy is now
  active, retaining bounded rollback images while old versions age out.
- `gs://data-infra-infobio-prototype-data` held 111,240,263 live bytes. A
  recursive dry-run sync found no live object missing from the OCEAN bucket.
  The legacy bucket still has its own noncurrent object history, so deletion is
  treated as irreversible retirement rather than routine housekeeping.
- Four enabled `onagawa-*` secret containers remain only for rollback.

Rollback now requires re-enabling the two legacy service accounts and starting
the legacy SQL instance. Do not treat the dormant URL as an instant failover.

## Automatic housekeeping

- Both Artifact Registry repositories preserve the five newest versions and
  delete versions older than 30 days. The policies were promoted from dry-run
  after the image inventory was reviewed.
- The single `OCEAN Platform Cloud Run Web` OAuth client contains only the
  current OCEAN JavaScript origin and `/api/auth/callback/google` redirect.
  The two legacy `onagawa-source-chat` entries were removed and the persisted
  client configuration was re-read after saving.
- `gs://data-infra-infobio_cloudbuild` contains transient source archives only
  (15,191,629 bytes at audit time). `source/` objects expire after 30 days via
  [`deploy/gcp/cloudbuild-storage-lifecycle.json`](../deploy/gcp/cloudbuild-storage-lifecycle.json).
- Cloud Run serving minimum scale is zero. All Cloud Run Jobs are manual and
  Cloud Scheduler is disabled.
- The default log bucket retains 30 days. The locked required-audit bucket
  retains 400 days.

## Confirmed absent

The audit found no Cloud Build triggers, Scheduler jobs, Cloud Functions,
Compute Engine VMs, Serverless VPC Access connectors, Pub/Sub topics or
subscriptions, BigQuery datasets, Dataplex lakes, App Hub applications,
monitoring alert policies, notification channels, custom logging sinks, or
custom Vertex AI deployments.

Several console and data APIs are enabled without resources. An enabled API is
not a running process and normally has no resource charge by itself, so these
were not disabled merely to reduce the service list. Disable an API only after
checking service dependencies and operator workflows.

## Retirement actions requiring explicit approval

These actions remove rollback state and are intentionally not automatic:

1. Delete `onagawa-source-chat` and the four `onagawa-*` Cloud Run Job
   definitions.
2. Delete Artifact Registry `onagawa-source-chat` after choosing whether the
   five retained API/frontend images are still needed.
3. Delete `onagawa-postgres` only after confirming the final SQL export and
   restore evidence. This removes its 10 GB disk and managed backup history.
4. Delete `gs://data-infra-infobio-prototype-data` only after accepting loss of
   its independent noncurrent object history.
5. Delete the four `onagawa-*` secrets and then the two disabled legacy service
   accounts.

The project billing link is enabled, but the active CLI account cannot list the
billing-account budget objects. Budget configuration therefore remains a
billing-account IAM follow-up rather than a verified result of this audit.
