#!/bin/sh
# Upload only the bounded Phase 5 raw seed. Dry-run is the default.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
GCP_PROJECT_ID="${GCP_PROJECT_ID:-data-infra-infobio}"
UPLOAD_MODE="${UPLOAD_MODE:-dry-run}"
SEED_TAG="${SEED_TAG:-phase5-raw-v1}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RAW_DIR="$PROJECT_ROOT/data/raw"
SST_DIR="$PROJECT_ROOT/onagawa_sst_subset"
: "${DATA_BUCKET:?Set DATA_BUCKET to the prepared bucket name}"

case "$UPLOAD_MODE" in
  dry-run|apply) ;;
  *)
    echo "UPLOAD_MODE must be dry-run or apply." >&2
    exit 2
    ;;
esac

case "$SEED_TAG" in
  ""|*[!A-Za-z0-9._-]*)
    echo "SEED_TAG may contain only letters, digits, dot, underscore, and hyphen." >&2
    exit 2
    ;;
esac

if [ "$UPLOAD_MODE" = "apply" ] && [ "${CONFIRM_DATA_BUCKET:-}" != "$DATA_BUCKET" ]; then
  echo "Set CONFIRM_DATA_BUCKET=$DATA_BUCKET to allow data uploads." >&2
  exit 2
fi

TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/onagawa-phase5-seed.XXXXXX")
trap 'rm -rf "$TEMP_DIR"' EXIT HUP INT TERM
MANIFEST_PATH="$TEMP_DIR/$SEED_TAG.json"

"$PYTHON_BIN" "$PROJECT_ROOT/scripts/build_gcp_seed_manifest.py" \
  --raw-dir="$RAW_DIR" \
  --sst-dir="$SST_DIR" \
  --output="$MANIFEST_PATH"

gcloud storage buckets describe "gs://$DATA_BUCKET" \
  --project="$GCP_PROJECT_ID" >/dev/null

if [ "$UPLOAD_MODE" = "dry-run" ]; then
  gcloud storage rsync "$RAW_DIR" "gs://$DATA_BUCKET/raw" \
    --recursive \
    --dry-run \
    --checksums-only \
    --exclude='.*\.DS_Store$' \
    --project="$GCP_PROJECT_ID"
  gcloud storage rsync "$SST_DIR" "gs://$DATA_BUCKET/raw/sst-netcdf" \
    --recursive \
    --dry-run \
    --checksums-only \
    --exclude='.*\.DS_Store$' \
    --project="$GCP_PROJECT_ID"
  echo "Dry-run complete. No objects were uploaded."
  exit 0
fi

gcloud storage rsync "$RAW_DIR" "gs://$DATA_BUCKET/raw" \
  --recursive \
  --checksums-only \
  --exclude='.*\.DS_Store$' \
  --project="$GCP_PROJECT_ID"
gcloud storage rsync "$SST_DIR" "gs://$DATA_BUCKET/raw/sst-netcdf" \
  --recursive \
  --checksums-only \
  --exclude='.*\.DS_Store$' \
  --project="$GCP_PROJECT_ID"
EXPECTED_OBJECTS=$("$PYTHON_BIN" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["total_objects"])' \
  "$MANIFEST_PATH")
EXPECTED_BYTES=$("$PYTHON_BIN" -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["total_bytes"])' \
  "$MANIFEST_PATH")
REMOTE_OBJECTS=$(gcloud storage ls "gs://$DATA_BUCKET/raw/**" \
  --project="$GCP_PROJECT_ID" | wc -l | tr -d ' ')
REMOTE_BYTES=$(gcloud storage du --summarize "gs://$DATA_BUCKET/raw" \
  --project="$GCP_PROJECT_ID" | awk 'NR == 1 {print $1}')

if [ "$REMOTE_OBJECTS" != "$EXPECTED_OBJECTS" ]; then
  echo "Remote raw object count mismatch: expected $EXPECTED_OBJECTS, observed $REMOTE_OBJECTS." >&2
  exit 1
fi
if [ "$REMOTE_BYTES" != "$EXPECTED_BYTES" ]; then
  echo "Remote raw byte count mismatch: expected $EXPECTED_BYTES, observed $REMOTE_BYTES." >&2
  exit 1
fi

gcloud storage cp "$MANIFEST_PATH" \
  "gs://$DATA_BUCKET/manifests/$SEED_TAG.json" \
  --project="$GCP_PROJECT_ID"

echo "Verified $REMOTE_OBJECTS raw objects and $REMOTE_BYTES bytes."
echo "Raw-only seed upload complete. No local files or remote objects were deleted."
