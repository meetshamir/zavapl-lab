#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

show_menu() {
  echo -e "\n\033[1;35m╔══════════════════════════════════════════════════════╗\033[0m"
  echo -e "\033[1;35m║        ⚡ PowerGrid ZeroOps Lab — Scenario Menu      ║\033[0m"
  echo -e "\033[1;35m╚══════════════════════════════════════════════════════╝\033[0m\n"
  echo -e "  \033[1;31mBreak Scenarios:\033[0m"
  echo -e "    \033[1;37m1)\033[0m  Service Outage    — outage-api returns 503"
  echo -e "    \033[1;37m2)\033[0m  Memory Leak       — meter-api leaks memory (OOM)"
  echo -e "    \033[1;37m3)\033[0m  Perf Degradation  — grid-status-api 5s delay"
  echo -e "    \033[1;37m4)\033[0m  Crash Loop        — notification-svc missing config"
  echo -e "    \033[1;37m5)\033[0m  Bad Image          — portal ImagePullBackOff"
  echo -e "    \033[1;37m6)\033[0m  Double Fault      — grid-status-api slow + errors"
  echo ""
  echo -e "  \033[1;32mRecovery:\033[0m"
  echo -e "    \033[1;37m7)\033[0m  Fix All           — restore all services to healthy state"
  echo ""
  echo -e "  \033[1;36mOther:\033[0m"
  echo -e "    \033[1;37m0)\033[0m  Quit"
  echo ""
}

while true; do
  show_menu
  read -p "$(echo -e '\033[1;33mSelect a scenario [0-7]: \033[0m')" choice

  case "$choice" in
    1) bash "$SCRIPT_DIR/break-service.sh" ;;
    2) bash "$SCRIPT_DIR/break-memleak.sh" ;;
    3) bash "$SCRIPT_DIR/break-perf.sh" ;;
    4) bash "$SCRIPT_DIR/break-crash.sh" ;;
    5) bash "$SCRIPT_DIR/break-image.sh" ;;
    6) bash "$SCRIPT_DIR/break-config.sh" ;;
    7) bash "$SCRIPT_DIR/fix-all.sh" ;;
    0)
      echo -e "\n\033[1;36mGoodbye! 👋\033[0m\n"
      exit 0
      ;;
    *)
      echo -e "\n\033[1;31m✘ Invalid selection. Please enter 0-7.\033[0m"
      ;;
  esac

  echo ""
  read -p "$(echo -e '\033[1;33mPress Enter to continue...\033[0m')"
done
