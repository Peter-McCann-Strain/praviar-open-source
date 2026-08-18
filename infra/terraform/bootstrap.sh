#!/usr/bin/env bash
# Prepare one existing GCP project for Terraform remote state.
# Dry-run is the default. This helper never creates credentials or changes IAM.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  PRAVIAR_GCP_PROJECT_ID=my-project \
  PRAVIAR_TF_STATE_BUCKET=my-globally-unique-state-bucket \
  bash ./infra/terraform/bootstrap.sh

The default is a dry run. Set PRAVIAR_BOOTSTRAP_APPLY=YES only after reviewing
the printed project, bucket, region, authenticated account, and commands.

Optional:
  PRAVIAR_GCP_REGION       bucket location (default: europe-west2)
  PRAVIAR_BOOTSTRAP_APPLY  must be exactly YES to make changes

The project must already exist, have billing enabled, and be selected by an
operator with narrowly scoped permissions. Authenticate local Terraform with
Application Default Credentials before running terraform init or plan.
EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi
if [ "$#" -ne 0 ]; then
  usage >&2
  exit 2
fi

: "${PRAVIAR_GCP_PROJECT_ID:?Set PRAVIAR_GCP_PROJECT_ID to an existing GCP project ID}"
: "${PRAVIAR_TF_STATE_BUCKET:?Set PRAVIAR_TF_STATE_BUCKET without a gs:// prefix}"

PRAVIAR_GCP_REGION="${PRAVIAR_GCP_REGION:-europe-west2}"
PRAVIAR_BOOTSTRAP_APPLY="${PRAVIAR_BOOTSTRAP_APPLY:-NO}"

if [[ ! "$PRAVIAR_GCP_PROJECT_ID" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
  echo "PRAVIAR_GCP_PROJECT_ID is not a valid GCP project ID." >&2
  exit 2
fi
if [[ ! "$PRAVIAR_TF_STATE_BUCKET" =~ ^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$ ]]; then
  echo "PRAVIAR_TF_STATE_BUCKET is not a valid bucket name." >&2
  exit 2
fi
if [[ ! "$PRAVIAR_GCP_REGION" =~ ^[a-z]+-[a-z]+[0-9]$ ]]; then
  echo "PRAVIAR_GCP_REGION is not a valid region." >&2
  exit 2
fi
if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud is required; install the Google Cloud CLI first." >&2
  exit 2
fi

active_account="$(gcloud auth list --filter=status:ACTIVE --limit=1 --format='value(account)')"
if [ -z "$active_account" ]; then
  echo "No active gcloud account. Authenticate and retry." >&2
  exit 2
fi

echo "Project:               $PRAVIAR_GCP_PROJECT_ID"
echo "State bucket:          gs://$PRAVIAR_TF_STATE_BUCKET"
echo "Region:                $PRAVIAR_GCP_REGION"
echo "Authenticated account: $active_account"
echo "Apply mode:            $PRAVIAR_BOOTSTRAP_APPLY"

commands=(
  "gcloud services enable storage.googleapis.com --project=$PRAVIAR_GCP_PROJECT_ID"
  "gcloud storage buckets create gs://$PRAVIAR_TF_STATE_BUCKET --project=$PRAVIAR_GCP_PROJECT_ID --location=$PRAVIAR_GCP_REGION --uniform-bucket-level-access --public-access-prevention"
  "gcloud storage buckets update gs://$PRAVIAR_TF_STATE_BUCKET --versioning --uniform-bucket-level-access --public-access-prevention"
)

if [ "$PRAVIAR_BOOTSTRAP_APPLY" != "YES" ]; then
  echo
  echo "Dry run; no changes made. Planned commands:"
  printf '  %s\n' "${commands[@]}"
  exit 0
fi

project_number="$(
  gcloud projects describe "$PRAVIAR_GCP_PROJECT_ID" --format='value(projectNumber)'
)"
if [ -z "$project_number" ]; then
  echo "Could not resolve the selected project's numeric identity; refusing to continue." >&2
  exit 1
fi
gcloud services enable storage.googleapis.com --project="$PRAVIAR_GCP_PROJECT_ID"
if gcloud storage buckets describe "gs://$PRAVIAR_TF_STATE_BUCKET" >/dev/null 2>&1; then
  bucket_project_number="$(
    gcloud storage buckets describe "gs://$PRAVIAR_TF_STATE_BUCKET" \
      --format='value(projectNumber)'
  )"
  if [ -z "$bucket_project_number" ]; then
    echo "Could not resolve the existing bucket's project identity; refusing to modify it." >&2
    exit 1
  fi
  if [ "$bucket_project_number" != "$project_number" ]; then
    echo "Existing state bucket belongs to a different project; refusing to modify it." >&2
    exit 1
  fi
  echo "State bucket already exists; leaving its location and ownership unchanged."
else
  gcloud storage buckets create "gs://$PRAVIAR_TF_STATE_BUCKET" \
    --project="$PRAVIAR_GCP_PROJECT_ID" \
    --location="$PRAVIAR_GCP_REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention
fi
gcloud storage buckets update "gs://$PRAVIAR_TF_STATE_BUCKET" \
  --versioning \
  --uniform-bucket-level-access \
  --public-access-prevention

echo "Bootstrap complete. Review retention and recovery policy before storing state."
echo "Initialize with: terraform init -backend-config=bucket=$PRAVIAR_TF_STATE_BUCKET"
