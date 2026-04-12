#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   POWERGRID DEMO SIMULATOR — Zava Power ZeroOps SRE Agent Lab      ║
╚══════════════════════════════════════════════════════════════╝

A rich CLI simulator for demonstrating Azure SRE Agent
capabilities in the Zava Power ZeroOps lab environment.

Scenarios:
  1. Service Outage        — outage-api returns 503
  2. Memory Leak           — meter-api OOM
  3. Deploy Regression     — grid-status-api slow responses
  4. Container Crash       — notification-svc CrashLoopBackOff
  5. ServiceNow Demo       — Incident lifecycle
  6. Simulate All          — Launch scenarios 1-4 simultaneously
  7. Reset All             — Restore healthy baseline
  Q. Quit

Usage:
  python simulator/demo.py
"""

import sys
import os
import time
import json
import random
import subprocess
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
        print("Done.\n")

_ensure_deps()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.align import Align
from rich import box
import requests as req

if sys.platform == "win32":
    import msvcrt

# ── Config (override with env vars or azd env) ─────────────
WORKLOAD = os.environ.get("POWERGRID_WORKLOAD_NAME", "powergrid")

PORTAL_URL     = os.environ.get("POWERGRID_PORTAL_URL",     "")
OUTAGE_API_URL = os.environ.get("POWERGRID_OUTAGE_API_URL",  "")
METER_API_URL  = os.environ.get("POWERGRID_METER_API_URL",   "")
GRID_API_URL   = os.environ.get("POWERGRID_GRID_API_URL",    "")
NOTIFY_URL     = os.environ.get("POWERGRID_NOTIFY_URL",      "")

SN_URL  = os.environ.get("POWERGRID_SN_URL",  "")
SN_USER = os.environ.get("POWERGRID_SN_USER", "admin")
SN_PASS = os.environ.get("POWERGRID_SN_PASS", "")

SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
RESOURCE_GROUP  = os.environ.get("POWERGRID_RESOURCE_GROUP", f"rg-{WORKLOAD}")

console = Console()

# ── Helpers ─────────────────────────────────────────────────

def check_key():
    """Non-blocking keypress check (Windows)."""
    if sys.platform != "win32":
        return None
    if msvcrt.kbhit():
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            msvcrt.getch()
            return None
        try:
            return ch.decode("utf-8").lower()
        except Exception:
            return None
    return None


def _wait_key():
    """Block until any key is pressed."""
    if sys.platform == "win32":
        msvcrt.getch()
    else:
        input()


def health_check(url, timeout=5):
    """Poll a /health endpoint. Returns (status_code, latency_ms, body)."""
    if not url:
        return 0, 0, "URL not configured"
    try:
        r = req.get(f"{url}/health", timeout=timeout)
        return r.status_code, r.elapsed.total_seconds() * 1000, r.text[:200]
    except Exception as e:
        return 0, 0, str(e)[:200]


def _color_status(code):
    if code == 200:
        return "green"
    if code == 503:
        return "red"
    return "yellow"


def _color_ms(ms):
    if ms < 100:
        return "green"
    if ms < 500:
        return "yellow"
    return "red"


def _bar(ms, max_ms=5000, width=30):
    filled = min(int((ms / max(max_ms, 1)) * width), width)
    c = _color_ms(ms)
    return f"[{c}]{'█' * filled}{'░' * (width - filled)}[/]"


def _status_icon(code):
    if code == 200:
        return "[green]● UP[/]"
    if code == 503:
        return "[red]● DOWN[/]"
    if code == 0:
        return "[dim]● N/A[/]"
    return f"[yellow]● {code}[/]"


def _check_alert_fired(alert_name_contains=None):
    """Check Azure Monitor alert status via az CLI."""
    if not SUBSCRIPTION_ID:
        return None, None
    try:
        result = subprocess.run(
            f'az rest --method GET --url "https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}/providers/Microsoft.AlertsManagement/alerts?api-version=2019-03-01&targetResourceGroup={RESOURCE_GROUP}" -o json',
            capture_output=True, text=True, timeout=20, shell=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            for alert in data.get("value", []):
                props = alert.get("properties", {}).get("essentials", {})
                rule = props.get("alertRule", "")
                condition = props.get("monitorCondition", "")
                if alert_name_contains and alert_name_contains not in rule:
                    continue
                if condition in ("Fired", "Resolved"):
                    return condition, props.get("startDateTime", "")
        return None, None
    except Exception:
        return None, None


class EventTimeline:
    """Tracks key events with timestamps for display."""
    def __init__(self):
        self.events = []
        self.start_time = datetime.now()

    def add(self, event, style="white"):
        self.events.append({
            "ts": datetime.now().strftime("%H:%M:%S"),
            "elapsed": f"+{(datetime.now() - self.start_time).seconds}s",
            "event": event,
            "style": style,
        })

    def to_table(self):
        t = Table(
            title="[bold]Event Timeline[/]",
            box=box.ROUNDED, border_style="blue", show_lines=False,
            width=74,
        )
        t.add_column("Time", style="dim", width=10)
        t.add_column("Elapsed", style="dim", width=8)
        t.add_column("Event", width=50)
        for e in self.events[-6:]:
            t.add_row(e["ts"], e["elapsed"], f"[{e['style']}]{e['event']}[/]")
        return t


class PerfGraph:
    """Rolling ASCII performance graph showing response times."""

    BLOCKS = " ▁▂▃▄▅▆▇█"

    def __init__(self):
        self.samples = []  # (timestamp, ms, is_healthy)
        self.fixed_at = None

    def add(self, ms, is_healthy=True):
        self.samples.append((datetime.now(), ms, is_healthy))
        if is_healthy and self.fixed_at is None and len(self.samples) > 5:
            unhealthy_before = any(not s[2] for s in self.samples[-10:-1])
            if unhealthy_before:
                self.fixed_at = len(self.samples) - 1

    def to_panel(self, title="Performance"):
        if len(self.samples) < 2:
            return Panel("[dim]Collecting data...[/]", title=f"[bold]{title}[/]", border_style="magenta", width=76)

        recent = self.samples[-50:]
        sparkline = ""
        for _, ms, healthy in recent:
            if not healthy or ms == 0:
                sparkline += "[red]✕[/]"
            elif ms > 3000:
                sparkline += "[red]█[/]"
            elif ms > 1000:
                sparkline += "[yellow]▆[/]"
            elif ms > 200:
                sparkline += "[yellow]▃[/]"
            else:
                sparkline += "[green]▁[/]"

        valid = [s[1] for s in recent if s[1] > 0]
        avg = sum(valid) / len(valid) if valid else 0

        if self.fixed_at is not None:
            before = [s[1] for s in self.samples[:self.fixed_at] if s[1] > 0][-20:]
            after = [s[1] for s in self.samples[self.fixed_at:] if s[1] > 0][:20]
            if before and after:
                before_avg = sum(before) / len(before)
                after_avg = sum(after) / len(after)
                improvement = ((before_avg - after_avg) / max(before_avg, 1)) * 100
                stats = f"\n  [red]██ BEFORE[/] avg: [red bold]{before_avg:.0f}ms[/]    [green]██ AFTER[/] avg: [green bold]{after_avg:.0f}ms[/]    [cyan bold]⚡ {improvement:.0f}% improvement[/]"
                return Panel(
                    f"  {sparkline}\n{stats}",
                    title=f"[bold green]📊 {title} — SRE Agent Fixed![/]",
                    border_style="green", width=76,
                )

        return Panel(
            f"  {sparkline}\n  Avg: [{_color_ms(avg)}]{avg:.0f}ms[/]  |  Samples: {len(self.samples)}",
            title=f"[bold magenta]📊 {title}[/]",
            border_style="magenta", width=76,
        )


# ── Banner & Menu ───────────────────────────────────────────

BANNER = r"""[bold cyan]
  ██████╗  ██████╗ ██╗    ██╗███████╗██████╗  ██████╗ ██████╗ ██╗██████╗
  ██╔══██╗██╔═══██╗██║    ██║██╔════╝██╔══██╗██╔════╝ ██╔══██╗██║██╔══██╗
  ██████╔╝██║   ██║██║ █╗ ██║█████╗  ██████╔╝██║  ███╗██████╔╝██║██║  ██║
  ██╔═══╝ ██║   ██║██║███╗██║██╔══╝  ██╔══██╗██║   ██║██╔══██╗██║██║  ██║
  ██║     ╚██████╔╝╚███╔███╔╝███████╗██║  ██║╚██████╔╝██║  ██║██║██████╔╝
  ╚═╝      ╚═════╝  ╚══╝╚══╝ ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝╚═════╝
  [bold white]Zava Power ZeroOps — SRE Agent Demo Simulator[/bold white][/bold cyan]
"""


def _system_status():
    """Quick health check of all services."""
    lines = []
    services = [
        ("Portal",       PORTAL_URL),
        ("Outage API",   OUTAGE_API_URL),
        ("Meter API",    METER_API_URL),
        ("Grid Status",  GRID_API_URL),
        ("Notification", NOTIFY_URL),
    ]
    for name, url in services:
        if not url:
            lines.append(f"  {name:<16} [dim]● Not configured[/]")
        else:
            code, ms, _ = health_check(url, timeout=3)
            lines.append(f"  {name:<16} {_status_icon(code)}  [{_color_ms(ms)}]{ms:.0f}ms[/]")

    if SN_URL:
        lines.append(f"  {'ServiceNow':<16} [green]● Configured[/]")
    else:
        lines.append(f"  {'ServiceNow':<16} [dim]● Not configured[/]")

    return "\n".join(lines)


def show_menu():
    console.clear()
    console.print(BANNER)

    tbl = Table(
        title="[bold]Demo Scenarios[/]",
        box=box.DOUBLE_EDGE, border_style="cyan",
        title_style="bold white", show_lines=True, padding=(0, 2),
    )
    tbl.add_column("#", style="bold cyan", width=4, justify="center")
    tbl.add_column("Scenario", style="bold white", width=28)
    tbl.add_column("Description", style="dim white", width=48)

    tbl.add_row("1", "🔴  Service Outage",
        "outage-api returns 503 (FORCE_ERROR).\n"
        "SRE Agent detects, fixes config, restores.",
    )
    tbl.add_row("2", "💾  Memory Leak",
        "meter-api leaks memory until OOM.\n"
        "SRE Agent detects, restarts, recommends limit.",
    )
    tbl.add_row("3", "📉  Deploy Regression",
        "grid-status-api deployed with 5s delay.\n"
        "SRE Agent correlates to deploy, rolls back.",
    )
    tbl.add_row("4", "💥  Container Crash",
        "notification-svc missing REQUIRED_CONFIG.\n"
        "SRE Agent analyzes logs, adds env var.",
    )
    tbl.add_row("5", "🎫  ServiceNow Demo",
        "Create incident → SRE Agent updates → resolves.\n"
        "Full ITSM lifecycle.",
    )
    tbl.add_row("6", "🎯  Simulate All",
        "Launch scenarios 1-4 monitors simultaneously.",
    )
    tbl.add_row("7", "🧹  Reset All",
        "Restore all services to healthy baseline.",
    )
    tbl.add_row("Q", "🚪  Quit", "Exit the simulator.")

    console.print(Align.center(tbl))
    console.print()

    console.print(Align.center(
        Panel(_system_status(), title="[bold]System Status[/]", border_style="dim", width=62)
    ))
    console.print()


# ═══════════════════════════════════════════════════════════
# SCENARIO 1 — Service Outage (outage-api 503)
# ═══════════════════════════════════════════════════════════

def scenario_service_outage():
    console.clear()
    console.print(Panel(
        "[bold]Scenario 1 — Service Outage[/]\n\n"
        "The outage-api has been broken (FORCE_ERROR=true).\n"
        "SRE Agent should detect the 503 errors and fix the config.\n\n"
        "[dim]Controls:  q = quit   b = break again   r = reset[/]",
        title="[cyan bold]🔴 SERVICE OUTAGE SIMULATOR[/]",
        border_style="cyan", width=76,
    ))

    if not OUTAGE_API_URL:
        console.print("[red]POWERGRID_OUTAGE_API_URL not set. Configure and retry.[/]")
        console.print("[dim]Press any key…[/]"); _wait_key(); return

    # Break the service
    console.print("[yellow]Breaking outage-api (setting FORCE_ERROR=true)…[/]")
    _break_service("outage")
    time.sleep(1)

    timeline = EventTimeline()
    timeline.add("Simulation started — outage-api broken", "cyan")
    perf = PerfGraph()
    log = []
    was_broken = True
    fix_banner_shown = False
    alert_detected = False

    try:
        with Live(console=console, refresh_per_second=4) as live:
            while True:
                key = check_key()
                if key == "q":
                    break
                if key == "b":
                    _break_service("outage")
                    was_broken = True
                    fix_banner_shown = False
                    perf = PerfGraph()
                    timeline.add("⌨️  Re-broken outage-api", "yellow bold")
                if key == "r":
                    _fix_service("outage")
                    timeline.add("⌨️  Manually reset outage-api", "yellow")

                code, ms, body = health_check(OUTAGE_API_URL)
                is_healthy = code == 200
                perf.add(ms if is_healthy else 0, is_healthy)

                log.append({
                    "ts": datetime.now().strftime("%H:%M:%S"),
                    "code": code, "ms": ms, "healthy": is_healthy,
                })
                if len(log) > 20:
                    log.pop(0)

                # Track events
                if not is_healthy and was_broken and not alert_detected:
                    cond, _ = _check_alert_fired("http-5xx")
                    if cond == "Fired":
                        alert_detected = True
                        timeline.add("🚨 ALERT FIRED — Azure Monitor", "red bold")

                if is_healthy and was_broken and not fix_banner_shown:
                    fix_banner_shown = True
                    was_broken = False
                    timeline.add("🎉 SERVICE RESTORED! SRE Agent fixed it!", "green bold")

                # ── build display ──
                grid = Table.grid(padding=1)
                grid.add_column()

                grid.add_row(Panel(
                    "[bold cyan]🔴 SERVICE OUTAGE SIMULATOR[/]  —  outage-api\n"
                    "[dim]q = quit   b = break   r = reset[/]",
                    border_style="cyan",
                ))

                if fix_banner_shown:
                    grid.add_row(Panel(
                        "[bold green]🎉🎉🎉  SERVICE RESTORED!  🎉🎉🎉[/]\n\n"
                        "[green]The SRE Agent detected the outage and restored the service![/]",
                        border_style="green bold",
                        title="[green bold]✅ FIXED[/]",
                    ))
                elif is_healthy:
                    grid.add_row(Text("  ✅ outage-api: HEALTHY", style="green bold"))
                else:
                    grid.add_row(Text("  ❌ outage-api: DOWN (503) — FORCE_ERROR=true", style="red bold"))

                # Health check table
                ht = Table(
                    title="[bold]Health Checks[/]",
                    box=box.ROUNDED, border_style="dim", show_lines=False,
                )
                ht.add_column("Time", style="dim", width=10)
                ht.add_column("Status", width=8, justify="center")
                ht.add_column("Latency", width=12, justify="right")
                ht.add_column("Result", width=14, justify="center")
                for e in log[-8:]:
                    ht.add_row(
                        e["ts"],
                        f"[{_color_status(e['code'])}]{e['code']}[/]",
                        f"[{_color_ms(e['ms'])}]{e['ms']:.0f}ms[/]" if e["ms"] > 0 else "[red]—[/]",
                        "[green]🟢 UP[/]" if e["healthy"] else "[red]🔴 DOWN[/]",
                    )
                grid.add_row(ht)
                grid.add_row(perf.to_panel("outage-api Response"))
                grid.add_row(timeline.to_table())
                live.update(grid)
                time.sleep(2)
    except KeyboardInterrupt:
        pass


# ═══════════════════════════════════════════════════════════
# SCENARIO 3 — Deploy Regression (grid-status-api slow)
# ═══════════════════════════════════════════════════════════

def scenario_deploy_regression():
    console.clear()
    console.print(Panel(
        "[bold]Scenario 3 — Deploy Regression[/]\n\n"
        "A bad revision was deployed to grid-status-api with a 5s delay.\n"
        "SRE Agent should correlate with the deployment and roll back.\n\n"
        "[dim]Controls:  q = quit   b = break again   r = reset[/]",
        title="[cyan bold]📉 DEPLOY REGRESSION SIMULATOR[/]",
        border_style="cyan", width=76,
    ))

    if not GRID_API_URL:
        console.print("[red]POWERGRID_GRID_API_URL not set. Configure and retry.[/]")
        console.print("[dim]Press any key…[/]"); _wait_key(); return

    console.print("[yellow]Deploying bad revision (SIMULATE_DELAY_MS=5000)…[/]")
    _break_service("grid")
    time.sleep(1)

    timeline = EventTimeline()
    timeline.add("Bad revision deployed — 5000ms delay injected", "cyan")
    perf = PerfGraph()
    log = []
    was_slow = True
    fix_banner_shown = False

    try:
        with Live(console=console, refresh_per_second=4) as live:
            while True:
                key = check_key()
                if key == "q":
                    break
                if key == "b":
                    _break_service("grid")
                    was_slow = True
                    fix_banner_shown = False
                    perf = PerfGraph()
                    timeline.add("⌨️  Re-deployed bad revision", "yellow bold")
                if key == "r":
                    _fix_service("grid")
                    timeline.add("⌨️  Manually rolled back", "yellow")

                # Query the regions endpoint for latency measurement
                t0 = time.time()
                try:
                    r = req.get(f"{GRID_API_URL}/regions", timeout=10)
                    ms = (time.time() - t0) * 1000
                    code = r.status_code
                except Exception:
                    ms = (time.time() - t0) * 1000
                    code = 0

                is_fast = ms < 1000 and code == 200
                perf.add(ms, is_fast)

                log.append({
                    "ts": datetime.now().strftime("%H:%M:%S"),
                    "ms": ms, "code": code, "fast": is_fast,
                })
                if len(log) > 20:
                    log.pop(0)

                if is_fast and was_slow and not fix_banner_shown:
                    fix_banner_shown = True
                    was_slow = False
                    timeline.add("🎉 ROLLBACK COMPLETE! Response time normal!", "green bold")

                # ── display ──
                grid = Table.grid(padding=1)
                grid.add_column()

                grid.add_row(Panel(
                    "[bold cyan]📉 DEPLOY REGRESSION SIMULATOR[/]  —  grid-status-api\n"
                    "[dim]q = quit   b = break   r = reset[/]",
                    border_style="cyan",
                ))

                if fix_banner_shown:
                    grid.add_row(Panel(
                        "[bold green]🎉🎉🎉  ROLLBACK COMPLETE!  🎉🎉🎉[/]\n\n"
                        "[green]SRE Agent correlated the latency spike with the deployment\n"
                        "and rolled back to the previous revision![/]",
                        border_style="green bold",
                    ))
                elif is_fast:
                    grid.add_row(Text(f"  ✅ grid-status-api: {ms:.0f}ms (normal)", style="green bold"))
                else:
                    grid.add_row(Text(f"  ⚠️  grid-status-api: {ms:.0f}ms (DEGRADED)", style="red bold"))

                # Latency table
                lt = Table(
                    title="[bold]Response Times[/]",
                    box=box.ROUNDED, border_style="dim", show_lines=False,
                )
                lt.add_column("Time", style="dim", width=10)
                lt.add_column("Latency", width=14, justify="right")
                lt.add_column("Bar", width=32)
                lt.add_column("Status", width=12, justify="center")
                for e in log[-8:]:
                    m = e["ms"]
                    lt.add_row(
                        e["ts"],
                        f"[{_color_ms(m)}]{m:.0f}ms[/]",
                        _bar(m),
                        "[green bold]⚡ FAST[/]" if e["fast"] else "[red bold]🐌 SLOW[/]",
                    )
                grid.add_row(lt)
                grid.add_row(perf.to_panel("grid-status-api Latency"))
                grid.add_row(timeline.to_table())
                live.update(grid)
                time.sleep(2)
    except KeyboardInterrupt:
        pass


# ═══════════════════════════════════════════════════════════
# BREAK / FIX helpers (calls az containerapp update)
# ═══════════════════════════════════════════════════════════

def _break_service(service):
    """Inject a failure into a container app via env var update."""
    cmds = {
        "outage": f'az containerapp update -n ca-{WORKLOAD}-outage -g {RESOURCE_GROUP} --set-env-vars FORCE_ERROR=true --no-wait -o none 2>nul',
        "meter":  f'az containerapp update -n ca-{WORKLOAD}-meter -g {RESOURCE_GROUP} --set-env-vars SIMULATE_OOM=true --no-wait -o none 2>nul',
        "grid":   f'az containerapp update -n ca-{WORKLOAD}-grid -g {RESOURCE_GROUP} --set-env-vars SIMULATE_DELAY_MS=5000 --no-wait -o none 2>nul',
        "notify": f'az containerapp update -n ca-{WORKLOAD}-notify -g {RESOURCE_GROUP} --remove-env-vars REQUIRED_CONFIG --no-wait -o none 2>nul',
    }
    cmd = cmds.get(service)
    if cmd:
        try:
            subprocess.run(cmd, shell=True, timeout=30)
        except Exception as e:
            console.print(f"[yellow]Break warning: {e}[/]")


def _fix_service(service):
    """Restore a container app to healthy state."""
    cmds = {
        "outage": f'az containerapp update -n ca-{WORKLOAD}-outage -g {RESOURCE_GROUP} --remove-env-vars FORCE_ERROR --no-wait -o none 2>nul',
        "meter":  f'az containerapp update -n ca-{WORKLOAD}-meter -g {RESOURCE_GROUP} --remove-env-vars SIMULATE_OOM --no-wait -o none 2>nul',
        "grid":   f'az containerapp update -n ca-{WORKLOAD}-grid -g {RESOURCE_GROUP} --remove-env-vars SIMULATE_DELAY_MS --no-wait -o none 2>nul',
        "notify": f'az containerapp update -n ca-{WORKLOAD}-notify -g {RESOURCE_GROUP} --set-env-vars REQUIRED_CONFIG=enabled --no-wait -o none 2>nul',
    }
    cmd = cmds.get(service)
    if cmd:
        try:
            subprocess.run(cmd, shell=True, timeout=30)
        except Exception as e:
            console.print(f"[yellow]Fix warning: {e}[/]")


def reset_all():
    """Reset all services to healthy state."""
    console.print("[yellow]Resetting all services to healthy baseline…[/]")
    for svc in ("outage", "meter", "grid", "notify"):
        console.print(f"  Fixing {svc}…")
        _fix_service(svc)
    console.print("[green]✅ All services reset to healthy.[/]")
    time.sleep(2)


# ═══════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════

def main():
    while True:
        show_menu()
        choice = console.input("[bold cyan]Select scenario (1-7, Q): [/]").strip().lower()

        if choice == "1":
            scenario_service_outage()
        elif choice == "2":
            console.print("[yellow]Scenario 2 (Memory Leak) — coming soon[/]")
            time.sleep(2)
        elif choice == "3":
            scenario_deploy_regression()
        elif choice == "4":
            console.print("[yellow]Scenario 4 (Container Crash) — coming soon[/]")
            time.sleep(2)
        elif choice == "5":
            console.print("[yellow]Scenario 5 (ServiceNow) — coming soon[/]")
            time.sleep(2)
        elif choice == "6":
            console.print("[yellow]Scenario 6 (Simulate All) — coming soon[/]")
            time.sleep(2)
        elif choice == "7":
            reset_all()
        elif choice == "q":
            console.print("[bold]Goodbye! ⚡[/]")
            break
        else:
            console.print("[red]Invalid choice.[/]")
            time.sleep(1)


if __name__ == "__main__":
    main()
