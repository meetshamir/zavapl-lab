<!-- Badges — replace ORG/REPO with your GitHub path -->
[![Deploy to Azure](https://img.shields.io/badge/Deploy%20to-Azure-0078D4?logo=microsoftazure)](https://portal.azure.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![SRE Agent](https://img.shields.io/badge/Azure%20SRE%20Agent-Powered-blue?logo=microsoftazure)](https://sre.azure.com)

# PowerGrid ZeroOps Lab ⚡🤖

**An end-to-end Azure SRE Agent lab for utility-scale incident response — break PowerGrid services, watch the agent diagnose and fix them autonomously.**

Built for the Zava Power ZeroOps initiative. Deploy a realistic power-utility microservices platform, inject failures, and experience AI-driven SRE in action.

---

## What This Lab Demonstrates

| Scenario | What Happens |
|:---------|:-------------|
| **🔍 Autonomous Investigation** | Azure Monitor fires an alert → SRE Agent investigates logs, correlates metrics, references runbooks, and identifies root cause — all without human intervention |
| **🔧 Automated Remediation** | Agent executes the fix (restart container, rollback config, scale replicas) and validates recovery |
| **📋 ServiceNow Integration** | Agent creates an incident ticket, updates it throughout investigation, and resolves it with root-cause documentation |
| **📊 Proactive Health Monitoring** | Scheduled health checks run every 30 minutes — agent detects degradation before alerts fire |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Azure Resource Group                            │
│                                                                         │
│  ┌──────────────── Azure Container Apps Environment ──────────────────┐ │
│  │                                                                     │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │ │
│  │  │ portal   │ │ outage   │ │ meter    │ │ grid     │ │ notify   │ │ │
│  │  │ -web     │ │ -api     │ │ -api     │ │ -status  │ │ -svc     │ │ │
│  │  │ (JS)     │ │ (Python) │ │ (.NET)   │ │ (Node)   │ │ (Go)     │ │ │
│  │  └─────┬────┘ └─────┬────┘ └─────┬────┘ └─────┬────┘ └─────┬────┘ │ │
│  └────────│─────────────│────────────│────────────│────────────│──────┘ │
│           │             │            │            │            │        │
│           └─────────────┼────────────┼────────────┼────────────┘        │
│                         ▼            ▼            ▼                     │
│               ┌─────────────────────────────────────┐                   │
│               │      Observability Stack            │                   │
│               │  Log Analytics  ·  App Insights     │                   │
│               │  Managed Grafana                    │                   │
│               └──────────────┬──────────────────────┘                   │
│                              │                                          │
│                              ▼                                          │
│               ┌──────────────────────────┐                              │
│               │   Azure Monitor Alerts   │                              │
│               │  • HTTP 5xx errors       │                              │
│               │  • High response time    │                              │
│               │  • Container restarts    │                              │
│               └────────────┬─────────────┘                              │
│                            │ auto-investigate                           │
│                            ▼ response plan                              │
│               ┌──────────────────────────┐      ┌────────────────────┐  │
│               │    Azure SRE Agent 🤖    │─────▶│  Knowledge Base    │  │
│               │  • incident-handler      │      │  • Runbooks        │  │
│               │  • servicenow-handler    │      │  • Architecture    │  │
│               │  • utility-ops-agent     │      │  • Templates       │  │
│               └─────┬──────────┬─────────┘      └────────────────────┘  │
│                     │          │                                         │
└─────────────────────│──────────│─────────────────────────────────────────┘
                      │          │
          ┌───────────┘          └───────────┐
          ▼                                  ▼
┌──────────────────┐              ┌──────────────────┐
│   ServiceNow     │              │ Datadog/Dynatrace│
│   (optional)     │              │   (optional)     │
└──────────────────┘              └──────────────────┘
```

---

## What Gets Deployed

| Resource | Purpose |
|:---------|:--------|
| **SRE Agent** | AI agent with managed identity, knowledge base, custom agents, and response plan |
| **PowerGrid Services** | 5 microservices (portal-web, outage-api, meter-api, grid-status-api, notification-svc) on Container Apps |
| **Log Analytics Workspace** | Central log storage — KQL queries for diagnostics |
| **Application Insights** | Request telemetry, error tracking, and performance monitoring |
| **Managed Grafana** | Dashboards for real-time service observability |
| **Azure Monitor Alerts** | 5xx errors, high latency, container restarts → auto-triggers agent |
| **Container Registry** | PowerGrid container images |
| **Managed Identity** | Reader + Monitoring Reader + Log Analytics Reader + Container App Contributor RBAC |

### SRE Agent Configuration

| Component | File | Purpose |
|:----------|:-----|:--------|
| **incident-handler** | `sre-config/agents/incident-handler.yaml` | Investigates incidents using logs, KQL, and runbooks |
| **servicenow-handler** | `sre-config/agents/servicenow-handler.yaml` | Manages ServiceNow incident lifecycle |
| **utility-ops-agent** | `sre-config/agents/utility-ops-agent.yaml` | Scheduled health checks and grid status reports |
| **Response Plan** | `sre-config/response-plans/auto-investigate.yaml` | Routes Azure Monitor alerts to incident-handler |
| **Health Check** | `sre-config/scheduled-tasks/health-check.yaml` | Runs utility-ops-agent every 30 minutes |
| **ServiceNow MCP** | `sre-config/connectors/servicenow-mcp.yaml` | Optional ServiceNow connector template |
| **Datadog MCP** | `sre-config/connectors/datadog-mcp.yaml` | Optional Datadog connector template |
| **Dynatrace MCP** | `sre-config/connectors/dynatrace-mcp.yaml` | Optional Dynatrace connector template |
| **Global Tools** | Built-in | Azure Monitor, Log Analytics, App Insights, DevOps |

---

## Lab Scenarios

| # | Scenario | Break Type | What SRE Agent Does | Persona |
|:-:|:---------|:-----------|:--------------------|:--------|
| 1 | **Service Outage** | outage-api returns HTTP 503 | Queries logs, finds crash, restarts container | IT Operations |
| 2 | **Memory Leak** | meter-api OOM kill | Detects OOM in container logs, scales replicas, recommends fix | IT Operations |
| 3 | **Deploy Regression** | grid-status-api slow responses (>3s) | Correlates latency spike with deployment, identifies bad config | Developer |
| 4 | **Container Crash Loop** | notification-svc CrashLoopBackOff | Finds missing env var, applies config fix | IT Operations |
| 5 | **Alert-Driven Auto-Fix** | Same as #1 with response plan | Alert fires → agent investigates and remediates autonomously | ZeroOps |
| 6 | **ServiceNow Lifecycle** | Any break + ServiceNow connector | Creates INC, updates with findings, resolves with RCA | ITSM |
| 7 | **Source Code Analysis** | Any break + GitHub connected | Finds root cause in source code, creates GitHub issue | Developer |
| 8 | **Combined Chaos** | All services break simultaneously | Agent triages by severity, handles in parallel | Stress Test |

---

## Prerequisites

| Tool | macOS | Windows |
|:-----|:------|:--------|
| [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.60+ | `brew install azure-cli` | `winget install Microsoft.AzureCLI` |
| [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) 1.9+ | `brew install azd` | `winget install Microsoft.Azd` |
| [Git](https://git-scm.com/) 2.x | `brew install git` | `winget install Git.Git` |
| [Python](https://python.org) 3.10+ | `brew install python3` | `winget install Python.Python.3.12` |

> **Windows:** After installing Python, disable Store aliases: **Settings → Apps → App execution aliases** → turn OFF `python.exe` and `python3.exe`

### Azure Requirements

- Active Azure subscription with **Owner** role
- Register required providers:
  ```bash
  az provider register -n Microsoft.App --wait
  az provider register -n Microsoft.Dashboard --wait
  ```

### Optional

- [GitHub account](https://github.com) — fork this repo for Scenario 7 (source code analysis)
- [ServiceNow Developer Instance](https://developer.servicenow.com) — free, for Scenario 6

---

## Quick Start

### One-Command Setup (Recommended)

**macOS / Linux:**
```bash
git clone https://github.com/<ORG>/zava-power-zeroops-lab.git
cd zava-power-zeroops-lab
bash scripts/setup.sh
```

**Windows (Git Bash):**
```cmd
git clone https://github.com/<ORG>/zava-power-zeroops-lab.git
cd zava-power-zeroops-lab
"C:\Program Files\Git\bin\bash.exe" scripts/setup.sh
```

The setup script will:
1. ✅ Check prerequisites (az, azd, git, python)
2. 🔐 Sign in to Azure and Azure Developer CLI
3. 📦 Register resource providers
4. 🏗️ Deploy infrastructure (~8-12 min)
5. 🤖 Print SRE Agent connection instructions

### Manual Setup

```bash
az login --use-device-code
azd auth login --use-device-code
az provider register -n Microsoft.App --wait

azd env new powergrid-lab
azd env set AZURE_LOCATION eastus2
# Optional: azd env set GITHUB_USER <your-username>
azd up

bash scripts/post-provision.sh
```

### Verify Deployment

Open [sre.azure.com](https://sre.azure.com) → **Full Setup** → verify:
- **Azure resources**: resource group `rg-powergrid` visible
- **Incidents**: Azure Monitor connected
- **Knowledge sources**: runbook files indexed

---

## Breaking Things 💥

Use the CLI simulator to inject failures into PowerGrid services:

```bash
python simulator/demo.py
```

Or apply breaks individually:

| Scenario | Break Command | What Breaks |
|:---------|:-------------|:------------|
| Service Outage | `python simulator/demo.py --scenario 1` | outage-api returns 503 on all endpoints |
| Memory Leak | `python simulator/demo.py --scenario 2` | meter-api consumes memory until OOM killed |
| Deploy Regression | `python simulator/demo.py --scenario 3` | grid-status-api response times exceed 3 seconds |
| Container Crash | `python simulator/demo.py --scenario 4` | notification-svc enters CrashLoopBackOff |
| Combined Chaos | `python simulator/demo.py --scenario 6` | All services break simultaneously |
| Reset All | `python simulator/demo.py --scenario 7` | Restore all services to healthy baseline |

---

## Using SRE Agent

### Connect to Your Agent

1. Open [sre.azure.com](https://sre.azure.com)
2. Select your agent (created during deployment)
3. Navigate to **Builder** to configure agents, response plans, and scheduled tasks
4. Start a **New chat** to interact with the agent

### Sample Prompts

**Investigate an Outage:**
```
The outage-api is returning 503 errors. Can you investigate the issue,
find the root cause, and remediate?
```

**Run a Health Check:**
```
Run a full health check across all PowerGrid services and give me
a status report.
```

**Diagnose Latency:**
```
The grid-status-api is responding slowly. Check App Insights for latency
trends over the last hour and identify what changed.
```

**Container Diagnostics:**
```
The notification service keeps crashing. Query ContainerAppConsoleLogs
for crash reasons and propose a fix.
```

**KQL Deep Dive:**
```
Using the http-errors runbook, walk me through all the diagnostic KQL
queries and show me the results for the PowerGrid services.
```

**Resource Overview:**
```
What container apps are running in my resource group? Show me their
current replica counts and resource utilization.
```

### Automated Investigation

After breaking a service, the Azure Monitor alert will fire within **5-10 minutes**. If the response plan is configured:

1. Alert fires → response plan matches rule name
2. incident-handler agent is invoked automatically
3. Agent investigates, applies fix, validates recovery
4. Check **Activities → Incidents** in the SRE Agent portal to see the full investigation log

---

## Optional Integrations

### ServiceNow

Connect SRE Agent to ServiceNow for automated incident ticket management.

1. Create a free [ServiceNow Developer Instance](https://developer.servicenow.com)
2. Copy `sre-config/connectors/servicenow-mcp.yaml` and fill in your instance URL and credentials
3. Add the connector in **Builder → Connectors** in the SRE Agent portal
4. The servicenow-handler agent will automatically create and manage incidents

### Datadog

Bring in Datadog metrics and monitors alongside Azure-native observability.

1. Generate API and Application keys in your Datadog account
2. Reference `sre-config/connectors/datadog-mcp.yaml` for the connection template
3. Add the connector in **Builder → Connectors**

### Dynatrace

Connect Dynatrace for full-stack observability and AI-powered problem detection.

1. Create a platform access token with `metrics.read`, `logs.read`, `problems.read`, `entities.read` scopes
2. Reference `sre-config/connectors/dynatrace-mcp.yaml` for the connection template
3. Add the connector in **Builder → Connectors**

---

## CLI Simulator

The interactive CLI simulator (`simulator/demo.py`) provides a rich terminal experience for demonstrating SRE Agent capabilities without touching the Azure portal.

```bash
python simulator/demo.py
```

Features:
- 🎯 **Scenario selection** — choose which service to break
- 📊 **Live dashboards** — simulated metrics and log streams
- 🔄 **Reset capability** — restore all services to healthy state
- 🎭 **ServiceNow demo** — walk through the incident lifecycle
- ⚡ **Combined chaos** — break everything at once

The simulator injects real failures into your deployed Container Apps and displays simulated telemetry for demonstration purposes.

---

## Cost Estimate

> Estimates based on East US 2 pricing. Actual costs vary by usage.

| Resource | ACA Deployment | AKS Deployment |
|:---------|:---------------|:---------------|
| Container Apps (5 services) | ~$3/day | — |
| AKS Cluster (3-node B2s) | — | ~$7/day |
| Log Analytics (PerGB, ~1 GB/day) | ~$2.50/day | ~$2.50/day |
| Application Insights | Included with LA | Included with LA |
| Managed Grafana (Standard) | ~$2.70/day | ~$2.70/day |
| Container Registry (Basic) | ~$0.17/day | ~$0.17/day |
| SRE Agent | Preview pricing | Preview pricing |
| **Estimated Total** | **~$8-9/day (~$250/mo)** | **~$12-13/day (~$375/mo)** |

> 💡 **Tip:** This lab defaults to **Azure Container Apps** (ACA) for lower cost. Set `computePlatform=aks` in the Bicep parameters to deploy on AKS instead.

---

## Cleanup

Remove all deployed resources:

```bash
azd down --purge
```

This deletes the resource group and all resources within it, including soft-deleted resources (Key Vault, App Insights, etc.).

To clean up only the SRE Agent configuration, visit [sre.azure.com](https://sre.azure.com) → **Settings** → **Delete agent**.

---

## Troubleshooting

| Issue | Fix |
|:------|:----|
| `python` not found (Windows) | Disable Store aliases in Settings → Apps → App execution aliases, then reopen terminal |
| `azd up` times out | Check Azure subscription quotas; try a different region with `azd env set AZURE_LOCATION westus2` |
| Alert response plan not triggering | Wait 10-15 min for Azure Monitor evaluation; verify plan is linked in Builder → Response Plans |
| SRE Agent can't query logs | Verify managed identity RBAC: Reader + Monitoring Reader + Log Analytics Reader on the resource group |
| Container apps stuck in provisioning | Run `az containerapp list -g rg-powergrid -o table` to check status; retry `azd up` if needed |
| ServiceNow connector fails | Verify instance URL includes `https://` prefix; check credentials are correct; ensure instance is awake (dev instances sleep) |
| Grafana shows no data | It takes 5-10 min for Managed Grafana to ingest initial data; check Monitoring Reader role assignment |
| `setup.sh` fails on Windows | Use Git Bash: `"C:\Program Files\Git\bin\bash.exe" scripts/setup.sh` — do not use PowerShell or CMD directly |

---

## Resources

| Resource | Link |
|:---------|:-----|
| **SRE Agent Portal** | [sre.azure.com](https://sre.azure.com) |
| **SRE Agent Documentation** | [sre.azure.com/docs](https://sre.azure.com/docs) |
| **SRE Agent Blog** | [aka.ms/sreagent/blog](https://aka.ms/sreagent/blog) |
| **SRE Agent Labs** | [aka.ms/sreagent/lab](https://aka.ms/sreagent/lab) |
| **SRE Agent Pricing** | [aka.ms/sreagent/pricing](https://aka.ms/sreagent/pricing) |
| **GitHub (SRE Agent)** | [aka.ms/sreagent/github](https://aka.ms/sreagent/github) |
| **Azure Container Apps Docs** | [learn.microsoft.com/azure/container-apps](https://learn.microsoft.com/azure/container-apps/) |
| **Azure Monitor Docs** | [learn.microsoft.com/azure/azure-monitor](https://learn.microsoft.com/azure/azure-monitor/) |

---

<p align="center">
  Built with ⚡ by Zava Power · Powered by <a href="https://sre.azure.com">Azure SRE Agent</a>
</p>
