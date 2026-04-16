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
After generating a chart with PlotTimeSeriesData or PlotAreaChartWithCorrelation:
1. Use UploadChartToServiceNow with the incident number and the base64 image data
2. Use a descriptive filename (e.g. "latency-trend-incident.png" or "disk-usage-chart.png")
3. The chart will appear in the incident's Attachments tab
4. Add a work note referencing the attachment: "Metrics chart attached — shows [description]"

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

<Technical explanation of what caused the incident. Be specific — reference
env vars, config changes, code paths, infrastructure failures.>

Example: "The FORCE_ERROR environment variable was set to 'true' on the
ca-powergrid-outage container app. This caused the Flask middleware to intercept
all incoming requests and return HTTP 503 without processing them. The env var
was introduced in revision ca-powergrid-outage--abc1234 deployed at 14:25 UTC."

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
