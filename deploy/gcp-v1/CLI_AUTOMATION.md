# Mac CLI automation for the beta project

The dedicated service account is
`ocean-v1-beta-cli@ocean-v1-beta-20261101.iam.gserviceaccount.com`.
It is for unattended commands on the operator's Mac in
`ocean-v1-beta-20261101`, region `asia-northeast1`.

Use this wrapper for authorized beta work, including commands run by a coding
agent on this Mac:

```sh
./scripts/gcloud_beta.sh run services list
./scripts/gcloud_beta.sh run jobs list
./scripts/gcloud_beta.sh builds list --region=asia-northeast1 --limit=5
./scripts/gcloud_beta.sh logging read 'resource.type="cloud_run_revision"' --limit=10
```

The account has these project-level roles:

- `roles/run.viewer`: Cloud Run service, job, revision, and execution metadata.
- `roles/cloudbuild.builds.viewer`: build status and configuration.
- `roles/logging.viewer`: regular logs, excluding private Data Access logs.
- `roles/cloudbuild.builds.editor`: build submission and management, including
  trigger changes covered by Cloud Build's project-wide build-create permission.
- `roles/serviceusage.serviceUsageConsumer`: use enabled APIs and project quota.

It also has the resource-specific grants in the approved
[write-access plan](CLI_WRITE_ACCESS_PLAN.md): use of the existing build/serving
identities, update-only access to the existing serving service, repository reads,
and uploads to the build-source bucket. Deployment can run code with the serving
identity's existing database and secret access. The CLI identity has no direct
secret-value or database-administration grant, service-creation/deletion grant,
service-IAM mutation grant, or migration/bootstrap job execution grant.

For image builds, use an explicitly reviewed source directory/configuration:

```sh
./scripts/gcloud_beta.sh builds submit "$SOURCE_DIRECTORY" \
  --config="$BUILD_CONFIG" \
  --region=asia-northeast1 \
  --service-account=projects/ocean-v1-beta-20261101/serviceAccounts/ocean-v1-beta-build@ocean-v1-beta-20261101.iam.gserviceaccount.com \
  --gcs-source-staging-dir=gs://ocean-v1-beta-20261101-build-source
```

The build configuration must use `options.logging: CLOUD_LOGGING_ONLY` with this
identity, or another separately authorized logging destination. Push images to
`asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta`. The build
identity already has writer access there. Inspect the current multi-container
serving definition and deploy only approved images/configuration to
`ocean-v1-beta-serving`; preserve unrelated settings and runtime identities.

## Local authentication

The private key and isolated gcloud credential store live in
`$HOME/.config/gcloud-ocean-v1-beta/`, outside the repository. The directory is
owner-only and the key file is owner-readable/writable only. Do not copy its
contents into source control, logs, chat, or build artifacts.

The wrapper selects this isolated store and service account for each command,
clears inherited token and impersonation overrides, and disables interactive
prompts. It does not depend on the personal Google refresh token or change the
default personal gcloud configuration. A failed automation login returns an
error instead of opening a browser or falling back to the personal account.

The key can continue obtaining short-lived access tokens without a personal
login while the key and account remain valid and policy permits their use.
Revocation, account disablement, or an organization-enforced key expiry still
ends access. Google recommends workload identity federation or an attached
service account for jobs hosted in environments that support those methods;
this local setup uses a service-account key because commands run directly on
the Mac.

This configures authentication only. It does not schedule recurring commands,
deploy application changes, or keep the Cloud Console signed in.

## Initial read-only verification on 2026-11-02 JST

This initial verification preceded the subsequently approved write grants.

- The isolated credential store contains only the dedicated service account.
- Real service/job listings, a regional build-status query, and a log query
  succeeded using that identity.
- Cloud Run's permission-check API confirmed read access and absence of job
  execution, service/job mutation, and service IAM mutation permissions on the
  checked migration job and serving service.
- Listing Cloud Run services in the legacy `data-infra-infobio` project was
  denied.
- The directory, key, and credential database were owned by the operator and
  inaccessible to group/other users.
- The personal default configuration retained its original account and project.
- The user-managed key has no practical configured expiry
  (`validBeforeTime=9999-12-31T23:59:59Z`); it remains revocable.

## Approved build/deployment verification on 2026-11-02 JST

The user approved the complete [write-access plan](CLI_WRITE_ACCESS_PLAN.md).
All grants were applied and read back with their exact resource scopes. Using
only the isolated service-account credentials, synthetic build
`7af7f1df-cb46-4062-9b00-cd7a08f46b00` completed successfully and pushed its
test image. Cloud Run accepted a validation-only service-update request with
the current generation, revision, traffic, and template unchanged. This tests
submission/push and update-request validation; no live application rollout was
performed. Service deletion, service-IAM changes, migration execution/update,
and legacy project access remained denied in the checked scopes.
The temporary test image and source archive were removed after verification.

## Disable unattended access

Use the personal administrator configuration to disable this dedicated identity:

```sh
gcloud --configuration=default iam service-accounts disable \
  ocean-v1-beta-cli@ocean-v1-beta-20261101.iam.gserviceaccount.com \
  --project=ocean-v1-beta-20261101
```

Google references: [CLI authentication](https://docs.cloud.google.com/sdk/docs/authenticate),
[separate configurations](https://docs.cloud.google.com/sdk/docs/configurations),
and [service account keys](https://docs.cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys).
