# SRE Agent Setup Guide

## Overview

The lab deploys an SRE Agent resource (`sre-powergrid`) via Bicep as part of
`azd up`. This guide covers what gets deployed and what you need to configure
manually in the portal afterward.

---

## What Bicep Deploys Automatically

| Resource | Name | What It Does |
|---|---|---|
| SRE Agent | `sre-powergrid` | The AI agent resource (`Microsoft.App/agents`) |
| User-Assigned MI | `id-powergrid-sre` | Managed Identity the agent uses for Azure access |
| RBAC: Reader | on `rg-powergrid` | Agent can read all resources |
| RBAC: Monitoring Reader | on `rg-powergrid` | Agent can query Azure Monitor |
| RBAC: Log Analytics Reader | on `rg-powergrid` | Agent can run KQL queries |
| RBAC: Website Contributor | on `rg-powergrid` | Agent can manage Container Apps + App Service |
| SRE Agent Administrator | on agent | Your deploying user gets admin access |

After `azd up`, the agent exists but needs portal configuration.

---

## Step 1: Access Your Agent

1. Go to https://sre.azure.com
2. You should see `sre-powergrid` in your agents list
3. If not, check that you're signed in with the same account that ran the deployment

> **Supported regions:** East US 2, Sweden Central, Australia East.
> The Bicep defaults to East US 2.

## Step 2: Connect Azure Resources

1. Click on `sre-powergrid`
2. Go to **Full Setup** (left panel) → **Azure resources**
3. Click **+ Add resource group**
4. Select `rg-powergrid`
5. This lets the agent query App Insights, Log Analytics, and manage Container Apps

## Step 3: Connect Azure DevOps (for release management)

1. Go to **Builder → Connectors → + Add connector**
2. Select **Azure DevOps**
3. Organization: your ADO org name (e.g., `sreagentlab`)
4. Project: `zava-pl`
5. Click **Authorize** (OAuth flow)

This enables pipeline discovery, deployment correlation, build investigation,
and fix PR creation.

## Step 4: Apply Tools, Agents, Skills, and Knowledge

### With srectl (if available):
```bash
# See docs/SRE-AGENT-CONFIG.md for full commands
srectl init --resource-url <your-agent-endpoint>
# Apply 4 tools, 3 agents, 5 skills, 2 knowledge docs
```

### Without srectl (manual portal setup):
See the "Manual Setup" section in `docs/SRE-AGENT-CONFIG.md`.

## Step 5: Create a Response Plan

Response plans auto-trigger the agent when Azure Monitor alerts fire.

1. Go to **Builder → Incidents → Response plans**
2. Click **+ Create response plan**
3. Name: `auto-investigate`
4. Agent: `incident-handler`
5. Trigger source: **Azure Monitor**
6. Alert filter: match alerts from `rg-powergrid`
7. Mode: **Review** (agent proposes actions, you approve)
   - Or **Autonomous** for the "wake up at 9 AM" demo
8. Save

## Step 6: Verify Everything

Open a new chat and try:

```
What Azure resources are in my resource group?
```

The agent should list all your Container Apps, App Service, VM, etc.

Then try:

```
Check the health of all PowerGrid services.
```

If the agent queries your services and reports their status, everything is wired up.

---

## Creating the Agent Without Bicep

If you're setting up from scratch without the Bicep templates:

### Option A: Portal
1. Go to https://portal.azure.com
2. Search for **Azure SRE Agent** → **Create**
3. Resource group: `rg-powergrid`
4. Name: `sre-powergrid`
5. Region: East US 2
6. Create

### Option B: Azure CLI
```bash
# Register the provider (one-time)
az provider register -n Microsoft.App --wait

# Create managed identity
az identity create -g rg-powergrid -n id-powergrid-sre

# Get identity details
IDENTITY_ID=$(az identity show -g rg-powergrid -n id-powergrid-sre --query id -o tsv)
IDENTITY_PRINCIPAL=$(az identity show -g rg-powergrid -n id-powergrid-sre --query principalId -o tsv)

# Assign RBAC roles
az role assignment create --assignee $IDENTITY_PRINCIPAL --role "Reader" --scope /subscriptions/<SUB_ID>/resourceGroups/rg-powergrid
az role assignment create --assignee $IDENTITY_PRINCIPAL --role "Monitoring Reader" --scope /subscriptions/<SUB_ID>/resourceGroups/rg-powergrid
az role assignment create --assignee $IDENTITY_PRINCIPAL --role "Log Analytics Reader" --scope /subscriptions/<SUB_ID>/resourceGroups/rg-powergrid
```

### Option C: Bicep (included in this lab)
```bash
az deployment sub create \
  --location eastus2 \
  --template-file infra/main.bicep \
  --parameters location=eastus2 computePlatform=aca
```

---

## Firewall Requirements

If your network has egress restrictions, allow:
- `*.azuresre.ai` — SRE Agent communication
- `sre.azure.com` — Portal access
- `*.service-now.com` — ServiceNow integration (if using SNOW)
