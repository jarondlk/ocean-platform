#!/bin/sh
# Use this Mac's dedicated beta automation credentials, independent of user login.
set -eu

project_id=ocean-v1-beta-20261101
account=ocean-v1-beta-cli@ocean-v1-beta-20261101.iam.gserviceaccount.com
config_dir="${HOME:?HOME must point to your user directory}/.config/gcloud-ocean-v1-beta"

if [ ! -f "$config_dir/configurations/config_default" ]; then
  echo "Beta automation is not configured on this Mac. See deploy/gcp-v1/CLI_AUTOMATION.md." >&2
  exit 1
fi

# An inherited token, impersonation setting, or credential file must not select
# a different identity instead of the dedicated service account.
unset CLOUDSDK_AUTH_ACCESS_TOKEN CLOUDSDK_AUTH_ACCESS_TOKEN_FILE \
  CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT \
  CLOUDSDK_AUTH_DISABLE_CREDENTIALS GOOGLE_APPLICATION_CREDENTIALS \
  CLOUDSDK_CORE_ACCOUNT CLOUDSDK_CORE_PROJECT
export CLOUDSDK_CONFIG="$config_dir"
export CLOUDSDK_ACTIVE_CONFIG_NAME=default
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

gcloud_bin="$(command -v gcloud || true)"
if [ -z "$gcloud_bin" ] && [ -x /opt/homebrew/bin/gcloud ]; then
  gcloud_bin=/opt/homebrew/bin/gcloud
fi
if [ -z "$gcloud_bin" ]; then
  echo "Google Cloud CLI is not installed or available on PATH." >&2
  exit 1
fi

exec "$gcloud_bin" --account="$account" --project="$project_id" "$@"
