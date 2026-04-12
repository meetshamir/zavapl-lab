#!/bin/bash
# ═══════════════════════════════════════════════════════════
# Fix Scenario: Clean up disk on Arc VM
# ═══════════════════════════════════════════════════════════

set -e

WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"
VM_NAME="vm-${WORKLOAD}-arc"

echo ""
echo "═══════════════════════════════════════════════"
echo "  🧹 Cleaning up /data partition on $VM_NAME"
echo "═══════════════════════════════════════════════"
echo ""

az vm run-command invoke \
  --resource-group "$RG" \
  --name "$VM_NAME" \
  --command-id RunShellScript \
  --scripts '
    echo "Before cleanup:"
    df -h /data 2>/dev/null || echo "/data not mounted"

    rm -f /data/scada-backups/scada-full-*.bak
    rm -f /data/grid-logs/grid-manager.log
    rm -f /data/grid-logs/core-dump-*.tmp
    rm -f /data/meter-data/interval-reads-*.dat

    echo ""
    echo "After cleanup:"
    df -h /data 2>/dev/null || echo "/data not mounted"
  ' \
  --output json 2>&1 | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for msg in data.get('value', []):
        print(msg.get('message', ''))
except: pass
"

echo ""
echo "  ✅ Disk cleaned up."
echo ""
