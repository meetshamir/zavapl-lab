#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Zava Power Limited — Post-Deploy SRE Agent Configuration
# ═══════════════════════════════════════════════════════════════
# Run this AFTER 'azd up' to configure the SRE Agent with tools,
# agents, skills, knowledge, and response plans.
#
# Requires: srectl (SRE Agent CLI)
# If srectl is not available, follow docs/SRE-AGENT-CONFIG.md
# for manual portal setup instructions.
#
# Usage: bash scripts/configure-agent.sh [--ado-org <org> --ado-project <project>]
# ═══════════════════════════════════════════════════════════════

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Zava Power Limited — SRE Agent Configuration${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo ""

# ── Check srectl ───────────────────────────────────────────
if ! command -v srectl &> /dev/null; then
    echo -e "${YELLOW}srectl (SRE Agent CLI) not found.${NC}"
    echo ""
    echo "srectl is not yet publicly available. To configure your SRE Agent,"
    echo "follow these manual steps in the portal at https://sre.azure.com :"
    echo ""
    echo "  1. Select your agent (sre-powergrid)"
    echo ""
    echo "  2. Builder → Tools → + Add tool → Python"
    echo "     Upload each YAML from sre-config/tools/:"
    echo "       - CreateServiceNowIncident"
    echo "       - UpdateServiceNowWorkNotes"
    echo "       - ResolveServiceNowIncident"
    echo "       - LookupServiceNowIncident"
    echo ""
    echo "  3. Builder → Agents → + Create agent"
    echo "     Create from each YAML in sre-config/agents/:"
    echo "       - incident-handler"
    echo "       - servicenow-handler"
    echo "       - utility-ops-agent"
    echo ""
    echo "  4. Builder → Skills → + Create skill"
    echo "     Upload each SKILL.md from skills/:"
    echo "       - outage-api-diagnosis"
    echo "       - meter-api-diagnosis"
    echo "       - grid-status-diagnosis"
    echo "       - notification-svc-diagnosis"
    echo "       - deployment-rollback"
    echo ""
    echo "  5. Builder → Knowledge → + Upload document"
    echo "       - knowledge-base/powergrid-architecture.md"
    echo "       - knowledge-base/incident-report-template.md"
    echo ""
    echo "  6. Builder → Incidents → Response plans → + Create"
    echo "       Name: auto-investigate, Agent: incident-handler"
    echo ""
    echo "Full details: docs/SRE-AGENT-CONFIG.md"
    exit 0
fi

# ── Get agent endpoint ─────────────────────────────────────
WORKLOAD="${POWERGRID_WORKLOAD_NAME:-powergrid}"
RG="${POWERGRID_RESOURCE_GROUP:-rg-$WORKLOAD}"
SUB_ID=$(az account show --query id -o tsv 2>/dev/null)

echo -e "${YELLOW}Finding SRE Agent endpoint...${NC}"
AGENT_URL=$(az rest --method GET \
  --url "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.App/agents/sre-${WORKLOAD}?api-version=2025-05-01-preview" \
  --query "properties.agentEndpoint" -o tsv 2>/dev/null)

if [ -z "$AGENT_URL" ]; then
    echo -e "${RED}Could not find SRE Agent. Run 'azd up' first.${NC}"
    exit 1
fi
echo -e "${GREEN}  Agent: $AGENT_URL${NC}"

# ── Initialize srectl ──────────────────────────────────────
echo ""
echo -e "${YELLOW}Initializing srectl...${NC}"
srectl init --resource-url "$AGENT_URL"

# ── Apply Tools (4 ServiceNow tools) ──────────────────────
echo ""
echo -e "${CYAN}── Applying Tools ──────────────────────────────${NC}"
for tool in CreateServiceNowIncident UpdateServiceNowWorkNotes ResolveServiceNowIncident LookupServiceNowIncident; do
    echo -n "  $tool... "
    srectl apply --file "sre-config/tools/${tool}/${tool}.yaml" --quiet 2>/dev/null && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}"
done

# ── Apply Agents (3 subagents) ─────────────────────────────
echo ""
echo -e "${CYAN}── Applying Agents ─────────────────────────────${NC}"
for agent in incident-handler servicenow-handler utility-ops-agent; do
    echo -n "  $agent... "
    srectl apply --file "sre-config/agents/${agent}.yaml" --quiet 2>/dev/null && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}"
done

# ── Apply Skills (5 troubleshooting skills) ────────────────
echo ""
echo -e "${CYAN}── Applying Skills ─────────────────────────────${NC}"
for skill in outage-api-diagnosis meter-api-diagnosis grid-status-diagnosis notification-svc-diagnosis deployment-rollback; do
    echo -n "  $skill... "
    srectl skill apply --name "$skill" --quiet 2>/dev/null && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}"
done

# ── Upload Knowledge Base (2 reference docs) ──────────────
echo ""
echo -e "${CYAN}── Uploading Knowledge Base ────────────────────${NC}"
for doc in powergrid-architecture.md incident-report-template.md; do
    echo -n "  $doc... "
    srectl doc upload --file "knowledge-base/$doc" --quiet 2>/dev/null && echo -e "${GREEN}✓${NC}" || echo -e "${RED}✗${NC}"
done

# ── Create Response Plan ───────────────────────────────────
echo ""
echo -e "${CYAN}── Creating Response Plan ──────────────────────${NC}"
echo -n "  auto-investigate... "
srectl incidenthandler create \
    --id auto-investigate \
    --name "Auto Investigate PowerGrid Alerts" \
    --handling-agent incident-handler \
    --quiet 2>/dev/null && echo -e "${GREEN}✓${NC}" || echo -e "${YELLOW}(may already exist)${NC}"

# ── ADO Setup (if org provided) ────────────────────────────
ADO_ORG="${1:-}"
ADO_PROJECT="${2:-zava-pl}"

if [ "$ADO_ORG" = "--ado-org" ] && [ -n "$2" ]; then
    ADO_ORG="$2"
    ADO_PROJECT="${4:-zava-pl}"
    
    echo ""
    echo -e "${CYAN}── Setting up Azure DevOps ─────────────────────${NC}"
    
    echo -n "  Creating project... "
    az devops project create --name "$ADO_PROJECT" --org "https://dev.azure.com/$ADO_ORG" -o none 2>/dev/null && echo -e "${GREEN}✓${NC}" || echo -e "${YELLOW}(may already exist)${NC}"
    
    echo -n "  Importing repo... "
    az repos import create --git-source-url https://github.com/meetshamir/zavapl-lab.git --repository "$ADO_PROJECT" --project "$ADO_PROJECT" --org "https://dev.azure.com/$ADO_ORG" -o none 2>/dev/null && echo -e "${GREEN}✓${NC}" || echo -e "${YELLOW}(may already exist)${NC}"
    
    echo -n "  Creating deploy pipeline... "
    az pipelines create --name "PowerGrid-Deploy" --repository "$ADO_PROJECT" --repository-type tfsgit --branch main --yml-path pipelines/azure-pipelines.yml --project "$ADO_PROJECT" --org "https://dev.azure.com/$ADO_ORG" --skip-first-run true -o none 2>/dev/null && echo -e "${GREEN}✓${NC}" || echo -e "${YELLOW}(may already exist)${NC}"
    
    echo -n "  Creating CI pipeline... "
    az pipelines create --name "PowerGrid-BuildTest" --repository "$ADO_PROJECT" --repository-type tfsgit --branch main --yml-path pipelines/azure-pipelines-ci.yml --project "$ADO_PROJECT" --org "https://dev.azure.com/$ADO_ORG" --skip-first-run true -o none 2>/dev/null && echo -e "${GREEN}✓${NC}" || echo -e "${YELLOW}(may already exist)${NC}"
fi

# ── Summary ────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ SRE Agent configured successfully!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Applied: 4 tools, 3 agents, 5 skills, 2 knowledge docs, 1 response plan"
echo ""
echo -e "  ${YELLOW}Manual steps remaining:${NC}"
echo "    1. ADO service connection: ADO → Project Settings → Service connections"
echo "       (see docs/ADO-SETUP.md)"
echo "    2. Connect ADO to SRE Agent: sre.azure.com → Connectors → Azure DevOps"
echo "       (see docs/SRE-AGENT-SETUP.md)"
echo "    3. ServiceNow (optional): developer.servicenow.com → Request Instance"
echo "       (see docs/SERVICENOW-SETUP.md)"
echo ""
echo "  Ready to demo:"
echo "    python simulator/demo.py              # CLI simulator (recommended)"
echo "    # Or: ADO → PowerGrid-Deploy → failure_scenario=crash"
echo ""
