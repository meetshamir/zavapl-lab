#!/bin/bash
set -euo pipefail

WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"
APP="ca-${WORKLOAD}-portal"

echo -e "\n\033[1;31m╔══════════════════════════════════════════════╗\033[0m"
echo -e "\033[1;31m║   BREAK SCENARIO: Bad Image (ImagePullBackOff)║\033[0m"
echo -e "\033[1;31m╚══════════════════════════════════════════════╝\033[0m\n"

echo -e "\033[1;33m→ Updating container image to nonexistent:latest on ${APP}\033[0m"
echo -e "  Resource Group: ${RG}"
echo -e "  Effect: portal will fail with ImagePullBackOff\n"

az containerapp update \
  --name "$APP" \
  --resource-group "$RG" \
  --image "nonexistent:latest"

echo -e "\n\033[1;32m✔ Done — service is now broken. Open SRE Agent to watch it investigate.\033[0m\n"
