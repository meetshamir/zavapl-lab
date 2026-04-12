#!/bin/bash
# Fix the App Service port misconfiguration
set -e
WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"

echo "Restoring WEBSITES_PORT=8080..."
az webapp config appsettings set \
  --name "app-${WORKLOAD}-portal" \
  --resource-group "$RG" \
  --settings WEBSITES_PORT=8080 \
  --output none 2>/dev/null

az webapp restart \
  --name "app-${WORKLOAD}-portal" \
  --resource-group "$RG" \
  --output none 2>/dev/null

echo "✅ App Service portal restored."
