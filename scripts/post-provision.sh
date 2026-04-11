#!/bin/bash
set -euo pipefail

echo -e "\n\033[1;35m╔══════════════════════════════════════════════════════╗\033[0m"
echo -e "\033[1;35m║   ⚡ PowerGrid ZeroOps Lab — Post-Provision          ║\033[0m"
echo -e "\033[1;35m╚══════════════════════════════════════════════════════╝\033[0m\n"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# ── Load deployed environment values ─────────────────────────────────
echo -e "\033[1;36m▸ Reading deployed environment values...\033[0m\n"

eval "$(azd env get-values 2>/dev/null)" || true

WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"

# ── Discover service URLs ────────────────────────────────────────────
echo -e "\033[1;36m▸ Discovering service URLs...\033[0m\n"

SERVICES=("outage" "meter" "grid" "notify" "portal")

for svc in "${SERVICES[@]}"; do
  APP="ca-${WORKLOAD}-${svc}"
  FQDN=$(az containerapp show \
    --name "$APP" \
    --resource-group "$RG" \
    --query "properties.configuration.ingress.fqdn" \
    --output tsv 2>/dev/null) || FQDN="(not deployed)"

  echo -e "  \033[1;32m${APP}\033[0m"
  echo -e "    https://${FQDN}"
  echo ""
done

# ── SRE Agent instructions ───────────────────────────────────────────
echo -e "\033[1;35m══════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;35m  Next Steps: Connect SRE Agent\033[0m"
echo -e "\033[1;35m══════════════════════════════════════════════════════\033[0m\n"

echo -e "  1. Open \033[1;36mhttps://sre.azure.com\033[0m"
echo -e "  2. Create a new connector pointing to your Azure subscription"
echo -e "  3. Select resource group: \033[1;33m${RG}\033[0m"
echo -e "  4. SRE Agent will automatically monitor your Container Apps"
echo ""

# ── Simulator instructions ───────────────────────────────────────────
echo -e "\033[1;35m══════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;35m  Inject Failures\033[0m"
echo -e "\033[1;35m══════════════════════════════════════════════════════\033[0m\n"

echo -e "  Launch the interactive menu to inject failures:"
echo -e ""
echo -e "    \033[1;33mbash scripts/menu.sh\033[0m"
echo -e ""
echo -e "  Or run individual break scripts:"
echo -e ""
echo -e "    \033[1;33mbash scripts/break-service.sh\033[0m   # 503 outage"
echo -e "    \033[1;33mbash scripts/break-memleak.sh\033[0m   # OOM on meter-api"
echo -e "    \033[1;33mbash scripts/break-perf.sh\033[0m      # 5s latency on grid-status"
echo -e "    \033[1;33mbash scripts/break-crash.sh\033[0m     # crash loop on notify"
echo -e "    \033[1;33mbash scripts/break-image.sh\033[0m     # bad image on portal"
echo -e "    \033[1;33mbash scripts/break-config.sh\033[0m    # double fault on grid-status"
echo -e ""
echo -e "  To restore everything:"
echo -e ""
echo -e "    \033[1;33mbash scripts/fix-all.sh\033[0m"
echo -e ""
