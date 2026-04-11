#!/bin/bash
set -euo pipefail

WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"
APP="ca-${WORKLOAD}-meter"

echo -e "\n\033[1;31m╔══════════════════════════════════════════════╗\033[0m"
echo -e "\033[1;31m║   BREAK SCENARIO: Memory Leak (OOM)          ║\033[0m"
echo -e "\033[1;31m╚══════════════════════════════════════════════╝\033[0m\n"

echo -e "\033[1;33m→ Setting SIMULATE_OOM=true on ${APP}\033[0m"
echo -e "  Resource Group: ${RG}"
echo -e "  Effect: meter-api will leak memory until OOM-killed\n"

az containerapp update \
  --name "$APP" \
  --resource-group "$RG" \
  --set-env-vars "SIMULATE_OOM=true"

echo -e "\n\033[1;32m✔ Done — service is now broken. Open SRE Agent to watch it investigate.\033[0m\n"
