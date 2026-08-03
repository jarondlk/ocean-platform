#!/bin/sh
# Create non-runtime GCP foundations after billing is linked.
set -eu

GCP_PROJECT_ID="${GCP_PROJECT_ID:-data-infra-infobio}"
GCP_REGION="${GCP_REGION:-asia-northeast1}"
ARTIFACT_REPOSITORY="${ARTIFACT_REPOSITORY:-onagawa-source-chat}"
: "${DATA_BUCKET:?Set DATA_BUCKET to a globally unique Cloud Storage bucket name}"

if [ "${CONFIRM_GCP_PROJECT:-}" != "$GCP_PROJECT_ID" ]; then
  echo "Set CONFIRM_GCP_PROJECT=$GCP_PROJECT_ID to allow foundation changes." >&2
  exit 2
fi

gcloud projects describe "$GCP_PROJECT_ID" >/dev/null
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="$GCP_PROJECT_ID"

if ! gcloud artifacts repositories describe "$ARTIFACT_REPOSITORY" \
  --location="$GCP_REGION" \
  --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$ARTIFACT_REPOSITORY" \
    --location="$GCP_REGION" \
    --repository-format=docker \
    --description="Onagawa Source Chat containers" \
    --labels=environment=prototype,cost_component=artifact_registry \
    --project="$GCP_PROJECT_ID"
fi

for account in onagawa-app onagawa-jobs; do
  email="$account@$GCP_PROJECT_ID.iam.gserviceaccount.com"
  if ! gcloud iam service-accounts describe "$email" \
    --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$account" \
      --display-name="$account" \
      --project="$GCP_PROJECT_ID"
  fi
done

for secret in \
  onagawa-auth-secret \
  onagawa-internal-auth-secret \
  onagawa-oidc-client-secret \
  onagawa-database-url; do
  if ! gcloud secrets describe "$secret" \
    --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$secret" \
      --replication-policy=automatic \
      --labels=environment=prototype,cost_component=secrets \
      --project="$GCP_PROJECT_ID"
  fi
done

if ! gcloud storage buckets describe "gs://$DATA_BUCKET" \
  --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$DATA_BUCKET" \
    --project="$GCP_PROJECT_ID" \
    --location="$GCP_REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention
fi
gcloud storage buckets update "gs://$DATA_BUCKET" \
  --versioning \
  --update-labels=environment=prototype,cost_component=storage

app_member="serviceAccount:onagawa-app@$GCP_PROJECT_ID.iam.gserviceaccount.com"
jobs_member="serviceAccount:onagawa-jobs@$GCP_PROJECT_ID.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member="$app_member" \
  --role=roles/cloudsql.client \
  --condition=None >/dev/null
gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member="$jobs_member" \
  --role=roles/cloudsql.client \
  --condition=None >/dev/null

for secret in \
  onagawa-auth-secret \
  onagawa-internal-auth-secret \
  onagawa-oidc-client-secret \
  onagawa-database-url; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --project="$GCP_PROJECT_ID" \
    --member="$app_member" \
    --role=roles/secretmanager.secretAccessor >/dev/null
done
gcloud secrets add-iam-policy-binding onagawa-database-url \
  --project="$GCP_PROJECT_ID" \
  --member="$jobs_member" \
  --role=roles/secretmanager.secretAccessor >/dev/null

gcloud storage buckets add-iam-policy-binding "gs://$DATA_BUCKET" \
  --member="$app_member" \
  --role=roles/storage.objectViewer >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$DATA_BUCKET" \
  --member="$jobs_member" \
  --role=roles/storage.objectUser >/dev/null

echo "Foundation prepared. No secret versions, database, jobs, or services were created."
