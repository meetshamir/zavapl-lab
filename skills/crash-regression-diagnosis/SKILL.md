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

## Output to caller

```
CRASH REGRESSION RCA
  service:        outage-api
  revision:       ca-powergrid-outage--0000044
  symptom:        500 on every request to /api/outages
  exception:      ModuleNotFoundError: No module named 'flask.ext'
  count_5min:     127 (matches request count — every request fails)
  prior revision: 0 exceptions
  likely cause:   Flask 3.0 upgrade removed flask.ext shim;
                  outage-api still uses 'from flask.ext.cors import CORS'
  fix direction: replace import with 'from flask_cors import CORS'
                 (one-line change, no behavior change)
```

Pass to `deployment-rollback` (immediate mitigation), then
`servicenow-incident-mgmt` (open ticket with this RCA), then
`create-pr-or-issue` (file fix PR with this body).
