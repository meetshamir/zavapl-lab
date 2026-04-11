#!/bin/bash
set -euo pipefail

echo -e "\n\033[1;35m╔══════════════════════════════════════════════════════╗\033[0m"
echo -e "\033[1;35m║        ⚡ PowerGrid ZeroOps Lab — Setup              ║\033[0m"
echo -e "\033[1;35m╚══════════════════════════════════════════════════════╝\033[0m\n"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Check prerequisites ──────────────────────────────────────────────
echo -e "\033[1;36m▸ Checking prerequisites...\033[0m\n"

MISSING=()
command -v az    >/dev/null 2>&1 || MISSING+=("az (Azure CLI)")
command -v azd   >/dev/null 2>&1 || MISSING+=("azd (Azure Developer CLI)")
command -v git   >/dev/null 2>&1 || MISSING+=("git")
command -v python3 >/dev/null 2>&1 || {
  command -v python >/dev/null 2>&1 || MISSING+=("python3")
}

if [ ${#MISSING[@]} -ne 0 ]; then
  echo -e "\033[1;31m✘ Missing required tools:\033[0m"
  for tool in "${MISSING[@]}"; do
    echo -e "    - $tool"
  done
  echo -e "\nPlease install the missing tools and re-run this script."
  exit 1
fi

echo -e "  \033[1;32m✔ az\033[0m    $(az version --output tsv 2>/dev/null | head -1)"
echo -e "  \033[1;32m✔ azd\033[0m   $(azd version 2>/dev/null | head -1)"
echo -e "  \033[1;32m✔ git\033[0m   $(git --version)"
echo -e "  \033[1;32m✔ python\033[0m $(python3 --version 2>/dev/null || python --version 2>/dev/null)"

# ── Authenticate ─────────────────────────────────────────────────────
echo -e "\n\033[1;36m▸ Authenticating with Azure...\033[0m\n"

echo -e "  Logging in to Azure CLI (device code flow)..."
az login --use-device-code

echo -e "\n  Logging in to Azure Developer CLI (device code flow)..."
azd auth login --use-device-code

# ── Register providers ───────────────────────────────────────────────
echo -e "\n\033[1;36m▸ Registering required Azure resource providers...\033[0m\n"

echo -e "  Registering Microsoft.App..."
az provider register -n Microsoft.App --wait
echo -e "  \033[1;32m✔ Microsoft.App registered\033[0m"

# ── Optional GitHub user ─────────────────────────────────────────────
echo ""
read -p "$(echo -e '\033[1;33mEnter your GitHub username (optional, press Enter to skip): \033[0m')" GITHUB_USER

if [ -n "$GITHUB_USER" ]; then
  echo -e "  Setting GITHUB_USER=${GITHUB_USER}"
fi

# ── Initialize azd environment ───────────────────────────────────────
echo -e "\n\033[1;36m▸ Initializing azd environment...\033[0m\n"

cd "$PROJECT_DIR"

azd env new powergrid-lab
azd env set AZURE_LOCATION eastus2

if [ -n "${GITHUB_USER:-}" ]; then
  azd env set GITHUB_USER "$GITHUB_USER"
fi

# ── Deploy ────────────────────────────────────────────────────────────
echo -e "\n\033[1;36m▸ Deploying infrastructure and services with azd up...\033[0m\n"
echo -e "  This may take 10-15 minutes.\n"

azd up

# ── Post-provision ────────────────────────────────────────────────────
echo -e "\n\033[1;36m▸ Running post-provision configuration...\033[0m\n"

if [ -f "$SCRIPT_DIR/post-provision.sh" ]; then
  bash "$SCRIPT_DIR/post-provision.sh"
fi

# ── Success ───────────────────────────────────────────────────────────
echo -e "\n\033[1;32m╔══════════════════════════════════════════════════════╗\033[0m"
echo -e "\033[1;32m║   ✔ PowerGrid ZeroOps Lab — Setup Complete!          ║\033[0m"
echo -e "\033[1;32m╚══════════════════════════════════════════════════════╝\033[0m\n"

echo -e "  \033[1;36mAzure Portal:\033[0m  https://portal.azure.com"
echo -e "  \033[1;36mSRE Agent:\033[0m     https://sre.azure.com"
echo -e ""
echo -e "  Run \033[1;33mbash scripts/menu.sh\033[0m to inject failures and test SRE Agent."
echo -e ""
