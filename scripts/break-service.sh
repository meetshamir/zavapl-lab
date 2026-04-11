#!/bin/bash
set -euo pipefail

WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"
APP="ca-${WORKLOAD}-outage"

echo -e "\n\033[1;31m╔══════════════════════════════════════════════╗\033[0m"
echo -e "\033[1;31m║   BREAK SCENARIO: Service Outage (503)       ║\033[0m"
echo -e "\033[1;31m╚══════════════════════════════════════════════╝\033[0m\n"

echo -e "\033[1;33m→ Setting FORCE_ERROR=true on ${APP}\033[0m"
echo -e "  Resource Group: ${RG}"
echo -e "  Effect: outage-api will return HTTP 503 for all requests\n"

az containerapp update \
  --name "$APP" \
  --resource-group "$RG" \
  --set-env-vars "FORCE_ERROR=true"

echo -e "\n\033[1;32m✔ Done — service is now broken. Open SRE Agent to watch it investigate.\033[0m\n"
