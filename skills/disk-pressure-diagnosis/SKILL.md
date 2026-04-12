---
metadata:
  api_version: azuresre.ai/v2
  kind: Skill
name: disk-pressure-diagnosis
description: "Diagnose and remediate disk pressure on Azure VMs. Investigates disk usage, identifies large files, old backups, runaway logs, and recommends cleanup or disk expansion. Use when disk utilization alerts fire or a VM reports low free space."
---

# Disk Pressure Diagnosis

## Overview
Investigate and remediate disk space issues on Azure VMs (including Arc-enabled servers).

## Phase 1: Detect — Confirm Disk Pressure

### Check disk utilization
```bash
az vm run-command invoke --resource-group <RG> --name <VM_NAME> --command-id RunShellScript --scripts "df -h"
```

Look for partitions above 85% (warning) or 95% (critical).

### Check disk metrics in Azure Monitor
```kql
InsightsMetrics
| where Namespace == "LogicalDisk" and Name == "FreeSpacePercentage"
| where Computer contains "<VM_NAME>"
| where TimeGenerated > ago(24h)
| summarize avg(Val) by bin(TimeGenerated, 1h), Tags
| order by TimeGenerated desc
```

## Phase 2: Investigate — Find What's Using Space

### Largest directories
```bash
az vm run-command invoke --resource-group <RG> --name <VM_NAME> --command-id RunShellScript --scripts "du -sh /* 2>/dev/null | sort -rh | head -20"
```

### Drill into the largest
```bash
az vm run-command invoke --resource-group <RG> --name <VM_NAME> --command-id RunShellScript --scripts "du -sh /data/* 2>/dev/null | sort -rh | head -20"
```

### Large individual files
```bash
az vm run-command invoke --resource-group <RG> --name <VM_NAME> --command-id RunShellScript --scripts "find / -type f -size +100M -exec ls -lh {} \; 2>/dev/null | sort -k5 -rh | head -20"
```

### Common culprits
```bash
# Old log files
find /var/log -type f -name '*.log' -size +50M -ls

# Old backups
find / -type f \( -name '*.bak' -o -name '*.backup' -o -name '*.dump' \) | head -20

# Temp files older than 7 days
find /tmp -type f -mtime +7 -ls

# Core dumps
find / -type f \( -name 'core.*' -o -name '*.core' \)
```

## Phase 3: Root Cause — Classify the Problem

| Pattern | Likely Cause | Check |
|---|---|---|
| Large .bak/.dump files in /data | Backup retention not configured | Is there a cron job? Is retention set? |
| Single giant .log file | App logging at DEBUG/TRACE level | Check app log config, logrotate config |
| Many small files filling inodes | Runaway job creating temp files | Check `df -i` for inode usage |
| Steady growth over days | Data accumulation without cleanup | Check batch job outputs |
| Sudden spike | One-time event (dump, export, failed job) | Check timestamps of large files |

## Phase 4: Remediate

### Option A: Clean up (after confirming files are safe to delete)
```bash
# Rotate and compress logs
find /var/log -name '*.log' -size +100M -exec gzip {} \;

# Remove old backups
rm -f /data/backups/*.bak.old

# Clear old temp files
find /tmp -type f -mtime +7 -delete
```

### Option B: Expand disk
```bash
az disk show --resource-group <RG> --name <DISK_NAME> --query diskSizeGb
az disk update --resource-group <RG> --name <DISK_NAME> --size-gb <NEW_SIZE>
# Then resize partition inside the VM
```

## Phase 5: Validate
```bash
az vm run-command invoke --resource-group <RG> --name <VM_NAME> --command-id RunShellScript --scripts "df -h"
```
Confirm target partition is below 80%.

## Overview
Provide a clear overview of what this skill does and when it should be used.

## Capabilities
- List the main capabilities of this skill
- What problems does it solve?
- What can it help with?

## Instructions
Provide detailed instructions for using this skill:

1. When to use this skill
2. How to approach tasks with this skill
3. Best practices and guidelines
4. Any constraints or limitations

## Example Workflows

### Example 1: [Task Name]
- Goal: Describe what the user wants to accomplish
- Steps:
  1. First step
  2. Second step
  3. Third step
- Expected outcome: What should happen

### Example 2: [Another Task]
- Goal: Another use case
- Steps:
  1. Step one
  2. Step two
- Expected outcome: Result

## Related Skills
- List any related skills that might be used together with this one
- When to handoff or use other skills

## Additional Resources
- Links to documentation
- Related runbooks
- Other helpful information
