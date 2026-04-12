#!/bin/bash
# ═══════════════════════════════════════════════════════════
# Break Scenario: Disk Pressure on Arc VM
# ═══════════════════════════════════════════════════════════
# Fills the /data partition on the Arc-enabled VM to simulate
# a grid management server running out of disk space (logs,
# database backups, SCADA data accumulation).
#
# Usage: bash scripts/break-disk.sh

set -e

WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"
VM_NAME="vm-${WORKLOAD}-arc"

echo ""
echo "═══════════════════════════════════════════════"
echo "  💾 DISK PRESSURE — Filling /data partition"
echo "═══════════════════════════════════════════════"
echo ""
echo "  VM:     $VM_NAME"
echo "  Target: /data partition → 95% full"
echo ""

# Fill the data disk to 95% using fallocate (fast, no I/O overhead)
echo "Injecting disk pressure via az vm run-command..."
az vm run-command invoke \
  --resource-group "$RG" \
  --name "$VM_NAME" \
  --command-id RunShellScript \
  --scripts '
    # Mount data disk if not already mounted
    if ! mountpoint -q /data; then
      mkdir -p /data
      # Find the data disk (sdc or sdd, not sda/sdb)
      DATA_DISK=$(lsblk -rno NAME,SIZE | grep "32G" | head -1 | awk "{print \$1}")
      if [ -n "$DATA_DISK" ]; then
        mkfs.ext4 -F /dev/$DATA_DISK 2>/dev/null || true
        mount /dev/$DATA_DISK /data
      fi
    fi

    mkdir -p /data/grid-logs /data/scada-backups /data/meter-data

    echo "Creating simulated grid operations data..."

    # Simulate accumulated SCADA backup files
    fallocate -l 5G /data/scada-backups/scada-full-2026-04-01.bak 2>/dev/null || \
      dd if=/dev/zero of=/data/scada-backups/scada-full-2026-04-01.bak bs=1M count=5120 2>/dev/null

    # Simulate runaway grid management logs
    fallocate -l 4G /data/grid-logs/grid-manager.log 2>/dev/null || \
      dd if=/dev/zero of=/data/grid-logs/grid-manager.log bs=1M count=4096 2>/dev/null

    # Simulate meter data accumulation
    fallocate -l 3G /data/meter-data/interval-reads-2026-Q1.dat 2>/dev/null || \
      dd if=/dev/zero of=/data/meter-data/interval-reads-2026-Q1.dat bs=1M count=3072 2>/dev/null

    # Simulate old temp files
    fallocate -l 2G /data/grid-logs/core-dump-20260401.tmp 2>/dev/null || \
      dd if=/dev/zero of=/data/grid-logs/core-dump-20260401.tmp bs=1M count=2048 2>/dev/null

    echo ""
    echo "Disk usage after fill:"
    df -h /data
    echo ""
    du -sh /data/*
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
echo "═══════════════════════════════════════════════"
echo "  ✅ Disk pressure injected!"
echo "═══════════════════════════════════════════════"
echo ""
echo "  What happens next:"
echo "    1. Azure Monitor disk % metric exceeds threshold"
echo "    2. Alert fires → SRE Agent investigates"
echo "    3. Agent runs 'df -h' and 'du -sh' on the VM"
echo "    4. Agent identifies large files (old backups, logs)"
echo "    5. Agent cleans up temp/old files"
echo "    6. Agent verifies disk usage back under threshold"
echo ""
