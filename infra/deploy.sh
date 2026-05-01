#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# EduDoc AI Document Classifier — Azure Container Apps deployment
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
RESOURCE_GROUP="${RESOURCE_GROUP:-edudoc-ai-rg}"
LOCATION="${LOCATION:-eastus}"
ACR_NAME="${ACR_NAME:-edudocaiacr18970}"   # pinned — reuse existing registry
EXISTING_ENV_RG="edudoc-rg"               # resource group of pre-existing environment
EXISTING_ENV_NAME="edudoc-env"            # reuse free-tier environment (1 per region limit)
CONTAINER_APP_ENV="${CONTAINER_APP_ENV:-edudoc-env}"
CONTAINER_APP_NAME="${CONTAINER_APP_NAME:-edudoc-ai-classifier}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
LOG_WORKSPACE="${LOG_WORKSPACE:-edudoc-ai-logs}"

# Load secrets from .env if present
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

GOOGLE_API_KEY="${GOOGLE_API_KEY:?GOOGLE_API_KEY must be set in .env or environment}"
LANGCHAIN_API_KEY="${LANGCHAIN_API_KEY:-}"
LANGCHAIN_PROJECT="${LANGCHAIN_PROJECT:-edudoc-ai-classification}"

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
docker build --platform linux/amd64 -t "$IMAGE_NAME" .
docker push "$IMAGE_NAME"

# ── 4 & 5. Container Apps Environment (reuse existing — free tier: 1 per region) ──
# Azure free subscriptions allow only 1 Container App Environment per region.
# We reuse the pre-existing 'edudoc-env' environment instead of creating a new one.
echo "▶ Reusing existing Container Apps environment: $EXISTING_ENV_NAME (in $EXISTING_ENV_RG)"
CONTAINER_APP_ENV_RESOURCE_GROUP="$EXISTING_ENV_RG"
CONTAINER_APP_ENV="$EXISTING_ENV_NAME"

# ── 6. Build env-vars and secrets lists (use arrays for safe quoting) ───────
SECRETS_ARGS=("google-api-key=$GOOGLE_API_KEY")
ENV_VARS_ARGS=("GOOGLE_API_KEY=secretref:google-api-key" "PYTHONUNBUFFERED=1")

if [ -n "$LANGCHAIN_API_KEY" ]; then
  SECRETS_ARGS+=("langchain-api-key=$LANGCHAIN_API_KEY")
  ENV_VARS_ARGS+=("LANGCHAIN_TRACING_V2=true")
  ENV_VARS_ARGS+=("LANGCHAIN_API_KEY=secretref:langchain-api-key")
  ENV_VARS_ARGS+=("LANGCHAIN_PROJECT=$LANGCHAIN_PROJECT")
fi

# ── 7. Container App ──────────────────────────────────────────────────────────
echo "▶ Creating Container App: $CONTAINER_APP_NAME"

ACR_PASSWORD=$(az acr credential show \
  --name "$ACR_NAME" \
  --query "passwords[0].value" -o tsv)

az containerapp create \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$CONTAINER_APP_ENV_RESOURCE_GROUP/providers/Microsoft.App/managedEnvironments/$CONTAINER_APP_ENV" \
  --image "$IMAGE_NAME" \
  --registry-server "$ACR_LOGIN_SERVER" \
  --registry-username "$ACR_NAME" \
  --registry-password "$ACR_PASSWORD" \
  --cpu 2.0 \
  --memory 4.0Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --ingress external \
  --target-port 8000 \
  --secrets "${SECRETS_ARGS[@]}" \
  --env-vars "${ENV_VARS_ARGS[@]}" \
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
