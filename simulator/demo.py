#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   POWERGRID DEMO SIMULATOR — Zava Power Limited             ║
╚══════════════════════════════════════════════════════════════╝

Story-driven CLI simulator for Azure SRE Agent demos.
Each scenario narrates the business context, triggers real Azure
resources, and monitors the SRE Agent's autonomous response.

Usage:  python simulator/demo.py
"""

import sys, os, time, json, subprocess, threading
from datetime import datetime

# ── Auto-install dependencies ───────────────────────────────
def _ensure_deps():
    missing = []
    for pkg in ("rich", "requests"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing: {', '.join(missing)} ...")
        os.system(f'"{sys.executable}" -m pip install {" ".join(missing)} --quiet')

_ensure_deps()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich import box
import requests

import msvcrt

# ── Configuration ───────────────────────────────────────────
WORKLOAD    = os.environ.get("POWERGRID_WORKLOAD_NAME", "powergrid")
ADO_ORG     = "sreagentlab"
ADO_PROJECT = "zava-pl"
OUTAGE_API_URL = os.environ.get("POWERGRID_OUTAGE_API_URL",
    "https://ca-powergrid-outage.proudmoss-f0b5f310.eastus2.azurecontainerapps.io")
GRID_API_URL = os.environ.get("POWERGRID_GRID_API_URL",
    "https://ca-powergrid-grid.proudmoss-f0b5f310.eastus2.azurecontainerapps.io")
NOTIFY_URL = os.environ.get("POWERGRID_NOTIFY_URL",
    "https://ca-powergrid-notify.proudmoss-f0b5f310.eastus2.azurecontainerapps.io")
PORTAL_URL = os.environ.get("POWERGRID_PORTAL_URL",
    "https://app-powergrid-portal.azurewebsites.net")

console = Console()
RECOVERY_THRESHOLD = 3   # consecutive healthy samples before declaring recovered

# ── Keyboard ────────────────────────────────────────────────
def check_key():
    """Non-blocking keypress check. Returns bytes or None."""
    if msvcrt.kbhit():
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            msvcrt.getch()
            return None
        return ch
    return None

# ── Health checks ───────────────────────────────────────────
def health_check(url, path="/health", timeout=5):
    """Returns (status_code, latency_ms)."""
    try:
        r = requests.get(f"{url}{path}", timeout=timeout)
        return r.status_code, r.elapsed.total_seconds() * 1000
    except Exception:
        return 0, 0

# ── Event Timeline ──────────────────────────────────────────
class EventTimeline:
    def __init__(self):
        self.events = []
        self.start = datetime.now()

    def add(self, text, style="white"):
        self.events.append({
            "ts": datetime.now().strftime("%H:%M:%S"),
            "elapsed": f"+{(datetime.now() - self.start).seconds}s",
            "text": text, "style": style,
        })

    def render(self):
        t = Table(title="[bold]Event Timeline[/]", box=box.ROUNDED,
                  border_style="blue", width=68)
        t.add_column("Time", style="dim", width=9)
        t.add_column("Δ", style="dim", width=6)
        t.add_column("Event", width=48)
        for e in self.events[-6:]:
            t.add_row(e["ts"], e["elapsed"], f"[{e['style']}]{e['text']}[/]")
        return t

# ── Backstory / Result helpers ──────────────────────────────
def _indent(text, prefix="    "):
    return "\n".join(f"{prefix}{line}" for line in text.split("\n"))

def show_backstory(emoji, title, backstory, what_happens):
    """Phase 1: Display the scenario narrative and wait for Enter."""
    console.clear()
    console.print(Panel(
        f"\n  [bold]BACKSTORY:[/]\n{_indent(backstory)}\n\n"
        f"  [bold]WHAT WILL HAPPEN:[/]\n{_indent(what_happens)}\n",
        title=f"[bold]{emoji} {title}[/]",
        border_style="cyan", width=68,
    ))
    console.input("[dim]  Press Enter to start...[/]")

def show_result(emoji, title, lines):
    """Phase 4: Display result summary and wait for Enter."""
    console.print(Panel(
        "\n" + "\n".join(f"  {l}" for l in lines) + "\n",
        title=f"[bold green]{emoji} {title}[/]",
        border_style="green", width=68,
    ))
    console.input("[dim]  Press Enter to return to menu...[/]")

# ── Azure DevOps Pipeline helpers ───────────────────────────
def run_ado_pipeline(name, params=None, branch="main"):
    """Trigger an ADO pipeline. Returns run ID or None."""
    cmd = (f'az pipelines run --name "{name}" --project {ADO_PROJECT} '
           f'--org https://dev.azure.com/{ADO_ORG} --branch {branch}')
    if params:
        ps = " ".join(f'"{k}={v}"' for k, v in params.items())
        cmd += f" --parameters {ps}"
    cmd += " -o json"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout).get("id")
        console.print(f"[red]  ✗ Pipeline returned code {r.returncode}[/]")
    except subprocess.TimeoutExpired:
        console.print("[red]  ✗ Pipeline trigger timed out[/]")
    except Exception as e:
        console.print(f"[red]  ✗ Pipeline error: {e}[/]")
    return None

def poll_pipeline(run_id, label):
    """Poll pipeline until complete. Returns 'succeeded'|'failed'|'canceled'|'quit'."""
    SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    start = time.time()
    last_poll = 0
    status, result = "queued", ""

    with Live(console=console, refresh_per_second=4) as live:
        while True:
            key = check_key()
            if key in (b"q", b"Q"):
                return "quit"

            now = time.time()
            elapsed = int(now - start)

            if now - last_poll >= 10:
                last_poll = now
                try:
                    cmd = (f'az pipelines runs show --id {run_id} '
                           f'--project {ADO_PROJECT} '
                           f'--org https://dev.azure.com/{ADO_ORG} -o json')
                    r = subprocess.run(cmd, shell=True, capture_output=True,
                                       text=True, timeout=15)
                    if r.returncode == 0 and r.stdout.strip():
                        d = json.loads(r.stdout)
                        status = d.get("status", "unknown")
                        result = d.get("result", "")
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass

            s = SPIN[elapsed % len(SPIN)]
            live.update(Panel(
                f"  {s}  [bold]{label}[/]  (Run #{run_id})\n"
                f"     Status: [cyan]{status}[/]   Result: {result or '—'}\n"
                f"     Elapsed: {elapsed}s   [dim]q = abort[/]",
                border_style="cyan", width=64,
            ))

            if status == "completed":
                return result or "unknown"
            time.sleep(0.25)

def run_build_release(failure_scenario, services):
    """Full build → release pipeline flow. Returns True on success."""
    console.print("\n[bold cyan]  ▶ Triggering PowerGrid-Build...[/]")
    build_id = run_ado_pipeline("PowerGrid-Build", {
        "failure_scenario": failure_scenario, "services": services,
    })
    if not build_id:
        console.input("[dim]  Press Enter...[/]"); return False

    console.print(f"[green]  ✓ Build #{build_id} triggered[/]\n")
    r = poll_pipeline(build_id, "PowerGrid-Build")
    if r == "quit": return False
    if r != "succeeded":
        console.print(f"[red]  ✗ Build {r}[/]")
        console.input("[dim]  Press Enter...[/]"); return False

    console.print("[green]  ✓ Build succeeded![/]\n")
    console.print("[bold cyan]  ▶ Triggering PowerGrid-Release...[/]")
    rel_id = run_ado_pipeline("PowerGrid-Release")
    if not rel_id:
        console.input("[dim]  Press Enter...[/]"); return False

    console.print(f"[green]  ✓ Release #{rel_id} triggered[/]\n")
    r = poll_pipeline(rel_id, "PowerGrid-Release")
    if r == "quit": return False
    if r != "succeeded":
        console.print(f"[red]  ✗ Release {r}[/]")
        console.input("[dim]  Press Enter...[/]"); return False

    console.print("[green]  ✓ Release succeeded![/]\n")
    return True

# ── Health Monitoring (Phase 3) ─────────────────────────────
def monitor_health(url, path, service_name, agent_name,
                   healthy_fn=None, ok_label="HEALTHY", bad_label="UNHEALTHY"):
    """Live health monitor. Runs until service recovers or user presses q.
    Recovery requires RECOVERY_THRESHOLD consecutive healthy samples."""
    if healthy_fn is None:
        healthy_fn = lambda code, ms: code == 200

    timeline = EventTimeline()
    timeline.add(f"Monitoring {service_name}", "cyan")
    timeline.add(f"🤖 {agent_name} is investigating...", "yellow")

    checks = []
    had_unhealthy = False
    consecutive_ok = 0
    recovered = False

    with Live(console=console, refresh_per_second=2) as live:
        while not recovered:
            key = check_key()
            if key in (b"q", b"Q"):
                return False

            code, ms = health_check(url, path)
            healthy = healthy_fn(code, ms)
            checks.append({"ts": datetime.now().strftime("%H:%M:%S"),
                           "code": code, "ms": ms, "ok": healthy})
            if len(checks) > 20:
                checks.pop(0)

            if not healthy:
                had_unhealthy = True
                consecutive_ok = 0
            else:
                consecutive_ok += 1

            if healthy and had_unhealthy and consecutive_ok >= RECOVERY_THRESHOLD:
                recovered = True
                timeline.add("🎉 SERVICE RESTORED!", "green bold")

            # ── build display ──
            grid = Table.grid(padding=1)
            grid.add_column()

            if recovered:
                grid.add_row(Panel(
                    "[bold green]🎉🎉🎉  SERVICE RESTORED!  🎉🎉🎉[/]",
                    border_style="green bold", width=64,
                ))

            color = "green" if healthy else "red"
            icon = "✅" if healthy else "❌"
            label = ok_label if healthy else bad_label
            grid.add_row(Text(
                f"  {icon} {service_name}: {label} ({code} / {ms:.0f}ms)",
                style=f"{color} bold"))

            ht = Table(box=box.ROUNDED, border_style="dim", width=64)
            ht.add_column("Time", style="dim", width=9)
            ht.add_column("Status", width=7, justify="center")
            ht.add_column("Latency", width=10, justify="right")
            ht.add_column("Result", width=10, justify="center")
            for c in checks[-8:]:
                sc = "green" if c["ok"] else "red"
                ht.add_row(
                    c["ts"],
                    f"[{sc}]{c['code']}[/]",
                    f"{c['ms']:.0f}ms",
                    f"[green]{ok_label}[/]" if c["ok"] else f"[red]{bad_label}[/]",
                )
            grid.add_row(ht)
            grid.add_row(Text(
                f"  🤖 {agent_name} → sre.azure.com → sre-zavapower-ops",
                style="dim"))
            grid.add_row(timeline.render())
            grid.add_row(Text("  [dim]q = return to menu[/]"))
            live.update(grid)
            time.sleep(2)
    return True

# ═══════════════════════════════════════════════════════════
#  SCENARIO 1 — Bad Deployment: App Crash (SCADA Bug)
# ═══════════════════════════════════════════════════════════
def scenario_crash():
    show_backstory("💥", "BAD DEPLOYMENT — APP CRASH",
        "The grid operations team filed ticket GRID-2847 requesting\n"
        "SCADA cross-referencing on the outage map. A developer\n"
        "implemented the enrichment code — calling .upper() on\n"
        "crew_status to normalize it for the dashboard display.\n\n"
        "The code worked in dev where all test records were complete.\n"
        "But in production, some SCADA records return None for\n"
        "crew_status and cause fields.",

        "1. We trigger the build pipeline with the buggy code\n"
        "2. Build completes → Release deploys to production\n"
        "3. Release trigger fires → deployment-validator agent\n"
        "   PROACTIVELY checks service health\n"
        "4. Agent finds /outages returning 500 (AttributeError)\n"
        "5. Agent investigates → finds NoneType crash in SCADA code\n"
        "6. Agent rolls back → creates fix PR → documents in SNOW")

    if not run_build_release("crash", "outage-api"):
        return
    console.print("[bold yellow]  ⚡ RELEASE TRIGGER FIRED — deployment-validator investigating[/]\n")
    time.sleep(1)

    if monitor_health(OUTAGE_API_URL, "/outages", "outage-api",
                      "deployment-validator"):
        show_result("🎉", "SERVICE RESTORED!", [
            "SRE Agent (deployment-validator):",
            "- Created SNOW ticket INC00XXXXX",
            "- Found AttributeError in _enrich_outage() line 116",
            "- Rolled back to previous revision",
            "- Created fix PR in ADO",
            "",
            "Check sre.azure.com for the full investigation thread.",
            "Check dev268981.service-now.com for the SNOW ticket.",
        ])

# ═══════════════════════════════════════════════════════════
#  SCENARIO 2 — Bad Deployment: Performance Regression
# ═══════════════════════════════════════════════════════════
def scenario_perf():
    show_backstory("🐌", "BAD DEPLOYMENT — PERFORMANCE REGRESSION",
        "Security audit SEC-2847 required SHA-256 checksum validation\n"
        "on all grid telemetry payloads. A developer added the check\n"
        "but implemented it as a synchronous O(n²) loop that computes\n"
        "checksums for every record on every request.\n\n"
        "Unit tests passed (only 5 records). In production, the regions\n"
        "endpoint processes 10,000+ records per call.",

        "1. We trigger the build pipeline with the slow code\n"
        "2. Build completes → Release deploys to production\n"
        "3. Release trigger fires → deployment-validator agent\n"
        "   PROACTIVELY checks service health\n"
        "4. Agent finds /regions taking >5s (was <100ms)\n"
        "5. Agent investigates → finds O(n²) checksum loop\n"
        "6. Agent rolls back → creates fix PR → documents in SNOW")

    if not run_build_release("perf", "grid-status-api"):
        return
    console.print("[bold yellow]  ⚡ RELEASE TRIGGER FIRED — deployment-validator investigating[/]\n")
    time.sleep(1)

    if monitor_health(GRID_API_URL, "/regions", "grid-status-api",
                      "deployment-validator",
                      healthy_fn=lambda c, ms: c == 200 and ms < 1000,
                      ok_label="FAST", bad_label="SLOW"):
        show_result("🎉", "PERFORMANCE RESTORED!", [
            "SRE Agent (deployment-validator):",
            "- Created SNOW ticket INC00XXXXX",
            "- Found O(n²) checksum loop in validate_telemetry()",
            "- Response time: 5200ms → 85ms after rollback",
            "- Rolled back to previous revision",
            "- Created fix PR with batch checksum approach",
            "",
            "Check sre.azure.com for the full investigation thread.",
        ])

# ═══════════════════════════════════════════════════════════
#  SCENARIO 3 — Bad Deployment: Config Error (Wrong Port)
# ═══════════════════════════════════════════════════════════
def scenario_config():
    show_backstory("🔌", "BAD DEPLOYMENT — CONFIG ERROR (WRONG PORT)",
        "INFRA-3291: The networking team migrated the internal gateway\n"
        "from port 8443 to 9443 as part of the TLS 1.3 upgrade. They\n"
        "updated the gateway config and emailed all service owners.\n\n"
        "The notification service config was updated by a junior dev\n"
        "who accidentally set GATEWAY_PORT=9443 in staging but left\n"
        "production pointing to the old port 8443 — now closed.",

        "1. We trigger the build pipeline with the wrong config\n"
        "2. Build completes → Release deploys to production\n"
        "3. Release trigger fires → deployment-validator agent\n"
        "   PROACTIVELY checks service health\n"
        "4. Agent finds /send endpoint timing out (connection refused)\n"
        "5. Agent investigates → finds GATEWAY_PORT mismatch\n"
        "6. Agent rolls back → creates fix PR → documents in SNOW")

    if not run_build_release("config", "notification-svc"):
        return
    console.print("[bold yellow]  ⚡ RELEASE TRIGGER FIRED — deployment-validator investigating[/]\n")
    time.sleep(1)

    if monitor_health(NOTIFY_URL, "/send", "notification-svc",
                      "deployment-validator"):
        show_result("🎉", "SERVICE RESTORED!", [
            "SRE Agent (deployment-validator):",
            "- Created SNOW ticket INC00XXXXX",
            "- Found connection timeout to gateway:8443",
            "- Identified GATEWAY_PORT mismatch (8443 vs 9443)",
            "- Rolled back to previous revision",
            "- Created fix PR updating GATEWAY_PORT=9443",
            "",
            "Check sre.azure.com for the full investigation thread.",
        ])

# ═══════════════════════════════════════════════════════════
#  SCENARIO 4 — Disk Pressure (VM Alert)
# ═══════════════════════════════════════════════════════════
def scenario_disk():
    show_backstory("💾", "DISK PRESSURE — VM ALERT",
        "The grid management server (vm-grid-mgmt-01) runs SCADA data\n"
        "collection and stores raw telemetry locally before forwarding\n"
        "to Azure Data Explorer. Over the past week, a misconfigured\n"
        "log rotation policy let /var/log/scada grow unchecked.\n\n"
        "Combined with nightly SCADA backups that were never pruned,\n"
        "the 128GB OS disk is now at 94% capacity and climbing.",

        "1. We run break-disk.sh to simulate disk pressure on the VM\n"
        "2. Azure Monitor fires a disk-pressure alert\n"
        "3. Alert trigger → vm-ops-agent picks up the alert\n"
        "4. Agent SSHs into the VM and investigates\n"
        "5. Agent cleans old logs and backups, fixes log rotation\n"
        "6. Agent documents remediation in SNOW")

    console.print("[bold cyan]  ▶ Simulating disk pressure...[/]")
    try:
        subprocess.run("bash scripts/break-disk.sh", shell=True, timeout=60)
        console.print("[green]  ✓ Disk pressure injected[/]\n")
    except subprocess.TimeoutExpired:
        console.print("[red]  ✗ Script timed out[/]")
        console.input("[dim]  Press Enter...[/]"); return
    except Exception as e:
        console.print(f"[red]  ✗ Failed: {e}[/]")
        console.input("[dim]  Press Enter...[/]"); return

    console.print("[bold yellow]  ⚡ Azure Monitor alert firing → vm-ops-agent investigating[/]\n")
    console.print("[dim]  🤖 Agent → sre.azure.com → sre-zavapower-ops[/]")
    console.print("[dim]  Waiting for vm-ops-agent to remediate...[/]\n")
    console.input("[dim]  Press Enter when agent has completed...[/]")

    show_result("🎉", "DISK PRESSURE RESOLVED!", [
        "SRE Agent (vm-ops-agent):",
        "- Detected disk at 94% via Azure Monitor alert",
        "- SSHed into vm-grid-mgmt-01",
        "- Cleaned /var/log/scada (recovered 42GB)",
        "- Pruned old SCADA backups (recovered 31GB)",
        "- Fixed logrotate config for scada.log",
        "- Created SNOW ticket with remediation details",
        "",
        "Check sre.azure.com for the full investigation thread.",
    ])

# ═══════════════════════════════════════════════════════════
#  SCENARIO 5 — Organic Load Spike (No Bug)
# ═══════════════════════════════════════════════════════════
def scenario_load():
    show_backstory("📈", "ORGANIC LOAD SPIKE — NO BUG",
        "A major regional grid event (transformer failure in Sector 7)\n"
        "just hit the news. All 2.3 million customers in the affected\n"
        "region are simultaneously checking outage status on the portal.\n\n"
        "There is NO bug — the code is correct. The infrastructure is\n"
        "simply overwhelmed by legitimate traffic at 50x normal volume.",

        "1. We generate a burst of concurrent requests to grid-status-api\n"
        "2. Response times climb as the service saturates\n"
        "3. Azure Monitor fires high-latency alert → incident-handler\n"
        "4. Agent investigates — finds NO code defect\n"
        "5. Agent recommends horizontal scaling + CDN caching\n"
        "6. Agent documents the capacity event in SNOW")

    console.print("[bold cyan]  ▶ Generating load spike (10 concurrent workers)...[/]\n")
    stop_event = threading.Event()

    def worker():
        while not stop_event.is_set():
            try:
                requests.get(f"{GRID_API_URL}/regions", timeout=5)
            except Exception:
                pass
            time.sleep(0.05)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(10)]
    for t in threads:
        t.start()

    timeline = EventTimeline()
    timeline.add("Load spike started — 10 concurrent workers", "cyan")
    timeline.add("🤖 Waiting for Azure Monitor high-latency alert...", "yellow")
    checks = []
    max_iterations = 120  # ~4 min at 2s intervals

    try:
        with Live(console=console, refresh_per_second=2) as live:
            for i in range(max_iterations):
                key = check_key()
                if key in (b"q", b"Q"):
                    break

                code, ms = health_check(GRID_API_URL, "/regions")
                checks.append({"ts": datetime.now().strftime("%H:%M:%S"),
                                "code": code, "ms": ms})
                if len(checks) > 20:
                    checks.pop(0)

                remaining = (max_iterations - i) * 2
                grid = Table.grid(padding=1)
                grid.add_column()

                color = "red" if ms > 2000 else "yellow" if ms > 500 else "green"
                grid.add_row(Text(
                    f"  📈 grid-status-api: {code} / {ms:.0f}ms   "
                    f"[auto-stop in {remaining}s]",
                    style=f"{color} bold"))

                ht = Table(box=box.ROUNDED, border_style="dim", width=64)
                ht.add_column("Time", style="dim", width=9)
                ht.add_column("Status", width=7)
                ht.add_column("Latency", width=10, justify="right")
                for c in checks[-8:]:
                    lc = ("red" if c["ms"] > 2000
                          else "yellow" if c["ms"] > 500 else "green")
                    ht.add_row(c["ts"], str(c["code"]),
                               f"[{lc}]{c['ms']:.0f}ms[/]")
                grid.add_row(ht)
                grid.add_row(Text(
                    "  🤖 incident-handler → sre.azure.com → sre-zavapower-ops",
                    style="dim"))
                grid.add_row(timeline.render())
                grid.add_row(Text("  [dim]q = stop load test[/]"))
                live.update(grid)
                time.sleep(2)
    finally:
        stop_event.set()

    show_result("📈", "LOAD SPIKE ANALYZED", [
        "SRE Agent (incident-handler):",
        "- Detected high-latency alert on grid-status-api",
        "- Investigated recent deployments — none found",
        "- Analyzed code paths — no regressions detected",
        "- Correlated with news event: Sector 7 transformer failure",
        "- VERDICT: No bug — organic traffic spike at 50x volume",
        "",
        "Recommendations:",
        "- Scale grid-status-api to 5 replicas (from 2)",
        "- Enable CDN caching for /regions (TTL 30s)",
        "- Add auto-scale rule at 70% CPU threshold",
        "",
        "Check sre.azure.com for the full analysis.",
    ])

# ═══════════════════════════════════════════════════════════
#  SCENARIO 6 — Pipeline Build Failure
# ═══════════════════════════════════════════════════════════
def scenario_build_failure():
    show_backstory("🔨", "PIPELINE BUILD FAILURE",
        "A developer upgraded Flask from v2.3 to v3.0 to get native\n"
        "async route support. The upgrade looked clean — no deprecation\n"
        "warnings in the changelog for the APIs being used.\n\n"
        "However, Flask 3.0 removed the legacy flask.ext import shim.\n"
        "The outage-api still uses 'from flask.ext.cors import CORS'\n"
        "instead of the modern 'from flask_cors import CORS'.",

        "1. We trigger the build pipeline with the broken imports\n"
        "2. Build FAILS — ImportError at collect time\n"
        "3. Build failure trigger → incident-handler agent\n"
        "4. Agent reads build logs from ADO pipeline\n"
        "5. Agent identifies the flask.ext import error\n"
        "6. Agent creates fix PR and notifies the developer")

    console.print("[bold cyan]  ▶ Triggering PowerGrid-Build (will fail)...[/]")
    build_id = run_ado_pipeline("PowerGrid-Build", {
        "failure_scenario": "build-failure", "services": "outage-api",
    })
    if not build_id:
        console.input("[dim]  Press Enter...[/]"); return

    console.print(f"[green]  ✓ Build #{build_id} triggered[/]\n")
    result = poll_pipeline(build_id, "PowerGrid-Build")
    if result == "quit":
        return

    if result == "failed":
        console.print("[red bold]  ✗ BUILD FAILED — as expected![/]\n")
        console.print("[bold yellow]  ⚡ Build failure trigger fired → incident-handler reading logs[/]\n")
        time.sleep(2)
    else:
        console.print(f"[yellow]  Build result: {result} (expected failure)[/]\n")

    show_result("🔨", "BUILD FAILURE HANDLED", [
        "SRE Agent (incident-handler):",
        "- Detected build failure in PowerGrid-Build pipeline",
        "- Retrieved and analyzed build logs from ADO",
        "- Found: ImportError — flask.ext removed in Flask 3.0",
        "- Root cause: 'from flask.ext.cors import CORS'",
        "- Created fix PR: update to 'from flask_cors import CORS'",
        "- Notified developer via Teams with root cause analysis",
        "",
        "Check sre.azure.com for the investigation thread.",
    ])

# ═══════════════════════════════════════════════════════════
#  SCENARIO 7 — Reset All (Healthy Baseline)
# ═══════════════════════════════════════════════════════════
def scenario_reset():
    console.clear()
    console.print(Panel(
        "\n  Restoring all services to healthy baseline.\n"
        "  This will:\n"
        "  - Run fix-all.sh to reset configurations\n"
        "  - Redeploy healthy container images\n"
        "  - Validate all service health endpoints\n",
        title="[bold]🧹 RESET ALL — HEALTHY BASELINE[/]",
        border_style="cyan", width=68,
    ))
    console.input("[dim]  Press Enter to proceed...[/]")

    console.print("\n[bold cyan]  ▶ Running fix-all.sh...[/]")
    try:
        subprocess.run("bash scripts/fix-all.sh", shell=True, timeout=120)
        console.print("[green]  ✓ fix-all.sh completed[/]\n")
    except subprocess.TimeoutExpired:
        console.print("[yellow]  ⚠ fix-all.sh timed out[/]\n")
    except Exception as e:
        console.print(f"[yellow]  ⚠ fix-all.sh: {e}[/]\n")

    console.print("[bold cyan]  ▶ Validating services...[/]\n")
    services = [
        ("outage-api",       OUTAGE_API_URL),
        ("grid-status-api",  GRID_API_URL),
        ("notification-svc", NOTIFY_URL),
        ("portal",           PORTAL_URL),
    ]
    all_ok = True
    for name, url in services:
        code, ms = health_check(url)
        if code == 200:
            console.print(f"  [green]✅ {name}: {code} ({ms:.0f}ms)[/]")
        else:
            console.print(f"  [red]❌ {name}: {code or 'unreachable'}[/]")
            all_ok = False

    console.print()
    if all_ok:
        console.print("[green bold]  ✅ All services healthy![/]\n")
    else:
        console.print("[yellow]  ⚠ Some services may still be recovering.[/]\n")

    console.input("[dim]  Press Enter to return to menu...[/]")

# ── System Status Panel ─────────────────────────────────────
def _system_status_panel():
    services = [
        ("Outage API",   OUTAGE_API_URL),
        ("Grid Status",  GRID_API_URL),
        ("Notification", NOTIFY_URL),
        ("Portal",       PORTAL_URL),
    ]
    lines = []
    for name, url in services:
        code, ms = health_check(url, timeout=3)
        if code == 200:
            lines.append(f"  {name:<16} [green]● UP[/]   {ms:.0f}ms")
        elif code == 0:
            lines.append(f"  {name:<16} [dim]● N/A[/]")
        else:
            lines.append(f"  {name:<16} [red]● {code}[/]  {ms:.0f}ms")
    return Panel("\n".join(lines), title="[bold]System Status[/]",
                 border_style="dim", width=56)

# ── Menu ────────────────────────────────────────────────────
MENU_ITEMS = """
  [bold cyan]1.[/]  💥  Bad Deployment — App Crash (SCADA Bug)
  [bold cyan]2.[/]  🐌  Bad Deployment — Performance Regression
  [bold cyan]3.[/]  🔌  Bad Deployment — Config Error (Wrong Port)
  [bold cyan]4.[/]  💾  Disk Pressure (VM Alert)
  [bold cyan]5.[/]  📈  Organic Load Spike (No Bug)
  [bold cyan]6.[/]  🔨  Pipeline Build Failure
  [bold cyan]7.[/]  🧹  Reset All (Healthy Baseline)
  [bold cyan]Q.[/]  🚪  Quit
"""

def show_menu():
    console.clear()
    console.print(Panel(
        "[bold white]   POWERGRID DEMO SIMULATOR — Zava Power Limited[/]",
        border_style="bold cyan", width=64,
    ))
    console.print(Panel(MENU_ITEMS, border_style="dim", width=64))
    console.print(_system_status_panel())
    console.print()

# ── Main ────────────────────────────────────────────────────
def main():
    scenarios = {
        "1": scenario_crash,
        "2": scenario_perf,
        "3": scenario_config,
        "4": scenario_disk,
        "5": scenario_load,
        "6": scenario_build_failure,
        "7": scenario_reset,
    }
    while True:
        show_menu()
        choice = console.input(
            "[bold cyan]  Select scenario (1-7, Q): [/]").strip().lower()
        if choice == "q":
            console.print("[bold]  Goodbye! ⚡[/]")
            break
        fn = scenarios.get(choice)
        if fn:
            fn()
        else:
            console.print("[red]  Invalid choice.[/]")
            time.sleep(1)


if __name__ == "__main__":
    main()
