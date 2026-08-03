# GCP prototype migration plan

This plan moves the current local prototype to GCP in independently testable
stages. No stage advances until its integration gate passes. The initial
financial envelope is **JPY 10,000 per calendar month** for project
`data-infra-infobio`.

## Current cloud baseline

Live state verified on 2026-08-03:

- project billing is enabled and the linked JPY billing account is open;
- the project is in organization `735965963562`;
- the required foundation APIs are enabled, but no Cloud Run service, Cloud
  Run Job, or Cloud SQL instance exists;
- Artifact Registry repository `onagawa-source-chat` exists in
  `asia-northeast1`, is empty, and has cleanup rules in dry-run mode;
- service accounts `onagawa-app` and `onagawa-jobs` exist with no user-managed
  keys;
- the four named Secret Manager containers exist with no secret versions;
- regional bucket `data-infra-infobio-prototype-data` has public access
  prevention, uniform bucket-level access, versioning, and the reviewed
  lifecycle policy enabled; GCP's default seven-day soft-delete protection
  remains enabled;
- no application runtime component has been deployed; and
- the billing account has a Billing Account Administrator who can create and
  manage budgets.

This is a good migration starting point: cost controls can be installed before
the first runtime resource.

## Cost-control model

A normal Cloud Billing budget sends alerts but does not stop usage. The plan
therefore uses three layers:

1. a project-wide monthly alert budget;
2. service or `cost_component` label budgets for attribution and alerts; and
3. technical ceilings on every resource.

Cloud Run also supports a Preview spend-cap budget. The Cloud Run envelope is
**JPY 2,500/month**, with the enforced trigger set lower at **JPY 2,250/month**
to leave 10% headroom for delayed enforcement. It covers the serving service
and all Cloud Run Jobs together. It cannot distinguish jobs by label, so the
component budgets below remain alerts rather than hard stops. Spend-cap
enforcement is not instantaneous, and in-flight work can still exceed the
trigger slightly.

Do not automate disabling billing for the whole project. Disabling billing can
stop every service and can eventually delete resources. Persistent resources,
including Cloud SQL and Cloud Storage, also continue accruing fixed charges
when ordinary alert budgets are exceeded. Their resource-size and retention
ceilings are the primary controls.

### Monthly prototype envelope

| Component | JPY/month | Budget or technical ceiling |
| --- | ---: | --- |
| Cloud SQL PostgreSQL | 4,000 | Alert budget; `db-f1-micro`, zonal, no replicas, 10 GB SSD, automatic growth limited to 20 GB |
| Cloud Run serving | 1,200 | `cost_component=serving`; minimum 0, maximum 1 instance, concurrency 20 |
| Cloud Run migration job | 100 | `cost_component=migration`; manual only, one task, no retry, 15-minute timeout |
| Cloud Run pipeline job | 400 | `cost_component=pipeline`; dry-run default, manual execution, one task, no retry, 60-minute timeout |
| Cloud Run embedding job | 500 | `cost_component=embedding`; manual execution, batch size 32, one task, no retry, 60-minute timeout |
| Cloud Run evaluation job | 300 | `cost_component=evaluation`; quick suite first, one task, no retry, 60-minute timeout |
| Cloud Storage | 500 | Alert budget; one regional bucket; keep at most three noncurrent versions and delete them after 30 days |
| Cloud Build | 400 | Alert budget; manual builds only at first; 40-minute build timeout; no automatic branch trigger |
| Artifact Registry | 200 | Alert budget; keep five recent versions and remove older versions after 30 days |
| Secret Manager | 100 | Alert budget; four application secrets; no scheduled access polling |
| Logging and Monitoring | 300 | Alert budget; normal application logs only; no debug payloads or request bodies |
| Model runtime reserve | 1,000 | **Disabled initially**; no GPU/CPU Ollama VM; Vertex adapter and its own cap or quota required before use |
| Network and unclassified reserve | 1,000 | Covered by the project-wide budget; investigate any usage here before raising the envelope |
| **Project total** | **10,000** | Monthly alert budget at 50%, 75%, 90%, and 100%, plus a 95% forecast alert |

Budget amounts are operating guardrails, not cost forecasts or guarantees. Set
them below the maximum amount actually available because billing reports and
spend-cap enforcement can be delayed. Any increase requires an explicit review
of the prior seven days of cost by service and SKU.

### Budget ownership and notifications

- A principal with project-budget update permission creates and edits the
  project budget and the Cloud Run spend cap. Billing Account Administrators
  retain account-wide management access.
- Keep default IAM recipients enabled so Billing Account Administrators and
  Billing Account Users receive alerts.
- For a single-project budget, also notify project owners.
- Use `cost_component` labels from the deployment templates for advisory
  component budgets. The project-wide budget catches unlabeled or unsupported
  charges.
- Do not connect an automatic billing-disable action during the prototype.

## Migration order and integration gates

### Phase 0: governance and cost controls

Create no runtime resources.

Status on 2026-08-03: **complete**. The Cloud Billing Budget API is enabled and
the project-scoped Billing console shows both controls:

- `data-infra-infobio-monthly-guardrail`: JPY 10,000 monthly, actual alerts at
  50%, 75%, 90%, and 100%, and a forecast alert at 95%;
- `data-infra-infobio-cloud-run-spend-cap`: Cloud Run only, JPY 2,250 monthly
  enforced trigger, default notifications at 50%, 80%, and 100%, status
  `Configured`.

Both controls notify Billing Account Administrators/Users and project owners.
The CLI account still cannot enumerate account-wide budgets, so live checks
must use the project-scoped Billing console unless its IAM is expanded.

1. Enable only the Cloud Billing Budget API.
2. Create the JPY 10,000 monthly project alert budget.
3. Reserve JPY 2,500 for Cloud Run and create a JPY 2,250 enforced spend-cap
   trigger in the Billing console.
4. Record the budget owner and alert recipients.
5. Confirm which project-budget editors can raise the alert budget or lift the
   spend cap, and keep that access limited to project and billing operators.

Gate:

- budget scope is exactly `data-infra-infobio`;
- actual thresholds at 50%, 75%, 90%, and 100% and the 95% forecast threshold
  are visible;
- the Cloud Run spend cap is `Configured` at JPY 2,250 with 50%, 80%, and 100%
  notifications;
- both billing administration and project-owner recipients are confirmed; and
- no runtime API or component was created as part of this phase.

### Phase 1: non-runtime foundation

Run `prepare-foundation.sh` only after Phase 0 passes. It enables the required
APIs and creates the Artifact Registry repository, workload service accounts,
empty Secret Manager containers, and a regional data bucket.

Status on 2026-08-03: **complete**. The guarded script created the foundation
in `asia-northeast1` with bucket `data-infra-infobio-prototype-data`. The
storage lifecycle is active, the Artifact Registry cleanup policy remains in
dry-run mode, all secret containers have zero versions, and no Cloud Run or
Cloud SQL runtime exists.

Apply the prepared retention policies after reviewing them:

```sh
gcloud storage buckets update "gs://DATA_BUCKET" \
  --lifecycle-file=deploy/gcp/storage-lifecycle.json

gcloud artifacts repositories set-cleanup-policies onagawa-source-chat \
  --project=data-infra-infobio \
  --location=asia-northeast1 \
  --policy=deploy/gcp/artifact-cleanup-policy.json \
  --dry-run
```

Leave the Artifact Registry policy in dry-run until its matches have been
reviewed. Apply it later with `--no-dry-run`.

Gate:

- no user-managed service-account keys exist;
- `onagawa-app` can view data objects but cannot write them;
- `onagawa-jobs` can write data objects;
- only the named identities can access the intended secret containers;
- public access prevention and uniform bucket-level access are enabled; and
- the storage lifecycle and registry cleanup dry-run match only intended data.

### Phase 2: build and immutable artifacts

Run local tests before spending Cloud Build time, then submit `cloudbuild.yaml`
manually. Do not create a branch trigger yet.

Gate:

- backend tests and lint pass;
- frontend typecheck and production build pass;
- both images are stored under one immutable Cloud Build ID;
- a rendered manifest contains no unresolved tokens or secret values; and
- the registry cleanup policy preserves the five newest image versions.

### Phase 3: database and schema

Cloud SQL is the first persistent, always-billed runtime component. Create it
only after the previous phases pass. Use the guarded
`create-cloud-sql.sh`, create the database user out of band, add the database
secret version, and run the migration job manually.

Gate:

- instance tier, zonal availability, deletion protection, 10 GB initial
  storage, and 20 GB growth ceiling match the plan;
- PostgreSQL 16 and the `vector` extension are available;
- Alembic and corpus bootstrap complete once with no retry;
- both PostgreSQL integration modules pass against the migrated database;
- repeated upsert is idempotent; and
- a backup is verified by restoring it to a disposable database.

### Phase 4: restricted serving and authentication

Deploy the multi-container Cloud Run service with no public traffic first. The
Next.js container remains the ingress and FastAPI remains a localhost sidecar.
Keep the existing Auth.js Google OIDC flow and Cloud SQL-backed invitations and
roles.

Gate:

- service maximum is one instance and minimum is zero;
- `/health/live` succeeds through an authenticated operator path;
- FastAPI, Cloud SQL, and the model endpoint are not publicly reachable;
- login callback, invitation acceptance, viewer/researcher/admin permissions,
  logout, and suspension all pass;
- secrets and tokens do not appear in logs; and
- a previous image can receive traffic without a database downgrade.

Only after this gate passes should browser traffic be allowed to reach the
frontend.

### Phase 5: storage and batch pipeline

Upload a small representative data subset first. Execute the pipeline job in
dry-run mode, then run validation and a limited upsert without embedding. Add
the full dataset only after object counts and storage growth are understood.

Gate:

- dry-run produces the expected stages without mutations;
- validation, provenance manifests, and artifact freshness checks pass;
- the limited pipeline creates expected row and object counts;
- a second upsert makes no unintended changes;
- a pre-mutation backup and restore test pass; and
- noncurrent object versions obey the lifecycle policy.

### Phase 6: embeddings and model runtime

Do not create an Ollama VM as part of the baseline migration. It would add an
always-on compute cost that is not protected by the Cloud Run spend cap.
Implement the existing `model_runtime.py` provider boundary for a native Vertex
runtime first, or approve a separately costed private Ollama design.

Start with a small embedding sample and the quick evaluation job. Apply an
eligible service spend cap or a strict API quota and application-level request
limit before enabling general chat traffic.

Gate:

- model credentials use workload identity, not downloaded keys;
- request, token, and batch limits are configured;
- a small embedding batch has the expected dimension and row count;
- retrieval and citation checks pass against known questions;
- timeout, quota-exceeded, and unavailable-model paths fail safely; and
- the measured sample cost fits the JPY 1,000 model reserve.

### Phase 7: end-to-end prototype release

Run the full integration path with two invited test users before inviting the
research team.

Gate:

- sign in -> query -> retrieval -> model response -> citations -> feedback is
  successful;
- pipeline status, evaluation runs, and audit events survive a new Cloud Run
  revision;
- a controlled load test stays within one instance and the configured database
  connection pool;
- budget labels appear in cost reporting;
- rollback and database-restore runbooks are exercised; and
- the first 24-hour and seven-day cost reviews remain inside the envelope.

After seven stable days, maximum Cloud Run instances may increase from one to
two only if measured database connections and the remaining monthly budget
support it.

## Stop conditions

Pause migration and investigate before creating the next component when:

- actual spend reaches 75% of any component envelope earlier than expected;
- forecast spend reaches 95% of the project budget;
- a resource appears without `environment=prototype` and a component label;
- Cloud SQL grows past 15 GB;
- a job requests retry, parallelism, or a longer timeout;
- logs contain secrets, tokens, prompts with restricted data, or full request
  bodies; or
- a phase gate fails twice without an understood root cause.

## GCP references

- [Cloud Billing budgets and alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [Preview spend-cap budgets](https://cloud.google.com/billing/docs/how-to/budgets-spend-caps)
- [Cloud Run maximum instances](https://cloud.google.com/run/docs/configuring/max-instances)
- [Cloud SQL PostgreSQL instance settings](https://cloud.google.com/sql/docs/postgres/instance-settings)
- [Cloud Storage lifecycle management](https://cloud.google.com/storage/docs/lifecycle)
- [Artifact Registry cleanup policies](https://cloud.google.com/artifact-registry/docs/repositories/cleanup-policy-overview)
