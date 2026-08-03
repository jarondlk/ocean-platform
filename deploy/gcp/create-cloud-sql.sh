#!/bin/sh
# Create the billable prototype database only after explicit confirmation.
set -eu

GCP_PROJECT_ID="${GCP_PROJECT_ID:-data-infra-infobio}"
GCP_REGION="${GCP_REGION:-asia-northeast1}"
CLOUD_SQL_INSTANCE="${CLOUD_SQL_INSTANCE:-onagawa-postgres}"
CLOUD_SQL_TIER="${CLOUD_SQL_TIER:-db-f1-micro}"

if [ "${CONFIRM_BILLABLE_GCP_PROJECT:-}" != "$GCP_PROJECT_ID" ]; then
  echo "Set CONFIRM_BILLABLE_GCP_PROJECT=$GCP_PROJECT_ID to create Cloud SQL." >&2
  exit 2
fi

gcloud projects describe "$GCP_PROJECT_ID" >/dev/null
if ! gcloud sql instances describe "$CLOUD_SQL_INSTANCE" \
  --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
  # Cloud SQL instance labels are currently exposed by the gcloud beta create
  # surface. Keeping them on the create call avoids any unlabelled billing gap.
  gcloud beta sql instances create "$CLOUD_SQL_INSTANCE" \
    --project="$GCP_PROJECT_ID" \
    --region="$GCP_REGION" \
    --database-version=POSTGRES_16 \
    --tier="$CLOUD_SQL_TIER" \
    --storage-type=SSD \
    --storage-size=10 \
    --storage-auto-increase \
    --storage-auto-increase-limit=20 \
    --availability-type=zonal \
    --backup-start-time=18:00 \
    --enable-point-in-time-recovery \
    --labels=environment=prototype,cost_component=database \
    --deletion-protection
fi

if ! gcloud sql databases describe onagawa_rag \
  --instance="$CLOUD_SQL_INSTANCE" \
  --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
  gcloud sql databases create onagawa_rag \
    --instance="$CLOUD_SQL_INSTANCE" \
    --project="$GCP_PROJECT_ID"
fi

echo "Cloud SQL is ready for an application user and database secret."
echo "Create the password out of band; do not place it in this repository or shell history."
