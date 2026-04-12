# SRE Agent Configuration Guide

## Overview

This lab uses `srectl` (SRE Agent CLI) to apply agents, tools, skills, and
knowledge base documents to the SRE Agent. `srectl` is currently available
to Microsoft internal users and will be publicly released soon.

> **Note for external users:** Until `srectl` is publicly available, you can
> configure agents, tools, and skills manually through the SRE Agent portal
> at [sre.azure.com](https://sre.azure.com). See the "Manual Setup" section below.

---

## Setup with srectl

### 1. Initialize srectl

```bash
# Get your agent's endpoint URL from the Azure portal
AGENT_URL=$(az rest --method GET \
  --url "https://management.azure.com/subscriptions/<SUB_ID>/resourceGroups/rg-powergrid/providers/Microsoft.App/agents/sre-powergrid?api-version=2025-05-01-preview" \
  --query "properties.agentEndpoint" -o tsv)

# Initialize srectl pointing to your agent
srectl init --resource-url $AGENT_URL
```

### 2. Apply Tools (ServiceNow integration)

```bash
srectl apply --file sre-config/tools/CreateServiceNowIncident/CreateServiceNowIncident.yaml
srectl apply --file sre-config/tools/UpdateServiceNowWorkNotes/UpdateServiceNowWorkNotes.yaml
srectl apply --file sre-config/tools/ResolveServiceNowIncident/ResolveServiceNowIncident.yaml
srectl apply --file sre-config/tools/LookupServiceNowIncident/LookupServiceNowIncident.yaml
```

### 3. Apply Agents (subagents with investigation instructions)

```bash
srectl apply --file sre-config/agents/incident-handler.yaml
srectl apply --file sre-config/agents/servicenow-handler.yaml
srectl apply --file sre-config/agents/utility-ops-agent.yaml
```

### 4. Apply Skills (troubleshooting procedures)

```bash
srectl skill apply --name outage-api-diagnosis
srectl skill apply --name meter-api-diagnosis
srectl skill apply --name grid-status-diagnosis
srectl skill apply --name notification-svc-diagnosis
srectl skill apply --name deployment-rollback
```

### 5. Upload Knowledge Base (reference documents)

```bash
srectl doc upload --file knowledge-base/powergrid-architecture.md
srectl doc upload --file knowledge-base/incident-report-template.md
```

### 6. Verify

```bash
srectl status
# Should show: 3 agents, 4 tools, 5 skills
```

---

## Manual Setup (via sre.azure.com portal)

If `srectl` is not available, configure everything through the portal:

### Tools

1. Go to sre.azure.com → select your agent → **Builder → Tools**
2. Click **+ Add tool → Python**
3. For each tool YAML file in `sre-config/tools/`, copy the `functionCode`,
   `description`, `parameters`, and `dependencies` into the portal form
4. Repeat for all 4 ServiceNow tools

### Agents (Subagents)

1. Go to **Builder → Agents → + Create agent**
2. For each agent YAML in `sre-config/agents/`, copy the `name`,
   `instructions`, and select the tools from the tools list
3. Repeat for all 3 agents

### Skills

1. Go to **Builder → Skills → + Create skill**
2. For each skill in `skills/`, copy the `SKILL.md` content
3. Assign the appropriate tools
4. Repeat for all 5 skills

### Knowledge Base

1. Go to **Builder → Knowledge → + Upload document**
2. Upload `knowledge-base/powergrid-architecture.md`
3. Upload `knowledge-base/incident-report-template.md`

### Response Plan

1. Go to **Builder → Incidents → Response plans → + Create**
2. Name: `auto-investigate`
3. Agent: `incident-handler`
4. Trigger: Azure Monitor alerts

---

## What Gets Configured

| Type | Count | Names |
|------|-------|-------|
| **Tools** | 4 | CreateServiceNowIncident, UpdateServiceNowWorkNotes, ResolveServiceNowIncident, LookupServiceNowIncident |
| **Agents** | 3 | incident-handler, servicenow-handler, utility-ops-agent |
| **Skills** | 5 | outage-api-diagnosis, meter-api-diagnosis, grid-status-diagnosis, notification-svc-diagnosis, deployment-rollback |
| **Knowledge** | 2 | powergrid-architecture.md, incident-report-template.md |
