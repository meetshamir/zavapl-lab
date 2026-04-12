#!/bin/bash
# ═══════════════════════════════════════════════════════════
# Break Scenario: App Service Misconfiguration (Vanilla)
# ═══════════════════════════════════════════════════════════
# This scenario requires NO custom agents, skills, or tools.
# SRE Agent uses only its built-in reasoning to diagnose.
#
# What it does:
#   Changes the App Service container port to 9999 (wrong).
#   The app listens on 8080 but App Service routes to 9999.
#   Health checks fail, site returns 503.
#   SRE Agent must figure this out from App Service logs.
#
# Usage: bash scripts/break-appservice.sh

set -e

WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"

echo ""
echo "═══════════════════════════════════════════════"
echo "  🌐 APP SERVICE MISCONFIGURATION (Vanilla)"
echo "═══════════════════════════════════════════════"
echo ""
echo "  This scenario uses NO custom agents or skills."
echo "  SRE Agent must diagnose using built-in reasoning."
echo ""

echo "Setting WEBSITES_PORT=9999 (app listens on 8080)..."
az webapp config appsettings set \
  --name "app-${WORKLOAD}-portal" \
  --resource-group "$RG" \
  --settings WEBSITES_PORT=9999 \
  --output none 2>/dev/null

echo "Restarting App Service..."
az webapp restart \
  --name "app-${WORKLOAD}-portal" \
  --resource-group "$RG" \
  --output none 2>/dev/null

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ App Service misconfigured!"
echo "═══════════════════════════════════════════════"
echo ""
echo "  What happened:"
echo "    WEBSITES_PORT set to 9999 (container listens on 8080)"
echo "    App Service can't reach the container → 503 errors"
echo ""
echo "  Demo this WITHOUT custom agents:"
echo "    1. Go to sre.azure.com → sre-powergrid → New chat"
echo "    2. DON'T select a custom agent (use the meta agent)"
echo "    3. Ask: 'The PowerGrid portal at app-powergrid-portal"
echo "       is returning 503 errors. Can you investigate?'"
echo "    4. The agent should find the port mismatch in App Service"
echo "       logs and recommend fixing WEBSITES_PORT to 8080"
echo ""
echo "  To fix manually:"
echo "    bash scripts/fix-appservice.sh"
echo ""
