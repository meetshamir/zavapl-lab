---
metadata:
  api_version: azuresre.ai/v2
  kind: Skill
name: servicenow-incident-mgmt
description: "Manage the native ServiceNow incident lifecycle: read and acknowledge the triggering incident, add discussion entries for the audit trail, and resolve the same record. Uses ServiceNow sys_id semantics and the PowerGrid incident report template."
tools:
  - GetServiceNowIncident
  - AcknowledgeServiceNowIncident
  - PostServiceNowDiscussionEntry
  - ResolveServiceNowIncident
---

# ServiceNow Incident Management

## Overview
This skill manages the ServiceNow incident supplied by native Azure SRE Agent ingestion.
ServiceNow is authoritative for state transitions. Never create a duplicate incident from a response plan.

## When to Use
- An investigation has been triggered by native ServiceNow incident ingestion
- You need to document findings during an investigation
- A remediation has been completed and needs to be recorded
- An incident needs to be resolved with root cause and fix details

## Workflow

### Reading and Acknowledging the Incident
1. Use GetServiceNowIncident with the `sys_id` supplied by the native trigger.
2. Use AcknowledgeServiceNowIncident with the same `sys_id`.
3. Keep the `INC...` number for display and operator communication only.

### Adding Work Notes (Audit Trail)
Use PostServiceNowDiscussionEntry with the same `sys_id` at each investigation phase:
- "Investigating: Querying App Insights for error traces..."
- "Finding: AttributeError in outage-api at line 116, crew_status is None"
- "Correlation: Regression from ADO pipeline run #47 (commit abc123)"
- "Remediation: Rolled back to previous Container App revision"
- "Validation: /outages endpoint returns HTTP 200, service restored"

### Resolving an Incident
Use ResolveServiceNowIncident with:
- incident_id: The native incident `sys_id`
- resolution_notes: Root cause + what was done + permanent fix status

### Refreshing Incident State
Use GetServiceNowIncident to refresh the current state and verify that the response plan
still holds the triggering `sys_id`. Do not look up an incident by its display number to
start a second lifecycle.

## Incident Report Content
Use `knowledge-base/incident-report-template.md` for discussion and resolution
content. Keep the native `sys_id` separate from the human-readable `INC...`
number, and use the `Zava Power SRE` assignment group.
