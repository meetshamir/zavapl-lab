---
metadata:
  api_version: azuresre.ai/v2
  kind: Skill
name: servicenow-incident-mgmt
description: "Manage ServiceNow incident lifecycle: create incidents, add work notes for audit trail, and resolve tickets. Use this skill whenever an investigation needs to be documented in ServiceNow. Follows the PowerGrid incident report template for field mapping and priority classification."
tools:
  - CreateServiceNowIncident
  - UpdateServiceNowWorkNotes
  - ResolveServiceNowIncident
  - LookupServiceNowIncident
  - UploadChartToServiceNow
---

# ServiceNow Incident Management

## Overview
This skill manages the full ServiceNow incident lifecycle for PowerGrid services.
Use it to create, update, and resolve incidents with a complete audit trail.

## When to Use
- An investigation has been triggered (by alert or manually)
- You need to document findings during an investigation
- A remediation has been completed and needs to be recorded
- An incident needs to be resolved with root cause and fix details
- You need to attach a metrics chart to an incident

## Workflow

### Creating an Incident
1. Use CreateServiceNowIncident with:
   - short_description: "[PowerGrid] <service>: <brief symptom>"
   - description: Alert details, affected service, initial observations
   - urgency: 1 (Critical), 2 (High), 3 (Medium), 4 (Low)
   - impact: 1 (High), 2 (Medium), 3 (Low)
   - category: "Software"
2. Save the returned incident number (INC00XXXXX) for subsequent updates
3. Include the incident URL in work notes: https://dev268981.service-now.com/incident.do?sysparm_query=number=<INC_NUMBER>

### Adding Work Notes (Audit Trail)
Use UpdateServiceNowWorkNotes at each investigation phase:
- "Investigating: Querying App Insights for error traces..."
- "Finding: AttributeError in outage-api at line 116, crew_status is None"
- "Correlation: Regression from ADO pipeline run #47 (commit abc123)"
- "Remediation: Rolled back to previous Container App revision"
- "Validation: /outages endpoint returns HTTP 200, service restored"

### Resolving an Incident
Use ResolveServiceNowIncident with:
- incident_id: The INC number from creation
- resolution_notes: Root cause + what was done + permanent fix status

### Looking Up Existing Incidents
Use LookupServiceNowIncident to:
- Check if a related incident already exists before creating a duplicate
- Search by short description or keywords to find existing tickets
Note: Native ServiceNow tools now accept INC numbers directly — no sys_id translation needed.

### Attaching a Metrics Chart
Use UploadChartToServiceNow to generate and attach a chart to the incident:
1. Pass the incident number and a KQL query that returns time-series data
2. The tool runs the query, generates the chart (matplotlib), and uploads to SNOW automatically
3. Use a descriptive chart_title (e.g. "Disk Usage During Incident" or "Request Latency Spike")
4. Add a work note referencing the attachment: "Metrics chart attached — shows [description]"
Example KQL: requests | where timestamp > ago(30m) | summarize avg(duration), count() by bin(timestamp, 1m)

# ServiceNow Incident Report Template

## Purpose
Use this template when filing or updating ServiceNow incidents for the PowerGrid utility portal. The SRE Agent should populate these fields during investigation and include them in the incident report.

---

## ServiceNow Fields

| Field | Value / Guidance |
|-------|------------------|
| **Short description** | `[PowerGrid] <service-name>: <brief symptom>` — e.g., `[PowerGrid] outage-api: HTTP 503 on all endpoints` |
| **Description** | Detailed description including affected service, symptoms, error codes, and initial findings |
| **Category** | `Software` |
| **Subcategory** | `Application` or `Container Platform` |
| **Priority** | P1 (Critical) / P2 (High) / P3 (Medium) / P4 (Low) — see priority matrix below |
| **Impact** | 1-High / 2-Medium / 3-Low |
| **Urgency** | 1-High / 2-Medium / 3-Low |
| **Assignment group** | `PowerGrid-SRE` |
| **Assigned to** | Auto-assigned or on-call engineer |
| **Configuration item** | `ca-powergrid-<service>` (e.g., `ca-powergrid-outage`) |
| **Business service** | `PowerGrid Utility Portal` |

---

## Priority Matrix

| Impact \ Urgency | High | Medium | Low |
|-------------------|------|--------|-----|
| **High** (all users affected) | P1 — Critical | P2 — High | P3 — Medium |
| **Medium** (partial users) | P2 — High | P3 — Medium | P4 — Low |
| **Low** (minimal impact) | P3 — Medium | P4 — Low | P4 — Low |

---

## Incident Report Body Template

Use the following markdown structure for the incident description and work notes:

```markdown
# Incident Report: <short description>

- **Incident ID:** <ServiceNow INC number>
- **Service:** <container-app-name> (rg: <resource-group>)
- **Environment:** Production / Staging / Development
- **Severity:** P1 / P2 / P3 / P4
- **Status:** Investigating / Identified / Mitigated / Resolved

---

## Summary

<2-3 sentences: what happened, what was observed, who is affected.>

Example: "The outage-api service (ca-powergrid-outage) began returning HTTP 503 errors
on all endpoints at approximately 14:30 UTC. All outage reporting and lookup functionality
is unavailable. Customer-facing portal shows error messages for outage-related features."

---

## Impact

- **User Impact:** <description of user-facing impact>
- **Services Affected:** <list of affected services>
- **Estimated Users Affected:** <count or percentage>
- **Revenue Impact:** <if applicable>

---

## Timeline (UTC)

| Time (UTC) | Event |
|------------|-------|
| HH:MM | First anomaly detected (alert fired / user report) |
| HH:MM | Investigation started |
| HH:MM | Root cause identified |
| HH:MM | Remediation applied |
| HH:MM | Service restored / Incident resolved |

---

## Root Cause

<Technical explanation of what caused the incident. **Must include the
actual code-level cause**, not a paraphrase. Quote the offending
function and the exact source lines (≤5 lines, with file path and
line numbers) from the diagnosis skill's `code_cause` block. State
the mechanism in plain English: WHICH function, WHAT it does, WHY it
produces the observed symptom, by HOW MUCH (latency added, % of
requests affected, etc.). If the cause is a config/env delta, also
include `config_delta` showing old → new value and the deploy
artifact line that introduced it.>

Example (perf regression):
"The :latest image of grid-status-api enables a global Express
middleware that delays every request:

```js
// src/grid-status-api/server.js:42-46  (commit abc1234, build #44)
if (SIMULATE_DELAY_MS > 0) {
  app.use((_req, _res, next) => {
    setTimeout(next, SIMULATE_DELAY_MS);
  });
}
```

The deploy YAML for revision ca-powergrid-grid--0000031 sets
`SIMULATE_DELAY_MS=2000`, so every endpoint sleeps 2 s before
responding. The :stable image was built from the same source but
deployed without the env var, so the middleware was a no-op."

Example (crash regression):
"src/outage-api/app.py line 14 imports `from flask.ext.cors import CORS`.
Flask 3.0 (introduced in build #44) removed the legacy `flask.ext`
shim, so module load fails at process startup → every request returns
500 because Gunicorn never gets a working app."

Example (config regression):
"k8s/base/application.yaml line 73 (commit abc1234) removed
`REQUIRED_CONFIG=enabled` from the notification-svc env. The /notify
handler short-circuits with 503 when that env is absent
(src/notification-svc/server.js:18-20)."

---

## Evidence

### Logs
<Paste relevant log excerpts or KQL query results>

### Metrics
| Metric | Before Incident | During Incident | After Fix |
|--------|----------------|-----------------|-----------|
| Error Rate | 0% | 100% | 0% |
| Response Time | 150ms | N/A (503) | 145ms |
| Restart Count | 0 | 0 | 0 |

### KQL Queries Used
<Include the KQL queries used during investigation for reproducibility>

---

## Resolution

<What was done to fix the issue. Include exact commands run.>

Example:
"Removed the FORCE_ERROR environment variable from the container app:
`az containerapp update -g rg-powergrid-dev -n ca-powergrid-outage --remove-env-vars FORCE_ERROR`
New revision ca-powergrid-outage--def5678 was created and activated.
Service returned to healthy state at 15:10 UTC."

---

## Prevention

### Immediate Actions
- [ ] <Action item 1 — e.g., add deployment validation to prevent FORCE_ERROR in production>
- [ ] <Action item 2 — e.g., add pre-deployment health check gate>

### Long-Term Improvements
- [ ] <Improvement 1 — e.g., implement deployment approval workflow>
- [ ] <Improvement 2 — e.g., add canary deployment with automatic rollback>
- [ ] <Improvement 3 — e.g., enhance monitoring to detect this class of issue faster>

### Monitoring Gaps Identified
- [ ] <Gap 1 — e.g., no alert for FORCE_ERROR env var presence>
- [ ] <Gap 2 — e.g., alert threshold too high, delayed detection>
```

---

## Service-Specific Quick References

### outage-api (ca-powergrid-outage)
- **Common RCA:** `FORCE_ERROR=true` env var → 503 on all endpoints
- **Fix:** `az containerapp update -g <rg> -n ca-powergrid-outage --remove-env-vars FORCE_ERROR`
- **Runbook:** [outage-api-runbook.md](outage-api-runbook.md)

### meter-api (ca-powergrid-meter)
- **Common RCA:** `SIMULATE_OOM=true` → memory leak → OOM kill → restarts
- **Fix:** `az containerapp update -g <rg> -n ca-powergrid-meter --remove-env-vars SIMULATE_OOM`
- **Runbook:** [meter-api-runbook.md](meter-api-runbook.md)

### grid-status-api (ca-powergrid-grid)
- **Common RCA:** `SIMULATE_DELAY_MS=<value>` → artificial latency
- **Fix:** `az containerapp update -g <rg> -n ca-powergrid-grid --remove-env-vars SIMULATE_DELAY_MS`
- **Runbook:** [grid-status-runbook.md](grid-status-runbook.md)

### notification-svc (ca-powergrid-notify)
- **Common RCA:** Missing `REQUIRED_CONFIG` env var → crash loop
- **Fix:** `az containerapp update -g <rg> -n ca-powergrid-notify --set-env-vars REQUIRED_CONFIG=enabled`
- **Runbook:** [notification-svc-runbook.md](notification-svc-runbook.md)

---

## Labels / Tags for Classification

| Condition | ServiceNow Category | Tags |
|-----------|---------------------|------|
| HTTP 5xx errors | Application Failure | `http-5xx`, `service-unavailable` |
| OOM / Memory leak | Resource Exhaustion | `oom`, `memory-leak` |
| High latency | Performance Degradation | `latency`, `slow-response` |
| Crash loop | Application Crash | `crash-loop`, `startup-failure` |
| Bad deployment | Change-Related | `deployment`, `rollback` |

---

## Post-Incident Review Checklist

After the incident is resolved, ensure:
- [ ] Incident report is complete with all sections filled
- [ ] Timeline is accurate with UTC timestamps
- [ ] Root cause is clearly identified and documented
- [ ] Resolution steps are documented with exact commands
- [ ] Prevention actions are created as follow-up tasks
- [ ] Monitoring gaps are identified and ticketed
- [ ] Stakeholders are notified of resolution
- [ ] Knowledge base is updated if new failure mode discovered
