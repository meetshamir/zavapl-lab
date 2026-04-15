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
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Azure Resource Group                               │
│                                                                             │
│  ┌──────────── Azure Container Apps ───────────┐  ┌──────────────────────┐ │
│  │                                              │  │  Azure App Service   │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐     │  │  ┌────────────────┐  │ │
│  │  │ outage   │ │ meter    │ │ notify   │     │  │  │  portal-web    │  │ │
│  │  │ -api     │ │ -api     │ │ -svc     │     │  │  │  (React)       │  │ │
│  │  │ (Python) │ │ (.NET)   │ │ (Go)     │     │  │  └────────────────┘  │ │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘     │  └──────────────────────┘ │
│  │       │             │            │            │                           │
│  │  ┌────┴─────────────┴────────────┴─────┐     │  ┌──────────────────────┐ │
│  │  │       grid-status-api (Node)        │     │  │  Azure VM (Windows)  │ │
│  │  │       + /chaos endpoints            │     │  │  vm-powergrid-arc    │ │
│  │  └─────────────────────────────────────┘     │  │  (Arc-enabled)       │ │
│  └──────────────────────────────────────────────┘  └──────────────────────┘ │
│           │             │            │            │            │             │
│           └─────────────┼────────────┼────────────┼────────────┘             │
│                         ▼            ▼            ▼                          │
│               ┌─────────────────────────────────────┐                       │
│               │       Observability Stack           │                       │
│               │  Log Analytics  ·  App Insights     │                       │
│               │  Managed Grafana · Azure Monitor    │                       │
│               └──────────────┬──────────────────────┘                       │
│                              │                                               │
│         ┌────────────────────┼────────────────────┐                          │
│         ▼                    ▼                    ▼                          │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐               │
│  │ Az Monitor  │  │  HTTP Triggers   │  │ Release Triggers │               │
│  │ Alerts      │  │  (Synthetic /    │  │ (ADO Pipelines)  │               │
│  │ • Disk      │  │   3rd Party)     │  │ • BuildSucceeded │               │
│  │ • 5xx       │  │                  │  │ • BuildFailed    │               │
│  └──────┬──────┘  └────────┬─────────┘  └────────┬─────────┘               │
│         │                  │                      │                          │
│         └──────────────────┼──────────────────────┘                          │
│                            ▼                                                 │
│     ┌──────────────────────────────────────────────┐                        │
│     │          Azure SRE Agent 🤖                  │                        │
│     │                                              │                        │
│     │  sre-zavapower-ops:                          │    ┌────────────────┐  │
│     │   • incident-handler (alerts + triggers)     │───▶│ Knowledge Base │  │
│     │   • deployment-validator (post-deploy)        │    │ • Runbooks     │  │
│     │   • vm-ops-agent (disk/VM alerts)             │    │ • Architecture │  │
│     │   • utility-ops-agent (health checks)         │    │ • 7 Skills     │  │
│     │                                              │    └────────────────┘  │
│     │  sre-zavapower-itsupport:                    │                        │
│     │   • it-support-handler (SNOW tickets)         │                        │
│     └────┬────────────────┬────────────────┬───────┘                        │
│          │                │                │                                 │
└──────────│────────────────│────────────────│─────────────────────────────────┘
           │                │                │
           ▼                ▼                ▼
┌────────────────┐ ┌────────────────┐ ┌──────────────────────────────────────┐
│  ServiceNow    │ │  Azure DevOps  │ │  3rd Party Observability (optional) │
│  • Incidents   │ │  • Pipelines   │ │                                      │
│  • Work Notes  │ │  • Releases    │ │  Datadog ──┐                         │
│  • Resolution  │ │  • Fix PRs     │ │  Dynatrace ┼─▶ HTTP Trigger ──▶ SRE │
│                │ │                │ │  Splunk ───┘     Agent               │
└────────────────┘ └────────────────┘ └──────────────────────────────────────┘
```

---

## What Gets Deployed

| Resource | Purpose |
|:---------|:--------|
| **SRE Agents (×2)** | sre-zavapower-ops (infra/deploy) + sre-zavapower-itsupport (IT helpdesk) |
| **Container Apps (×4)** | outage-api (Python), meter-api (.NET), grid-status-api (Node), notification-svc (Go) |
| **App Service** | portal-web (React) — customer-facing power grid dashboard |
| **Azure VM** | vm-powergrid-arc — Windows Server 2022, simulates Arc-enabled on-prem grid server |
| **Log Analytics** | Central log + metric storage — KQL queries for diagnostics |
| **Application Insights** | Request telemetry, error tracking, performance monitoring (SDK in all services) |
| **Managed Grafana** | Dashboards for real-time service observability |
| **Azure Monitor Alerts** | Disk pressure (log-based), high latency (metric), HTTP 5xx (metric) |
| **Container Registry** | PowerGrid container images (5 services) |
| **ADO Pipelines** | Build (CI) + Release (CD) with bug injection and deployment validation |
| **Managed Identity** | Reader + Monitoring Reader + Log Analytics Reader + Container App Contributor RBAC |

### SRE Agent Configuration

| Component | Purpose |
|:----------|:--------|
| **incident-handler** | Investigates Azure Monitor alerts + HTTP triggers — logs, KQL, App Insights, scales infra |
| **deployment-validator** | Post-deploy health checks — triggered by ADO Release BuildSucceeded |
| **vm-ops-agent** | VM infrastructure alerts — disk pressure, CPU, memory on Arc-enabled VMs |
| **utility-ops-agent** | Scheduled health checks and grid status reports |
| **it-support-handler** | IT helpdesk — processes ServiceNow laptop tickets (on sre-zavapower-itsupport) |
| **HTTP Trigger** | Accepts synthetic monitoring + 3rd party alerts (Datadog, Dynatrace, Splunk) |
| **Release Triggers** | ADO pipeline events → deployment-validator (success) / incident-handler (failure) |
| **Incident Filters** | Routes Azure Monitor alerts by title to the right agent |
| **7 Skills** | Dynamic diagnostic runbooks for each service + SNOW + deployment rollback |
| **4 SNOW Tools** | Create, update, resolve, lookup ServiceNow incidents via REST API |

---

## Lab Scenarios

| # | Scenario | Trigger Type | What SRE Agent Does |
|:-:|:---------|:-------------|:--------------------|
| 1 | **Bad Deploy — App Crash** | ADO Release → deployment-validator | Detects SCADA bug crash, rolls back revision, creates fix PR |
| 2 | **Bad Deploy — Perf Regression** | ADO Release → deployment-validator | Finds 50K sync hashes blocking event loop, rolls back |
| 3 | **Bad Deploy — Config Error** | ADO Release → deployment-validator | Identifies wrong gateway port (9443→8443), fixes config |
| 4 | **Disk Pressure (VM)** | Azure Monitor → vm-ops-agent | Detects disk at 97%, cleans SCADA logs, documents in SNOW |
| 5 | **Organic Load Spike** | HTTP Trigger → incident-handler | Analyzes traffic patterns, checks grid events, scales replicas + CPU |
| 6 | **Pipeline Build Failure** | ADO Build Failed → incident-handler | Reads build logs, finds flask.ext import error, creates fix PR |
| 7 | **ServiceNow Laptop Replace** | SNOW Incident → it-support-handler | Checks warranty, fills laptop form, resolves ticket, emails user |
| 8 | **Reset All** | Manual | Restores all services to healthy baseline |

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

The simulator presents 8 scenarios, each launched in a separate terminal window with live monitoring:

| # | Scenario | Command | What Happens |
|:-:|:---------|:--------|:-------------|
| 1 | Bad Deploy — App Crash | `--scenario 1` | ADO pipeline deploys SCADA bug → outage-api crashes on `crew_status.upper()` |
| 2 | Bad Deploy — Perf Regression | `--scenario 2` | ADO pipeline deploys 50K sync SHA-256 hashes → grid-status-api blocks |
| 3 | Bad Deploy — Config Error | `--scenario 3` | ADO pipeline deploys wrong gateway port (9443→8443) → notification-svc timeouts |
| 4 | Disk Pressure (VM) | `--scenario 4` | Creates ~22GB SCADA data on C: drive → Azure Monitor log alert fires |
| 5 | Organic Load Spike | `--scenario 5` | 100 concurrent clients flood grid-status-api → HTTP trigger fires SRE Agent |
| 6 | Pipeline Build Failure | `--scenario 6` | Triggers ADO build with broken flask.ext imports → build fails |
| 7 | ServiceNow Laptop Replace | `--scenario 7` | Creates SNOW incident → SRE Agent checks warranty, fills form, resolves |
| 8 | Reset All | `--scenario 8` | Restores all services to healthy baseline |

### How Triggers Work

The lab uses three trigger types to invoke the SRE Agent:

```
┌─────────────────────────┐
│   Azure Monitor Alerts  │──▶ Incident Filters ──▶ vm-ops-agent (disk)
│   (disk pressure, 5xx)  │                    ──▶ incident-handler (other)
└─────────────────────────┘

┌─────────────────────────┐
│   ADO Release Triggers  │──▶ BuildSucceeded ──▶ deployment-validator
│   (pipeline events)     │──▶ BuildFailed   ──▶ incident-handler
└─────────────────────────┘

┌─────────────────────────┐
│   HTTP Triggers         │──▶ Synthetic monitor (simulator)
│   (REST API endpoint)   │──▶ 3rd party: Datadog, Dynatrace, Splunk
└─────────────────────────┘

┌─────────────────────────┐
│   ServiceNow Incidents  │──▶ Native polling ──▶ it-support-handler
│   (SNOW platform)       │     (every 60s)       (on sre-zavapower-itsupport)
└─────────────────────────┘
```

| Trigger | Scenarios | Agent | How It Works |
|:--------|:----------|:------|:-------------|
| **Azure Monitor** | 4 (disk) | vm-ops-agent | Log-based alert fires when C: < 15% free → incident filter routes by title |
| **ADO Release** | 1, 2, 3 | deployment-validator | BuildSucceeded on Release pipeline → validates health post-deploy |
| **ADO Build** | 6 | incident-handler | BuildFailed on Build pipeline → reads logs, identifies error, creates fix PR |
| **HTTP Trigger** | 5 (load) | incident-handler | Simulator detects high latency → POSTs to trigger URL → agent investigates autonomously |
| **ServiceNow** | 7 | it-support-handler | Incident created in SNOW → agent polls, picks up ticket, processes it |

> **3rd Party Integration:** Any external system (Datadog, Dynatrace, Splunk, PagerDuty) can POST to the HTTP trigger URL to invoke the SRE Agent. The payload just needs `service`, `endpoint`, `observedLatencyMs`, and `thresholdMs`. The agent's instructions handle all the investigation logic.

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

Depending on the scenario, the SRE Agent is triggered automatically:

- **Scenarios 1-3 (Bad Deployments):** ADO release pipeline completes → release trigger fires → deployment-validator checks health → if broken, investigates and rolls back
- **Scenario 4 (Disk Pressure):** Azure Monitor log alert fires within ~5 min → incident filter routes to vm-ops-agent → cleans up files, documents in SNOW
- **Scenario 5 (Load Spike):** Simulator detects sustained high latency → fires HTTP trigger → incident-handler analyzes traffic, checks grid events, scales infrastructure
- **Scenario 6 (Build Failure):** ADO build fails → build failure trigger fires → incident-handler reads logs, creates fix PR
- **Scenario 7 (SNOW):** Incident created in ServiceNow → sre-zavapower-itsupport polls every 60s → it-support-handler processes the ticket end-to-end

Check **sre.azure.com → Activities** to see live investigation threads.

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
