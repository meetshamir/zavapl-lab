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
- **Startup banner lines that mention latency injection** — e.g.
  `SIMULATE_DELAY_MS=N — artificial latency enabled` (Node) or
  similar Python equivalents. These reveal env-var-driven latency
  middleware that isn't visible in dependency traces.

### 6. Check chaos / latency-injection endpoints
Some services expose an admin endpoint that injects server-side
latency (used by load tests but sometimes left enabled). For each
slow service, GET `https://<service-fqdn>/chaos/status` and
`/chaos/latency` if they exist. If `active: true` or `latency_ms > 0`,
**that is your root cause** — not a code regression. Disable via
`DELETE /chaos/latency` or restart the revision.

### 7. Pinpoint the code change (REQUIRED for the SNOW summary)
A generic "latency baked into the code" is NOT acceptable. You must
identify the SPECIFIC change. Steps:
  a. Get the build commit SHA from the failing build:
     `GetPipelineRunHistory` on **PowerGrid-Build** for buildId
     → `sourceVersion` field.
  b. Get the previous healthy build's commit SHA the same way.
  c. Use `GetFileContents` / repo browse on saziz_microsoft/zavapl-lab
     to inspect the diff for the failing service's source dir
     (e.g. `src/grid-status-api/`). Pay attention to:
       - new `setTimeout` / `await sleep` / `time.sleep` calls
       - new env-var reads that gate latency middleware
       - new synchronous loops over request payloads
       - new external HTTP/DB calls without timeouts
       - changes to Dockerfile ENV / CMD that toggle latency
  d. Quote the exact function name and the offending lines (≤5 lines)
     in the RCA. Example:
     ```js
     // src/grid-status-api/server.js:42-46  (commit abc1234)
     if (SIMULATE_DELAY_MS > 0) {
       app.use((_req, _res, next) => {
         setTimeout(next, SIMULATE_DELAY_MS);  // adds 2000ms per request
       });
     }
     ```
  e. State the mechanism in plain English: WHICH function, WHAT it
     does, WHY it slows requests, by HOW MUCH.

## Output to caller
Return a structured RCA. The `code_cause` field is REQUIRED and must
quote actual source lines, not paraphrase.

```
PERF REGRESSION RCA
  service:        grid-status-api
  revision:       ca-powergrid-grid--0000031
  deploy_time:    21:02 UTC
  scope:          all endpoints (uniform 2000 ms floor)
  p95 before:     115 ms (revision 0000030, image :stable)
  p95 after:      2154 ms (revision 0000031, image :latest)
  dependencies:   p95 < 50 ms (not the bottleneck)
  chaos_endpoint: /chaos/status returns inactive
  startup_log:    "SIMULATE_DELAY_MS=2000 — artificial latency enabled"
  code_cause:     |
    src/grid-status-api/server.js lines 42-46 (commit abc1234,
    introduced in build #44):

      if (SIMULATE_DELAY_MS > 0) {
        app.use((_req, _res, next) => {
          setTimeout(next, SIMULATE_DELAY_MS);
        });
      }

    A global Express middleware delays EVERY request by
    SIMULATE_DELAY_MS milliseconds before invoking the handler. The
    :latest image was built with the deploy YAML setting
    SIMULATE_DELAY_MS=2000, which makes every endpoint sleep 2 s
    before responding.
  fix direction: revert the deploy manifest's SIMULATE_DELAY_MS
                 setting to 0 (or remove the env var); OR remove the
                 dev-only middleware entirely from server.js so it
                 cannot be re-enabled in production.
```

This RCA is the body for the `servicenow-incident-mgmt` work note and
the `create-pr-or-issue` PR description. The `code_cause` block goes
verbatim into the SNOW **Root Cause** section so on-callers see the
exact lines without re-investigating.
