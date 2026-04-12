# ServiceNow Integration Guide

## Overview

This guide connects Azure SRE Agent to ServiceNow so the agent can **create,
update, and resolve** incidents with a complete audit trail during investigations.

### Architecture

```
Azure Monitor Alert fires
    ↓
SRE Agent Response Plan triggers investigation
    ↓
Agent investigates (App Insights, KQL, ADO pipeline correlation)
    ↓
Agent calls ServiceNow MCP tools:
    ├─ create_incident   → INC0010042 created
    ├─ add_work_notes    → RCA documented
    ├─ add_work_notes    → Remediation steps logged
    └─ resolve_incident  → Ticket closed with resolution
```

> **Why MCP, not Incident Platform?**
> The Incident Platform connector is *inbound only* — SNOW → Agent.
> MCP gives the agent *outbound* tools to CREATE and UPDATE tickets.
> Use Azure Monitor alerts to trigger, ServiceNow MCP to document.

---

## Step 1: Get a ServiceNow Developer Instance (Free)

1. Go to https://developer.servicenow.com
2. Sign up / log in
3. Click **Request Instance** (takes ~2 minutes)
4. Note your:
   - Instance URL: `https://dev12345.service-now.com`
   - Admin username: `admin`
   - Admin password: (shown on the instance page)

> Dev instances sleep after 10 days of inactivity. Wake them from the
> developer portal. They're free and fully functional.

---

## Step 2: Configure the MCP Connector in SRE Agent

### Option A: ServiceNow Native MCP (if available)

Some ServiceNow instances have a built-in MCP endpoint:

1. In your ServiceNow instance:
   - Navigate to **System Web Services → MCP Server**
   - Enable the MCP gateway
   - Note the endpoint: `https://<instance>.service-now.com/api/sn_mcp/mcp`

2. In SRE Agent portal (sre.azure.com):
   - Select agent `sre-powergrid`
   - **Builder → Connectors → + Add connector**
   - Choose **MCP Server (User provided connector)**
   - Connection type: **Streamable-HTTP**
   - Name: `servicenow-mcp`
   - URL: `https://<instance>.service-now.com/api/sn_mcp/mcp`
   - Auth: **Basic** (admin / your-password)
   - Click **Next → Add**

### Option B: Community MCP Server (recommended for dev instances)

Use the open-source `servicenow-mcp-server` from PyPI:

```bash
# Install
pip install servicenow-mcp-server

# Run (local or deploy to Azure Container Apps)
export SERVICENOW_INSTANCE_URL="https://dev12345.service-now.com"
export SERVICENOW_USERNAME="admin"
export SERVICENOW_PASSWORD="your-password"
python -m mcp_server_servicenow.cli --port 8090
```

Then in SRE Agent:
- URL: `https://your-deployed-server/mcp` (or localhost for testing)
- Auth: None (if server handles SNOW auth internally)

### Option C: Custom Python Tool

Add a Python tool directly to your SRE Agent subagent:

```python
import requests

SNOW_URL = "https://dev12345.service-now.com"
SNOW_AUTH = ("admin", "your-password")

def create_incident(short_description, description, urgency="2", impact="2"):
    """Create a ServiceNow incident and return the incident number."""
    r = requests.post(
        f"{SNOW_URL}/api/now/table/incident",
        auth=SNOW_AUTH,
        json={
            "short_description": short_description,
            "description": description,
            "urgency": urgency,
            "impact": impact,
            "assignment_group": "SRE Agent",
        },
    )
    data = r.json()["result"]
    return f"Created {data['number']} (sys_id: {data['sys_id']})"

def add_work_note(incident_number, note):
    """Add a work note to an existing incident."""
    # First, get sys_id from incident number
    r = requests.get(
        f"{SNOW_URL}/api/now/table/incident",
        auth=SNOW_AUTH,
        params={"sysparm_query": f"number={incident_number}", "sysparm_limit": 1},
    )
    sys_id = r.json()["result"][0]["sys_id"]

    # Update with work note
    requests.patch(
        f"{SNOW_URL}/api/now/table/incident/{sys_id}",
        auth=SNOW_AUTH,
        json={"work_notes": note},
    )
    return f"Work note added to {incident_number}"

def resolve_incident(incident_number, resolution_notes):
    """Resolve an incident with resolution notes."""
    r = requests.get(
        f"{SNOW_URL}/api/now/table/incident",
        auth=SNOW_AUTH,
        params={"sysparm_query": f"number={incident_number}", "sysparm_limit": 1},
    )
    sys_id = r.json()["result"][0]["sys_id"]

    requests.patch(
        f"{SNOW_URL}/api/now/table/incident/{sys_id}",
        auth=SNOW_AUTH,
        json={
            "state": "6",  # Resolved
            "close_code": "Solved (Permanently)",
            "close_notes": resolution_notes,
            "work_notes": f"Resolved by SRE Agent: {resolution_notes}",
        },
    )
    return f"Incident {incident_number} resolved"
```

Upload this as a Python tool in SRE Agent:
**Builder → Tools → + Add tool → Python**

---

## Step 3: Select Tools

After adding the connector, click **Edit** on it and enable these tools:

| Tool | Purpose |
|------|---------|
| `create_incident` | Agent creates ticket when it detects an issue |
| `get_incident` | Agent reads incident details |
| `update_incident` | Agent updates ticket fields |
| `add_work_notes` | Agent documents investigation steps (audit trail) |
| `resolve_incident` | Agent closes ticket after fix is validated |
| `search_incidents` | Agent checks for existing related incidents |

---

## Step 4: Configure the Subagent Instructions

Update the `incident-handler` subagent to use ServiceNow tools.
Add these instructions:

```
When investigating an incident:
1. FIRST: Create a ServiceNow incident using create_incident with:
   - short_description: Brief summary of the issue
   - description: Alert details and initial observations
   - urgency: 2 (High) for service-affecting issues
   - impact: 2 (High) for customer-facing services

2. DURING investigation: Add work notes at each step using add_work_notes:
   - What you're checking (e.g., "Querying App Insights for error traces")
   - What you found (e.g., "AttributeError in outage-api at line 116")
   - Correlation findings (e.g., "Regression from ADO pipeline run #47")

3. AFTER remediation: Update the incident:
   - Add work note with remediation action taken
   - Add work note with validation results
   - If fix PR was created, note the PR number

4. WHEN validated: Resolve the incident using resolve_incident with:
   - Resolution notes: Root cause + what was done + permanent fix status
```

---

## Step 5: Test the Integration

In the SRE Agent chat, try:

```
Create a test incident in ServiceNow with short description
"Test — SRE Agent ServiceNow Integration" and description
"This is a test incident created by Azure SRE Agent to verify
the ServiceNow MCP connector is working correctly."
```

Then:
```
Add a work note to the incident you just created saying
"Integration test successful. Agent can create and update tickets."
```

Then:
```
Resolve the test incident with resolution notes
"Test complete. ServiceNow MCP integration verified."
```

Check your ServiceNow instance — you should see the full incident lifecycle.

---

## Demo Flow: Bad Deployment → Full SNOW Audit Trail

```
You:    "Run the PowerGrid-Deploy pipeline with failure_scenario=crash"

        [Pipeline runs, deploys buggy outage-api]
        [Azure Monitor 5xx alert fires]
        [Response Plan triggers SRE Agent]

Agent:  Creates INC0010042 in ServiceNow
        "outage-api returning HTTP 500 errors — Azure Monitor alert"

Agent:  Work note: "Investigating. Querying App Insights for error traces
        in the last 15 minutes..."

Agent:  Work note: "Root cause identified. AttributeError in
        src/outage-api/app.py line 116: _enrich_outage() calls
        crew_status.upper() but crew_status is None for outages
        OUT-1003 and OUT-1006 (incomplete SCADA data)."

Agent:  Work note: "Correlated with ADO pipeline PowerGrid-Deploy
        run #47 (commit ba21548). Change: 'Refactored outage enrichment
        with SCADA cross-reference' introduced the regression."

Agent:  Work note: "Remediation: Rolled back ca-powergrid-outage to
        previous Container App revision. /outages now returns HTTP 200."

Agent:  Work note: "Fix PR #4 created in Azure DevOps: 'Add null safety
        to SCADA enrichment'. Adds null checks for crew_status and cause
        fields before calling .upper()."

Agent:  Resolves INC0010042
        "Null reference regression in v1.4.0 SCADA enrichment code.
        Immediate fix: revision rollback. Permanent fix: PR #4 pending
        CI validation and merge. MTTR: 2 minutes (automated)."
```

---

## NERC CIP Compliance Notes

The ServiceNow ticket serves as the audit artifact:

| NERC CIP Standard | What the SNOW Ticket Provides |
|---|---|
| CIP-007 (System Security) | Patch/config change documented with timestamp |
| CIP-008 (Incident Reporting) | Full incident lifecycle with RCA |
| CIP-010 (Change Management) | Pipeline run ID, commit SHA, what changed |

All work notes are timestamped and attributable to `SRE Agent`.
