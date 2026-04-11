#!/bin/bash
set -euo pipefail

WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"

echo -e "\n\033[1;32m╔══════════════════════════════════════════════╗\033[0m"
echo -e "\033[1;32m║   FIX-ALL: Restoring Healthy State           ║\033[0m"
echo -e "\033[1;32m╚══════════════════════════════════════════════╝\033[0m\n"

SERVICES=("outage" "meter" "grid" "notify" "portal")
FAILURE_VARS=("FORCE_ERROR" "SIMULATE_OOM" "SIMULATE_DELAY_MS")

for svc in "${SERVICES[@]}"; do
  APP="ca-${WORKLOAD}-${svc}"
  echo -e "\033[1;36m→ Fixing ${APP}...\033[0m"

  # Remove all failure-triggering env vars
  az containerapp update \
    --name "$APP" \
    --resource-group "$RG" \
    --remove-env-vars "${FAILURE_VARS[@]}" \
    --output none 2>/dev/null || true

  echo -e "  \033[1;32m✔ ${APP} cleaned\033[0m"
done

# Restore REQUIRED_CONFIG on notification service
APP_NOTIFY="ca-${WORKLOAD}-notify"
echo -e "\n\033[1;36m→ Restoring REQUIRED_CONFIG on ${APP_NOTIFY}...\033[0m"
az containerapp update \
  --name "$APP_NOTIFY" \
  --resource-group "$RG" \
  --set-env-vars "REQUIRED_CONFIG=enabled" \
  --output none 2>/dev/null || true
echo -e "  \033[1;32m✔ ${APP_NOTIFY} config restored\033[0m"

# Restore portal image (uses azd to get the correct registry)
APP_PORTAL="ca-${WORKLOAD}-portal"
echo -e "\n\033[1;36m→ Restoring ${APP_PORTAL} container image...\033[0m"
echo -e "  \033[1;33m⚠ If the portal image was broken, re-run 'azd up' or manually set the correct image.\033[0m"

echo -e "\n\033[1;32m══════════════════════════════════════════════\033[0m"
echo -e "\033[1;32m  ✔ All services restored to healthy state.\033[0m"
echo -e "\033[1;32m══════════════════════════════════════════════\033[0m\n"
