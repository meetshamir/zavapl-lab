#!/bin/bash
# ═══════════════════════════════════════════════════════════
# Break Scenario 5: Organic Load Spike (No Bug)
# ═══════════════════════════════════════════════════════════
# Simulates a regional grid event where thousands of customers
# simultaneously check grid status. No code bug — just real load
# causing natural latency increase.
#
# SRE Agent should investigate and find:
#   - No recent deployments
#   - No code errors
#   - CPU at 95%, response times elevated
#   - Recommendation: scale out, not rollback
#
# Usage: bash scripts/break-load.sh [duration_seconds] [concurrency]

set -e

WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"
DURATION="${1:-300}"
CONCURRENCY="${2:-50}"

GRID_URL="https://ca-${WORKLOAD}-grid.$(az containerapp show -n ca-${WORKLOAD}-grid -g $RG --query 'properties.configuration.ingress.fqdn' -o tsv 2>/dev/null | cut -d. -f2-)"

if [ -z "$GRID_URL" ] || [ "$GRID_URL" = "https://ca-${WORKLOAD}-grid." ]; then
    GRID_FQDN=$(az containerapp show -n "ca-${WORKLOAD}-grid" -g "$RG" --query 'properties.configuration.ingress.fqdn' -o tsv 2>/dev/null)
    GRID_URL="https://${GRID_FQDN}"
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "  📈 ORGANIC LOAD SPIKE — No Bug, Just Traffic"
echo "═══════════════════════════════════════════════"
echo ""
echo "  Target:      $GRID_URL/regions"
echo "  Duration:    ${DURATION}s"
echo "  Concurrency: ${CONCURRENCY} parallel requests"
echo ""
echo "  This is NOT a code bug. It simulates a regional"
echo "  grid event causing a traffic surge."
echo ""

# Check if hey/ab/curl is available
if command -v hey &> /dev/null; then
    echo "Using 'hey' for load generation..."
    hey -z "${DURATION}s" -c "$CONCURRENCY" -q 10 "$GRID_URL/regions"
elif command -v ab &> /dev/null; then
    echo "Using 'ab' for load generation..."
    TOTAL=$((CONCURRENCY * DURATION / 2))
    ab -n "$TOTAL" -c "$CONCURRENCY" -t "$DURATION" "$GRID_URL/regions"
else
    echo "Using 'curl' loop for load generation..."
    echo "(Install 'hey' for better load testing: go install github.com/rakyll/hey@latest)"
    echo ""
    
    END=$((SECONDS + DURATION))
    COUNT=0
    ERRORS=0
    
    while [ $SECONDS -lt $END ]; do
        for i in $(seq 1 $CONCURRENCY); do
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GRID_URL/regions" --max-time 10 2>/dev/null &)
        done
        wait
        COUNT=$((COUNT + CONCURRENCY))
        
        if [ $((COUNT % 100)) -eq 0 ]; then
            ELAPSED=$((SECONDS))
            echo "  $(date '+%H:%M:%S') — Sent $COUNT requests (${ELAPSED}s elapsed)"
        fi
        sleep 0.5
    done
    
    echo ""
    echo "  Total requests sent: $COUNT"
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ Load spike complete"
echo "═══════════════════════════════════════════════"
echo ""
echo "  The Azure Monitor high-latency alert should fire."
echo "  SRE Agent will investigate and find:"
echo "    - No recent deployments (this is NOT a bad deploy)"
echo "    - No code errors"
echo "    - High CPU utilization"
echo "    - Elevated response times under load"
echo "    → Recommendation: scale out replicas"
echo ""
