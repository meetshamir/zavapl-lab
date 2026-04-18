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
A generic "config missing" is NOT acceptable. The lab's config
regressions are typically **hardcoded source-level constants** (not
runtime env vars), so the diff must inspect actual code:
  a. Get the build commit SHA from the failing build via
     `GetPipelineRunHistory` on **PowerGrid-Build** → `sourceVersion`,
     plus the previous healthy build's SHA.
  b. Browse the failing service's source dir (e.g.
     `src/notification-svc/`) for changed constants — URLs, ports,
     hostnames, feature flags.
  c. The actual failure path is usually a downstream call that times
     out or refuses connection because the constant points to the
     wrong endpoint. Trace it back to its declaration site.
  d. Quote the offending line(s) (≤5 lines) and the dependent call.
     Example for a wrong gateway port:
     ```go
     // src/notification-svc/main.go:35  (commit abc1234)
     const gatewayURL = "http://notification-gateway.internal:9443/api/v2/send"
     // INFRA-3291 migration; old port 8443 is closed in production
     ```
  e. State the mechanism: WHICH constant changed, WHERE it's used,
     WHY the new value is wrong (port closed, host renamed, TLS
     mismatch, etc.), and HOW the failure surfaces (timeout, conn
     refused, 503, etc.).

## Output to caller

```
CONFIG REGRESSION RCA
  service:        notification-svc
  revision:       ca-powergrid-notify--0000017
  deploy_time:    21:02 UTC
  symptom:        every POST /send returns 503 after ~5s timeout
  count_5min:     94
  prior revision: gatewayURL = ":8443"  (worked fine)
  code_cause:     |
    src/notification-svc/main.go line 35 (commit abc1234, build #44,
    INFRA-3291 TLS-1.3 migration):

      const gatewayURL = "http://notification-gateway.internal:9443/api/v2/send"

    The internal gateway listens on port 8443 in production; port
    9443 was the staging endpoint during the migration window and
    was never opened in prod. The /send handler dials this URL on
    every request and times out after ~5s, returning 503 to the
    caller. Health check passes because it doesn't exercise the
    downstream call.
  fix direction: revert the constant to `:8443`; OR (better) move
                 the gateway URL into a runtime config so it can be
                 changed without a redeploy, and add a
                 startup-time TCP connect probe so the service fails
                 fast instead of passing health checks.
```

Hand off to `deployment-rollback` → `servicenow-incident-mgmt` →
`create-pr-or-issue`. The `code_cause` block goes verbatim into the
SNOW **Root Cause** section.
