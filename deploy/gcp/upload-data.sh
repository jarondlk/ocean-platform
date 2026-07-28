#!/bin/sh
# Seed the prototype bucket after reviewing the local source directories.
set -eu

GCP_PROJECT_ID="${GCP_PROJECT_ID:-data-infra-infobio}"
: "${DATA_BUCKET:?Set DATA_BUCKET to the prepared bucket name}"

if [ "${CONFIRM_DATA_BUCKET:-}" != "$DATA_BUCKET" ]; then
  echo "Set CONFIRM_DATA_BUCKET=$DATA_BUCKET to allow data uploads." >&2
  exit 2
fi

gcloud storage buckets describe "gs://$DATA_BUCKET" \
  --project="$GCP_PROJECT_ID" >/dev/null

gcloud storage rsync data "gs://$DATA_BUCKET" \
  --recursive \
  --project="$GCP_PROJECT_ID"

if [ -d onagawa_sst_subset ]; then
  gcloud storage rsync onagawa_sst_subset \
    "gs://$DATA_BUCKET/raw/sst-netcdf" \
    --recursive \
    --project="$GCP_PROJECT_ID"
fi

if [ -d himawari_raw ]; then
  gcloud storage rsync himawari_raw \
    "gs://$DATA_BUCKET/raw/himawari" \
    --recursive \
    --project="$GCP_PROJECT_ID"
fi

echo "Data upload complete. Local source files were not modified."
