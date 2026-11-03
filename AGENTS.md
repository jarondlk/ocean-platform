# Beta Google Cloud CLI access on the operator's Mac

For Google Cloud work within the granted scopes in `ocean-v1-beta-20261101`, use
`./scripts/gcloud_beta.sh` when its local configuration is present. It selects
a dedicated service account and isolated credential store, so these commands
do not depend on the operator's personal Google login.

The wrapper supports inspecting resources/logs, submitting Cloud Build image
builds, and updating the existing `ocean-v1-beta-serving` Cloud Run service.
For builds, explicitly select `asia-northeast1`, service account
`projects/ocean-v1-beta-20261101/serviceAccounts/ocean-v1-beta-build@ocean-v1-beta-20261101.iam.gserviceaccount.com`,
and source staging directory `gs://ocean-v1-beta-20261101-build-source`.
Build configurations must use `options.logging: CLOUD_LOGGING_ONLY` with this
identity, or another separately authorized log destination. Build images in
`asia-northeast1-docker.pkg.dev/ocean-v1-beta-20261101/ocean-v1-beta`.

Deployment rights cover service updates, not creating/deleting services or
changing service IAM. Read the current service before applying an authorized
update and preserve its identities, sidecars, secrets, ingress, and other
settings unless the task calls for changing them. Deployment permission allows
code to run with the serving identity's existing data/secret access.

Job execution, database administration, direct secrets access, IAM changes,
new services, and other operations need their own authorized scope. Existing
build/deploy capability does not authorize unrelated releases or IAM expansion.
See `deploy/gcp-v1/CLI_WRITE_ACCESS_PLAN.md` for the approved exact grants.

Plain `gcloud` retains the operator's personal configuration, whose default
project may differ from the beta project. Always specify the intended project
for cloud operations. The beta automation identity has no legacy project grant.

See `deploy/gcp-v1/CLI_AUTOMATION.md` for usage, verification, local credential
location, and disabling access. Keep private keys and token values out of
repository files and command output.
