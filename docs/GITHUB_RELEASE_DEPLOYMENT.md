# Manual GitHub release deployment

Status on 2026-09-16: the user approved the exact permission plan below after
an automatic approval review block. GCP identities and GitHub production
environment variables have been provisioned. Live GitHub verification is pending.

## Use after activation

In GitHub, open **Actions → Deploy release → Run workflow**. Select branch
`main`, enter a published stable tag such as `v0.4.5`, and choose:

- `verify` (default): authenticate, check release ancestry, inspect live settings,
  and check data/schema compatibility. No build or production mutation.
- `deploy`: perform those checks, build and test an archive of the exact release
  commit, create and restore-test a database backup, deploy a candidate without
  production traffic, check HTTP routes, update the five existing job images,
  run a read-only schema check, promote traffic, and check production routes.

Publishing a release or pushing a commit does not trigger deployment. Concurrent
runs are serialized. The workflow records successful deployment against the
release commit, which can differ from the commit containing deployment tooling.

Candidate readiness and HTTP smoke tests check availability and authentication
boundaries. They do not replace authenticated browser acceptance or scientific
chat QA. A release that changes database/schema or data-generation paths stops
for a coordinated rollout; this workflow does not migrate data or regenerate
embeddings and provenance. The v0.4.5 refresh is already complete.

Failed promotion attempts restore the previous traffic and job images when
possible. An unexpected traffic change by another operator stops automatic
traffic rollback. A forced runner termination can prevent cleanup; inspect the
workflow summary and Cloud Run before retrying. Failed candidate revisions and
backups are retained for review. Build timeouts can leave a Cloud Build running.

## Exact permission plan requiring approval

Project: `data-infra-infobio` (`469489188516`). The setup creates two dedicated
service accounts, one workload identity pool/provider, four custom roles, and
additive IAM bindings. It enables the Security Token Service API.

| Identity / resource | Granted access and purpose |
| --- | --- |
| GitHub repository `jarondlk/ocean-platform`, numeric ID `1224179187`, owner ID `82869981` | Exchange GitHub OIDC credentials for the dedicated deployment account only when the manual `deploy-release.yml` workflow runs from `main` in the `production` environment |
| `ocean-release-deployer` | Submit/read Cloud Builds, consume enabled APIs, read project metadata and Cloud Run operations |
| Existing Cloud Run service `ocean-platform` | Read/update the service and inspect revisions, including replacing images and switching production traffic |
| Existing jobs `ocean-migrate`, `ocean-pipeline`, `ocean-embedding`, `ocean-evaluation`, `ocean-anemone-process` | Read/update job configurations and inspect executions |
| Existing jobs `ocean-pipeline` and `ocean-migrate` | Execute jobs with argument overrides for backup/restore verification and read-only schema checks |
| Service accounts `ocean-release-build`, `ocean-platform`, `ocean-jobs` | Deployment account may attach these identities to builds or Cloud Run resources (`serviceAccountUser`); no service-account keys are created |
| Existing source bucket `data-infra-infobio_cloudbuild` | Deployment account may inspect the bucket and create/read build-source objects; build account may read source objects |
| `ocean-release-build` | Write images to the existing `ocean-platform` Artifact Registry repository and write build logs |

The deployment account receives no Owner, Editor, IAM-administration, billing,
resource-delete, or direct Secret Manager access. The existing broadly privileged
Compute Engine default identity is not used for new builds.

**Security consequence:** code deployed through this workflow runs with the
existing application/job identities and their existing database, storage, and
secret access. Anyone able to change the trusted workflow on `main` and run it
can use that deployment authority. Job argument overrides can execute code as
`ocean-jobs`. These are persistent production deployment permissions even though
the individual login tokens are temporary. The current GitHub production
environment has no additional reviewer requirement; repository protections and
manual dispatch control who can use this path.

The exact commands, role permissions, and OIDC condition are in
[`deploy/gcp/setup-github-deploy.py`](../deploy/gcp/setup-github-deploy.py).
Running it without arguments prints the plan and does not contact GCP. Applying
requires `--apply` with an administrator's existing GCP session. If provisioning
was interrupted, inspect existing resources against the plan before resuming;
existing resources are not silently replaced.

After approval, set these non-secret GitHub production-environment variables:

```text
GCP_RELEASE_IDENTITY_PROVIDER=projects/469489188516/locations/global/workloadIdentityPools/ocean-github/providers/release-workflow
GCP_RELEASE_SERVICE_ACCOUNT=ocean-release-deployer@data-infra-infobio.iam.gserviceaccount.com
```

Activation verification: inspect live IAM against this plan, merge the workflow
through required CI, and run `verify` for `v0.4.5` from `main`. A subsequent manual
`deploy` run validates the full build and rollout path. Do not describe the
workflow as live until the actual GitHub identity exchange succeeds.

## Authentication design

GitHub OIDC uses Workload Identity Federation through the dedicated deployment
account. The workflow requests a one-hour access token for build operations and
obtains another after the build for deployment. No long-lived JSON key is stored
in GitHub. Generated credential files are excluded from Git, Docker, and Cloud
Build contexts; build source comes from a clean `git archive` of the release.

References: [Google's deployment federation guide](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
and [Google GitHub authentication action](https://github.com/google-github-actions/auth).
