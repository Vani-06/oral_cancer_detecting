#!/usr/bin/env bash
# Deploys OralSentinel to Google Cloud, Mumbai (asia-south1).
#
#   gcloud auth login                      # once, in your own terminal
#   bash deploy/gcp/deploy.sh <project-id>
#
# Creates (first run) or updates (later runs): Artifact Registry repository,
# Cloud SQL Postgres instance + database + user, private Cloud Storage bucket
# for photos and reports, Secret Manager secrets, a service account, and two
# Cloud Run services (oralsentinel-api, oralsentinel-web). Safe to re-run.
set -euo pipefail

PROJECT_ID="${1:?usage: deploy.sh <project-id>}"
REGION="asia-south1"
REPO="oralsentinel"
SQL_INSTANCE="oralsentinel-db"
DB_NAME="oralsentinel"
DB_USER="oralsentinel"
BUCKET="${PROJECT_ID}-oralsentinel-data"
SA_NAME="oralsentinel-api"
TAG="$(git rev-parse --short HEAD)"

gcloud config set project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"
# Cloud Run URLs are deterministic: https://SERVICE-PROJECTNUMBER.REGION.run.app
API_URL="https://oralsentinel-api-${PROJECT_NUMBER}.${REGION}.run.app"
WEB_URL="https://oralsentinel-web-${PROJECT_NUMBER}.${REGION}.run.app"

echo "== Enabling services"
gcloud services enable run.googleapis.com sqladmin.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com cloudbuild.googleapis.com storage.googleapis.com

echo "== Artifact Registry"
gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION"

echo "== Storage bucket (private, India)"
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 ||
  gcloud storage buckets create "gs://$BUCKET" --location "$REGION" --uniform-bucket-level-access \
    --public-access-prevention

echo "== Cloud SQL (Postgres 16) -- first creation takes several minutes"
gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1 ||
  gcloud sql instances create "$SQL_INSTANCE" --database-version POSTGRES_16 --region "$REGION" \
    --edition enterprise --tier db-g1-small --storage-auto-increase --backup-start-time 20:30
gcloud sql databases describe "$DB_NAME" --instance "$SQL_INSTANCE" >/dev/null 2>&1 ||
  gcloud sql databases create "$DB_NAME" --instance "$SQL_INSTANCE"

echo "== Secrets"
if ! gcloud secrets describe oralsentinel-database-url >/dev/null 2>&1; then
  DB_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  gcloud sql users create "$DB_USER" --instance "$SQL_INSTANCE" --password "$DB_PASSWORD"
  printf 'postgresql+psycopg://%s:%s@/%s?host=/cloudsql/%s:%s:%s' \
    "$DB_USER" "$DB_PASSWORD" "$DB_NAME" "$PROJECT_ID" "$REGION" "$SQL_INSTANCE" |
    gcloud secrets create oralsentinel-database-url --data-file=-
  unset DB_PASSWORD
fi
gcloud secrets describe oralsentinel-secret-key >/dev/null 2>&1 ||
  python -c 'import secrets; print(secrets.token_urlsafe(48), end="")' |
    gcloud secrets create oralsentinel-secret-key --data-file=-

echo "== Service account"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 ||
  gcloud iam service-accounts create "$SA_NAME" --display-name "OralSentinel API"
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$SA" \
  --role roles/cloudsql.client --condition None >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$SA" \
  --role roles/storage.objectAdmin >/dev/null
for s in oralsentinel-database-url oralsentinel-secret-key; do
  gcloud secrets add-iam-policy-binding "$s" --member "serviceAccount:$SA" \
    --role roles/secretmanager.secretAccessor >/dev/null
done

echo "== Building images in Cloud Build (about 10-15 minutes)"
gcloud builds submit --region "$REGION" --config deploy/gcp/cloudbuild.yaml \
  --substitutions "_REGISTRY=${REGISTRY},_TAG=${TAG},_API_URL=${API_URL}" .

echo "== Deploying the API"
gcloud run deploy oralsentinel-api --image "${REGISTRY}/api:${TAG}" --region "$REGION" \
  --service-account "$SA" --allow-unauthenticated --execution-environment gen2 \
  --cpu 2 --memory 2Gi --min-instances 1 --max-instances 2 --concurrency 4 --timeout 300 \
  --add-cloudsql-instances "${PROJECT_ID}:${REGION}:${SQL_INSTANCE}" \
  --add-volume "name=data,type=cloud-storage,bucket=${BUCKET}" \
  --add-volume-mount "volume=data,mount-path=/data" \
  --set-secrets "DATABASE_URL=oralsentinel-database-url:latest,SECRET_KEY=oralsentinel-secret-key:latest" \
  --set-env-vars "^@^ALLOW_REGISTRATION=true@CORS_ORIGINS=[\"${WEB_URL}\"]"

echo "== Deploying the website"
gcloud run deploy oralsentinel-web --image "${REGISTRY}/web:${TAG}" --region "$REGION" \
  --allow-unauthenticated --cpu 1 --memory 256Mi --min-instances 0 --max-instances 3

echo
echo "Done."
echo "  Website: ${WEB_URL}"
echo "  API:     ${API_URL}/health"
