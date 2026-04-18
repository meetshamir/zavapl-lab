---
metadata:
  api_version: azuresre.ai/v2
  kind: Skill
name: crash-regression-diagnosis
description: |
  Deep-dive diagnosis when deployment-validation has flagged a service
  with elevated 5xx errors AND exceptions present in App Insights.
  Identifies whether the cause is an unhandled exception, OOMKilled,
  ImagePullBackOff, missing dependency, or import error. Produces a
  structured RCA suitable for SNOW work note + fix PR.
---

# Crash Regression Diagnosis

## When to use
Invoke after `deployment-validation` returns FAIL with category
`crash` (5xx errors AND exceptions present in revision-scoped AI).

## Investigation steps

### 1. Top exceptions on the new revision
```kusto
AppExceptions
| where TimeGenerated >= datetime({DEPLOY_TIME})
| where cloud_RoleInstance has "{REVISION_NAME}"
| summarize count() by Type, OuterMessage
| order by count_ desc
```

### 2. Sample full stack trace
```kusto
AppExceptions
| where TimeGenerated >= datetime({DEPLOY_TIME})
| where cloud_RoleInstance has "{REVISION_NAME}"
| project TimeGenerated, Type, OuterMessage, Method, Details
| take 3
```

### 3. Check for container-level failures (OOM, ImagePullBackOff)
Use **Monitor Resource Log Query** on
`ContainerAppSystemLogs_CL` table filtered by
`RevisionName_s == "{REVISION_NAME}"`. Look for:
- `OOMKilled` — bump memory request OR fix leak
- `ImagePullBackOff` / `ErrImagePull` — image tag missing in ACR
- `CrashLoopBackOff` — process exits at startup; check console logs
- `Liveness probe failed` — endpoint never came up

### 4. Check container console logs for startup errors
```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated >= datetime({DEPLOY_TIME})
| where RevisionName_s == "{REVISION_NAME}"
| where Log_s contains "Error" or Log_s contains "Exception"
   or Log_s contains "ImportError" or Log_s contains "ModuleNotFound"
   or Log_s contains "Traceback"
| project TimeGenerated, Log_s
| take 20
```

### 5. Diff against previous revision env
If exceptions reference missing config / undefined vars, also call the
service-specific diagnosis skill (e.g. `outage-api-diagnosis`) to
inspect env-var differences vs the prior revision.

### 6. Pinpoint the code change (REQUIRED for the SNOW summary)
A generic "exception in the code" is NOT acceptable. Identify the
SPECIFIC change:
  a. Get the build commit SHA from the failing build via
     `GetPipelineRunHistory` on **PowerGrid-Build** → `sourceVersion`.
  b. Get the previous healthy build's SHA the same way.
  c. Browse the diff for the failing service (e.g.
     `src/outage-api/`) — focus on the file/line referenced in the
     exception stack trace.
  d. Quote the exact function and the offending lines (≤5 lines) in
     the RCA. Example for a NoneType crash:
     ```python
     # src/outage-api/app.py:126  (commit abc1234)
     enriched["crew_display"] = crew.upper().replace("_", " ")
     # crew is read from outage["crew_status"] which is None for
     # outages that haven't been dispatched yet
     ```
  e. State the mechanism: WHICH line throws, WHAT input causes it,
     WHY it slipped past tests, what the safe call should be.

## Output to caller

```
CRASH REGRESSION RCA
  service:        outage-api
  revision:       ca-powergrid-outage--0000044
  deploy_time:    21:02 UTC
  symptom:        500 on every GET /outages with active outages
  exception:      AttributeError: 'NoneType' object has no attribute 'upper'
                  (src/outage-api/app.py line 126, in enrich_outage)
  count_5min:     127 (matches request count for /outages)
  prior revision: 0 exceptions on this endpoint
  code_cause:     |
    src/outage-api/app.py line 126 (commit abc1234, build #44,
    GRID-2847 enrichment work):

      enriched["crew_display"] = crew.upper().replace("_", " ")

    `crew` is read from `outage["crew_status"]`. SCADA returns
    `crew_status: None` for any outage that hasn't been dispatched
    yet (~30% of records in production). Calling `.upper()` on None
    raises AttributeError, propagating as a 500 to the caller. Unit
    tests passed because the test fixture only had outages with
    completed dispatch records.
  fix direction: guard the call — `(crew or "unassigned").upper()`,
                 OR skip the enrichment when crew_status is None.
```

Pass to `deployment-rollback` (immediate mitigation), then
`servicenow-incident-mgmt` (open ticket with this RCA), then
`create-pr-or-issue` (file fix PR with this body). The `code_cause`
block goes verbatim into the SNOW **Root Cause** section.
