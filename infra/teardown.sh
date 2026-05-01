#!/usr/bin/env bash
# Deletes the entire resource group — removes ALL resources created by deploy.sh
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-edudoc-ai-rg}"

echo "⚠  This will permanently delete resource group: $RESOURCE_GROUP"
read -r -p "Type the resource group name to confirm: " CONFIRM

if [ "$CONFIRM" != "$RESOURCE_GROUP" ]; then
  echo "Aborted."
  exit 1
fi

az group delete --name "$RESOURCE_GROUP" --yes --no-wait
echo "✅ Teardown initiated. Resources will be deleted within a few minutes."
