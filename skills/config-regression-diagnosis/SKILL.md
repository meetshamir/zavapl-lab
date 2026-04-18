---
metadata:
  api_version: azuresre.ai/v2
  kind: Skill
name: config-regression-diagnosis
description: |
  Deep-dive diagnosis when deployment-validation has flagged a service
  with elevated 5xx errors but NO exceptions in App Insights — the
  classic shape of a missing-env-var or bad-downstream-URL regression
  where the app returns a clean 5xx without crashing.
---

# Config Regression Diagnosis

## When to use
Invoke after `deployment-validation` returns FAIL with category
`config` (5xx errors but no AppExceptions). Common signatures:
- A previously-required env var was removed from the new revision.
- A downstream URL was changed to point to a wrong / non-existent host.
- A feature flag was flipped on without the dependent code path ready.
- A secret was rotated but the app still references the old value.

## Investigation steps

### 1. Diff env vars: new revision vs previous
For the affected Container App:

```bash
# Current revision env
az containerapp revision show -g rg-powergrid \
  -n {APP_NAME} --revision {NEW_REVISION} \
  --query "properties.template.containers[0].env" -o json

# Previous revision env
az containerapp revision show -g rg-powergrid \
  -n {APP_NAME} --revision {PREV_REVISION} \
  --query "properties.template.containers[0].env" -o json
```

Identify env vars REMOVED, ADDED, or VALUE-CHANGED. Cross-reference
with the per-service diagnosis skill (e.g. `notification-svc-diagnosis`)
which lists each service's REQUIRED env vars.

### 2. Look for "missing config" responses
```kusto
AppRequests
| where TimeGenerated >= datetime({DEPLOY_TIME})
| where cloud_RoleInstance has "{REVISION_NAME}"
| where Success == false
| summarize count() by ResultCode, Name
| order by count_ desc
```
Then sample a failing request body via `AppDependencies` /
`AppTraces` for that OperationId — the response body often says
"REQUIRED_CONFIG not set" or similar.

### 3. Container console for explicit warnings
```kusto
ContainerAppConsoleLogs_CL
| where TimeGenerated >= datetime({DEPLOY_TIME})
| where RevisionName_s == "{REVISION_NAME}"
| where Log_s contains "config" or Log_s contains "env"
   or Log_s contains "missing" or Log_s contains "REQUIRED"
| take 20
```

### 4. Validate downstream URLs respond
For each external URL referenced by the app's env, do a quick
`ProbeServiceLatency(name, url, '/healthz', count=2)` to confirm
reachability. A 5xx because the app can't reach `https://api.partner/`
is still a config-shaped failure (wrong URL or firewall change).

### 5. Pinpoint the exact config delta + the code path that fails (REQUIRED)
A generic "config missing" is NOT acceptable. Identify:
  a. Which env var / config key changed (name + old value → new value).
  b. Which deploy artifact introduced the change — the deploy YAML
     diff (e.g. `k8s/base/application.yaml`) between the previous
     healthy build's commit SHA and this build's commit SHA. Get both
     SHAs via `GetPipelineRunHistory` on **PowerGrid-Build**.
  c. The code path that reads that config and short-circuits — quote
     the exact lines (≤5) showing the gating logic. Example:
     ```js
     // src/notification-svc/server.js:18-20  (unchanged for months)
     if (!process.env.REQUIRED_CONFIG) {
       return res.status(503).json({ error: "REQUIRED_CONFIG not set" });
     }
     ```
  d. State the mechanism: WHICH env var, WHERE it was removed, WHICH
     handler reads it, WHY the code returns 503 when missing.

## Output to caller

```
CONFIG REGRESSION RCA
  service:        notification-svc
  revision:       ca-powergrid-notify--0000017
  deploy_time:    21:02 UTC
  symptom:        every POST /notify returns 503 within 50ms
  count_5min:     94
  prior revision: REQUIRED_CONFIG=enabled  (worked fine)
  config_delta:   REQUIRED_CONFIG removed from env
                  (k8s/base/application.yaml line 73, commit abc1234)
  code_cause:     |
    src/notification-svc/server.js lines 18-20 (unchanged for months):

      if (!process.env.REQUIRED_CONFIG) {
        return res.status(503).json({ error: "REQUIRED_CONFIG not set" });
      }

    The /notify handler short-circuits with 503 when the env var is
    absent. The deploy template was edited to remove the env var
    declaration, so every request hits this guard.
  fix direction: re-add REQUIRED_CONFIG=enabled to ACA env vars
                 (revert the YAML line); OR make REQUIRED_CONFIG
                 optional with a sensible default in the code.
```

Hand off to `deployment-rollback` → `servicenow-incident-mgmt` →
`create-pr-or-issue`. The `code_cause` + `config_delta` blocks go
verbatim into the SNOW **Root Cause** section.
