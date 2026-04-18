---
metadata:
  api_version: azuresre.ai/v2
  kind: Skill
name: perf-regression-diagnosis
description: |
  Deep-dive diagnosis when deployment-validation has flagged a service
  as a perf regression (sequential or burst p95 > 1500 ms, no errors).
  Identifies whether the cause is CPU-bound code (e.g. O(n²) loop),
  slow synchronous I/O, blocking dependency, or cold-start. Produces a
  one-paragraph root-cause hypothesis suitable for the SNOW work note
  and the fix PR description.
---

# Perf Regression Diagnosis

## When to use
Invoke after `deployment-validation` returns FAIL with category
`perf` for one or more services. Input from caller: `service_name`,
`revision_name`, `deploy_time`, observed p95 from probes.

## Investigation steps

### 1. Confirm scope of slowness — which endpoints?
Use **Monitor Workspace Log Query** with:

```kusto
AppRequests
| where TimeGenerated >= datetime({DEPLOY_TIME})
| where cloud_RoleInstance has "{REVISION_NAME}"
| summarize p95 = percentile(DurationMs, 95), count() by Name
| order by p95 desc
```

If only ONE endpoint is slow → isolated code path (most likely a new
feature). If ALL endpoints are slow → infrastructure / framework / GC.

### 2. Inspect dependencies
```kusto
AppDependencies
| where TimeGenerated >= datetime({DEPLOY_TIME})
| where cloud_RoleInstance has "{REVISION_NAME}"
| summarize p95 = percentile(DurationMs, 95), count() by Type, Target
| order by p95 desc
```

If dependency p95 ≈ request p95 → downstream is the bottleneck (DB,
external API). If dependency p95 << request p95 → bottleneck is in-
process (CPU, GC, sync code).

### 3. Sample slow traces
```kusto
AppRequests
| where TimeGenerated >= datetime({DEPLOY_TIME})
| where cloud_RoleInstance has "{REVISION_NAME}"
| where DurationMs > 1500
| project TimeGenerated, Name, DurationMs, Url, OperationId
| take 5
```
For each OperationId, follow with `union AppRequests, AppDependencies,
AppExceptions, AppTraces | where OperationId == "..."` to see the full
call tree.

### 4. Compare to previous revision
Repeat (1) for the PREVIOUS revision (use the previous revision_name
from the ACA revision history) over the same kind of window. If the
prior revision had p95 < 200 ms on the same endpoint, that confirms
the new code is the cause.

### 5. Check container console logs for hot loops / GC
Use **Monitor Resource Log Query** on the Container App's console log
stream filtered by `RevisionName == "{REVISION_NAME}"`. Look for:
- Repeated identical log lines (hot loop)
- GC pause warnings
- "EVENTLOOP_BLOCKED", "long task" warnings (Node)
- Thread pool saturation (Python)

## Output to caller
Return a structured RCA:

```
PERF REGRESSION RCA
  service:        grid-status-api
  revision:       ca-powergrid-grid--0000029
  scope:          single endpoint /regions
  p95 before:     115 ms (revision 0000028)
  p95 after:      9837 ms (revision 0000029, +85x)
  dependencies:   p95 < 50 ms (not the bottleneck)
  suspected:      synchronous CPU work in /regions handler
  likely cause:   O(n²) checksum loop added in commit <sha>
  fix direction: replace nested loop with single-pass hash; OR move
                 checksum to async worker; OR cache by payload hash.
```

This RCA is the body for the `servicenow-incident-mgmt` work note and
the `create-pr-or-issue` PR description.
