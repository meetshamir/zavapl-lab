#!/bin/bash
set -euo pipefail

WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"
APP="ca-${WORKLOAD}-notify"

echo -e "\n\033[1;31m╔══════════════════════════════════════════════╗\033[0m"
echo -e "\033[1;31m║   BREAK SCENARIO: Crash Loop (Missing Config)║\033[0m"
echo -e "\033[1;31m╚══════════════════════════════════════════════╝\033[0m\n"

echo -e "\033[1;33m→ Removing REQUIRED_CONFIG from ${APP}\033[0m"
echo -e "  Resource Group: ${RG}"
echo -e "  Effect: notification-svc will crash on startup due to missing config\n"

az containerapp update \
  --name "$APP" \
  --resource-group "$RG" \
  --remove-env-vars "REQUIRED_CONFIG"

echo -e "\n\033[1;32m✔ Done — service is now broken. Open SRE Agent to watch it investigate.\033[0m\n"
