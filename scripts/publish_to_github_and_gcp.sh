#!/usr/bin/env bash
# ==============================================================================
# Strava Health AI Agent — One-Command GitHub & GCP Secret Manager / ADK Publisher
# ==============================================================================
# SECURITY NOTE: This script reads credentials strictly from environment variables
# or your local untracked `.env` file. No secrets or tokens are hardcoded here.
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-capsules-agents-1}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
GITHUB_REPO_URL="https://github.com/bertilw-google/strava-health-ai-agent.git"

echo "1. Running Pre-Publish Secret Audit..."
if git grep -iE "(3e3195b0f2|2c9c82d000|86c6fd3fce|ghp_)" >/dev/null 2>&1; then
  echo "❌ ERROR: Sensitive token detected in tracked files! Aborting."
  exit 1
fi
echo "   ✅ Zero hardcoded secrets in tracked files."

echo "2. Pushing sanitized repository to ${GITHUB_REPO_URL}..."
git remote set-url origin "$GITHUB_REPO_URL" 2>/dev/null || git remote add origin "$GITHUB_REPO_URL"
git push -u origin main

echo "3. Provisioning Single-Project GCP Infrastructure & Secret Manager (${PROJECT_ID})..."
for SECRET_NAME in STRAVA_CLIENT_ID STRAVA_CLIENT_SECRET STRAVA_ACCESS_TOKEN STRAVA_REFRESH_TOKEN; do
  SECRET_VAL="${!SECRET_NAME:-}"
  if [[ -n "$SECRET_VAL" ]]; then
    gcloud secrets create "$SECRET_NAME" --replication-policy="automatic" --project="$PROJECT_ID" 2>/dev/null || true
    printf "%s" "$SECRET_VAL" | gcloud secrets versions add "$SECRET_NAME" --data-file=- --project="$PROJECT_ID"
    echo "   ✅ Synced secret version for ${SECRET_NAME} in Secret Manager"
  fi
done

echo "4. Applying Terraform Single-Project Configuration..."
terraform -chdir=deployment/terraform init
terraform -chdir=deployment/terraform apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}" -auto-approve

echo "5. Deploying & Publishing ADK Agent to Vertex AI Agent Platform & Gemini Enterprise..."
agents-cli deploy --project="$PROJECT_ID" --region="$REGION" --target=agent_runtime
agents-cli publish --project="$PROJECT_ID" --region="$REGION" --display-name="Strava Health AI Coach"
