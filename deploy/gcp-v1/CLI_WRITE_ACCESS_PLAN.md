# Approved unattended beta build and deployment access

Status: approved by the user and applied on 2026-11-02 JST. Exact grants were
read back and matched this plan. A synthetic image build/push succeeded, and
Cloud Run accepted a validation-only update with the live service unchanged.
No application rollout was performed.

Principal: `serviceAccount:ocean-v1-beta-cli@ocean-v1-beta-20261101.iam.gserviceaccount.com`.
Project: `ocean-v1-beta-20261101`. Region: `asia-northeast1`.
The existing local credential and wrapper would continue to be used.

## Exact approved grants

| Resource | Grant | Effect |
| --- | --- | --- |
| Project `ocean-v1-beta-20261101` | `roles/cloudbuild.builds.editor` | Submit, inspect, cancel, and retry builds. Cloud Build also uses the build-create permission for trigger management. This permission is project-wide, not confined to a single build configuration. |
| Project `ocean-v1-beta-20261101` | `roles/serviceusage.serviceUsageConsumer` | Use enabled APIs and project quota; does not permit enabling APIs. |
| Service account `ocean-v1-beta-build@ocean-v1-beta-20261101.iam.gserviceaccount.com` | `roles/iam.serviceAccountUser` | Submit builds using the existing beta build identity. Does not grant token-creation permission. |
| Service account `ocean-v1-beta-serving@ocean-v1-beta-20261101.iam.gserviceaccount.com` | `roles/iam.serviceAccountUser` | Deploy revisions using the existing beta serving identity. Does not grant token-creation permission. |
| Cloud Run service `ocean-v1-beta-serving` in `asia-northeast1` | New project custom role `oceanBetaServiceDeployer`, containing only `run.services.update`, bound on this service | Update service configuration, deploy revisions, and adjust traffic on this existing service. No service-creation, deletion, or service-IAM permissions are included. |
| Artifact Registry repository `ocean-v1-beta` in `asia-northeast1` | `roles/artifactregistry.reader` | Read image metadata and images for deployment. The existing build identity already has repository writer access. |
| Bucket `gs://ocean-v1-beta-20261101-build-source` | `roles/storage.objectCreator` and `roles/storage.legacyBucketReader` | Upload new source archives and inspect the staging bucket/object listings. No object deletion or replacement permission is granted to the CLI identity. |

Existing inspection/logging roles would be retained. No grant is proposed in the
legacy `data-infra-infobio` project. No direct Secret Manager access, database
administration, job execution, service-account-key creation, project Owner/Editor,
or IAM administration role is proposed.

## Approved effects and limits

Deployment permission allows new code to run with the serving identity's existing
database and secret access. Lack of a direct secret-access role on the CLI
identity does not isolate deployed code from runtime data. Service-update access
also permits changing service settings; it is broader than replacing an image.

Cloud Build submission starts billable work. Its project-wide build-create
permission can also affect triggers and may allow use of the legacy Cloud Build
identity depending on project configuration. Explicitly selecting the bounded
build identity is the intended workflow, not an IAM restriction on every possible
build request. No organization-policy changes are proposed.

New services, migration/job execution, databases, network configuration, billing,
IAM, and legacy resources require their own specific scope.

## Validation procedure

1. Apply the exact grants sequentially, preserving existing bindings, and read
   back their scopes.
2. Use the isolated Mac service-account store for all capability checks.
3. Submit a small synthetic image build, with a 120-second build timeout, using
   the existing bounded build identity, dedicated staging bucket, repository,
   and Cloud Logging. Do not upload the application checkout or private data.
4. Validate an update against the freshly read beta service using Cloud Run's
   `validateOnly=true` API option. Do not create a revision, modify traffic, or
   replace the application as part of this authentication verification.
5. Check that service deletion, service IAM changes, migration-job execution,
   and legacy service access remain denied. Remove temporary test artifacts.
6. Update `AGENTS.md` and `CLI_AUTOMATION.md` to describe only the capabilities
   actually granted and verified.

## Verification result

- Build `7af7f1df-cb46-4062-9b00-cd7a08f46b00` completed with `SUCCESS` in
  `asia-northeast1`, using the bounded beta build identity, source-staging bucket,
  repository, and Cloud Logging. Only synthetic test files were submitted.
- The test image was pushed with digest
  `sha256:6de4791ffe20d7b6e870229940bc4c948e8028c4060251c17a0399468f3ddea2`.
- Cloud Run accepted an HTTP 200 `validateOnly=true` update request. Service
  generation `7`, revision `ocean-v1-beta-serving-00007-lxt`, traffic, and
  template were unchanged across that check. Validation returns a synthetic
  operation that is not persisted; no live rollout/startup test is claimed.
- Effective permission checks returned `run.services.get` and
  `run.services.update`, excluding service deletion and service IAM mutation.
  The checked migration job remained readable without run/update permission.
- Legacy project Cloud Run listing remained denied.
- The synthetic test image/tag and exact staging-archive generation were removed;
  follow-up listings confirmed neither remained active. The build result/log
  record remains available for verification.

Build record: [synthetic build verification](https://console.cloud.google.com/cloud-build/builds;region=asia-northeast1/7af7f1df-cb46-4062-9b00-cd7a08f46b00?project=534831104543).

For local Codex work, the Mac still needs to be awake and online with Codex
running. The service-account credential removes Google user-login prompts; it
does not remove Codex approval requirements or keep the browser signed in.

References: [Cloud Build roles and their scope](https://docs.cloud.google.com/build/docs/iam-roles-permissions),
[user-managed build identities](https://docs.cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts),
[Cloud Run deployment permissions](https://docs.cloud.google.com/run/docs/deploying),
and [Cloud Run validation-only updates](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.services/patch).
