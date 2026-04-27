#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# MediShield Document Classifier — Azure Container Apps deployment
#
# Prerequisites:
#   - Azure CLI installed and logged in  (az login)
#   - Docker running locally
#   - .env file with GOOGLE_API_KEY (and optionally LANGCHAIN_* vars)
#
# Usage:
#   chmod +x infra/deploy.sh
#   ./infra/deploy.sh
#
# All resources are created in the same resource group for easy teardown.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config (override via env vars before running) ────────────────────────────
RESOURCE_GROUP="${RESOURCE_GROUP:-medishield-rg}"
LOCATION="${LOCATION:-eastus}"
ACR_NAME="${ACR_NAME:-medishieldacr$RANDOM}"   # must be globally unique
CONTAINER_APP_ENV="${CONTAINER_APP_ENV:-medishield-env}"
CONTAINER_APP_NAME="${CONTAINER_APP_NAME:-medishield-classifier}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
LOG_WORKSPACE="${LOG_WORKSPACE:-medishield-logs}"

# Load secrets from .env if present
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

GOOGLE_API_KEY="${GOOGLE_API_KEY:?GOOGLE_API_KEY must be set in .env or environment}"
LANGCHAIN_API_KEY="${LANGCHAIN_API_KEY:-}"
LANGCHAIN_PROJECT="${LANGCHAIN_PROJECT:-medishield-classification}"

# ── 1. Resource Group ─────────────────────────────────────────────────────────
echo "▶ Creating resource group: $RESOURCE_GROUP ($LOCATION)"
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

# ── 2. Azure Container Registry ───────────────────────────────────────────────
echo "▶ Creating Container Registry: $ACR_NAME"
az acr create \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --sku Basic \
  --admin-enabled true \
  --output none

ACR_LOGIN_SERVER=$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query loginServer -o tsv)

echo "  Registry: $ACR_LOGIN_SERVER"

# ── 3. Build & push image to ACR ─────────────────────────────────────────────
IMAGE_NAME="$ACR_LOGIN_SERVER/classifier:$IMAGE_TAG"

echo "▶ Building and pushing image: $IMAGE_NAME"
az acr login --name "$ACR_NAME"
docker build -t "$IMAGE_NAME" .
docker push "$IMAGE_NAME"

# ── 4. Log Analytics Workspace (for container logs) ──────────────────────────
echo "▶ Creating Log Analytics workspace: $LOG_WORKSPACE"
az monitor log-analytics workspace create \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$LOG_WORKSPACE" \
  --location "$LOCATION" \
  --output none

LOG_WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$LOG_WORKSPACE" \
  --query customerId -o tsv)

LOG_WORKSPACE_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$LOG_WORKSPACE" \
  --query primarySharedKey -o tsv)

# ── 5. Container Apps Environment ────────────────────────────────────────────
echo "▶ Creating Container Apps environment: $CONTAINER_APP_ENV"
az containerapp env create \
  --name "$CONTAINER_APP_ENV" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --logs-workspace-id "$LOG_WORKSPACE_ID" \
  --logs-workspace-key "$LOG_WORKSPACE_KEY" \
  --output none

# ── 6. Build env-vars and secrets lists ──────────────────────────────────────
SECRETS="google-api-key=$GOOGLE_API_KEY"
ENV_VARS="GOOGLE_API_KEY=secretref:google-api-key PYTHONUNBUFFERED=1"

if [ -n "$LANGCHAIN_API_KEY" ]; then
  SECRETS="$SECRETS,langchain-api-key=$LANGCHAIN_API_KEY"
  ENV_VARS="$ENV_VARS LANGCHAIN_TRACING_V2=true"
  ENV_VARS="$ENV_VARS LANGCHAIN_API_KEY=secretref:langchain-api-key"
  ENV_VARS="$ENV_VARS LANGCHAIN_PROJECT=$LANGCHAIN_PROJECT"
fi

# ── 7. Container App ──────────────────────────────────────────────────────────
echo "▶ Creating Container App: $CONTAINER_APP_NAME"

ACR_PASSWORD=$(az acr credential show \
  --name "$ACR_NAME" \
  --query "passwords[0].value" -o tsv)

az containerapp create \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$CONTAINER_APP_ENV" \
  --image "$IMAGE_NAME" \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_NAME" \
  --registry-password "$ACR_PASSWORD" \
  --cpu 0.5 \
  --memory 2.0Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --ingress external \
  --target-port 8000 \
  --secrets "$SECRETS" \
  --env-vars $ENV_VARS \
  --output none

# ── 8. Get public URL ─────────────────────────────────────────────────────────
APP_URL=$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" -o tsv)

echo ""
echo "✅ Deployment complete!"
echo "   App URL : https://$APP_URL"
echo "   Health  : https://$APP_URL/health"
echo "   API docs: https://$APP_URL/docs"
echo "   Metrics : https://$APP_URL/metrics"
echo ""
echo "   To stream logs:"
echo "   az containerapp logs show -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP --follow"
echo ""
echo "   To update after code changes:"
echo "   ./infra/deploy.sh   (re-runs idempotently)"
