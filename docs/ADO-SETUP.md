# Azure DevOps Setup Guide

## Overview

This lab uses Azure DevOps for CI/CD pipelines that SRE Agent can discover,
investigate, and interact with (pipeline correlation, fix PRs, build triggers).

You'll create your own ADO project and import the repo from GitHub.

---

## Step 1: Create an ADO Organization (if you don't have one)

1. Go to https://dev.azure.com
2. Sign in with your Azure account
3. If prompted, create a new organization (e.g., `my-zavapl-lab`)

## Step 2: Create a Project

```bash
# Option A: CLI
az devops configure --defaults organization=https://dev.azure.com/<YOUR_ORG>
az devops project create --name zava-pl --description "Zava Power Limited — ZeroOps SRE Agent Demo"

# Option B: Portal
# Go to dev.azure.com/<YOUR_ORG> → + New project → Name: zava-pl
```

## Step 3: Import the GitHub Repo

```bash
az repos import create \
  --git-source-url https://github.com/meetshamir/zavapl-lab.git \
  --repository zava-pl \
  --project zava-pl
```

Or in the portal:
1. Go to Repos → Import a repository
2. Source URL: `https://github.com/meetshamir/zavapl-lab.git`
3. Click Import

## Step 4: Create the Azure Service Connection

The pipelines need access to your Azure subscription to build images and deploy.

```bash
# This creates a service connection using workload identity federation (no secrets)
# You may need a ServiceTree ID if on a Microsoft corp tenant
```

1. Go to **Project Settings → Service connections → New service connection**
2. Select **Azure Resource Manager → App registration (automatic)**
3. Credential: **Workload identity federation**
4. Subscription: select your subscription
5. Resource group: `rg-powergrid`
6. Service connection name: **`zava-pl-azure`** (must match exactly)
7. If prompted for Service Management Reference, enter your ServiceTree ID
8. Check **Grant access to all pipelines**
9. Save

> **Microsoft Corp Tenant Note:** If you get a ServiceManagementReference error,
> you need a ServiceTree ID. Find yours at https://servicetree.msftcloudes.com
> or ask your team lead. This is a corp tenant requirement, not an Azure/ADO issue.

## Step 5: Create the Pipelines

```bash
# Deploy pipeline (builds and deploys services, has failure_scenario parameter)
az pipelines create \
  --name "PowerGrid-Deploy" \
  --repository zava-pl \
  --repository-type tfsgit \
  --branch main \
  --yml-path pipelines/azure-pipelines.yml \
  --project zava-pl \
  --skip-first-run true

# CI pipeline (runs on PRs, validates fix before merge)
az pipelines create \
  --name "PowerGrid-BuildTest" \
  --repository zava-pl \
  --repository-type tfsgit \
  --branch main \
  --yml-path pipelines/azure-pipelines-ci.yml \
  --project zava-pl \
  --skip-first-run true
```

## Step 6: Connect SRE Agent to ADO

1. Go to sre.azure.com → select your agent
2. **Builder → Connectors → + Add connector → Azure DevOps**
3. Organization: `<YOUR_ORG>`
4. Project: `zava-pl`
5. Authorize with OAuth

This enables:
- `DiscoverPipelines` — agent finds your pipelines
- `GetPipelineRunHistory` — agent correlates deployments with incidents
- `InvestigateBuildFailure` — agent reads pipeline logs
- `CreateFixPullRequest` — agent creates fix PRs in your ADO repo
- `TriggerBuildPipelineRun` — agent can re-run the CI pipeline after a fix

---

## Running the Bad Deployment Demo

### Trigger a failure:
1. Go to ADO → Pipelines → **PowerGrid-Deploy** → **Run pipeline**
2. Set `failure_scenario` to one of: `crash`, `perf`, `config`, `all`
3. Click **Run**

### What happens:
| Scenario | What the pipeline does | What breaks |
|---|---|---|
| `crash` | Builds outage-api from `bugs/crash/app.py` | `/outages` throws AttributeError (NoneType) |
| `perf` | Builds grid-status-api from `bugs/perf/server.js` | `/regions` takes 3-5s (sync crypto loop) |
| `config` | Builds notification-svc from `bugs/config/main.go` | `/send` times out (wrong gateway port) |
| `all` | All three above | Multi-service outage |

### End-to-end flow:
```
Pipeline deploys buggy code → Service fails →
Azure Monitor alert fires → SRE Agent investigates →
Agent correlates with ADO pipeline run →
Agent creates fix PR in ADO →
PR triggers CI pipeline → Tests pass →
Merge → Clean deploy → Services healthy
```

---

## Quick Reference

| Resource | CLI Command |
|---|---|
| List projects | `az devops project list` |
| List pipelines | `az pipelines list --project zava-pl` |
| Run pipeline | `az pipelines run --name PowerGrid-Deploy --parameters "failure_scenario=crash"` |
| List runs | `az pipelines runs list --pipeline-id 2 --top 5` |
| Show run | `az pipelines runs show --id <run-id>` |
