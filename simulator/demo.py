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

# ── Expected Azure subscription (catches wrong-account issues) ──
EXPECTED_SUBSCRIPTION = "e964602f-6afc-4cc7-ba6b-3a796008e254"

# ── Centralized az CLI runner ───────────────────────────────
def run_az(args, timeout=30, retries=1, parse_json=False, quiet=False):
    """Run an az CLI command reliably. Returns (success, stdout, stderr).
    
    - Uses shell=False with arg list for safe quoting
    - Kills process tree on timeout
    - Retries on transient failures (throttle / conflict)
    - Parses JSON output if requested
    """
    if isinstance(args, str):
        # Split string command into list, but keep az.cmd as first arg
        import shlex
        args = args.split()

    # On Windows `az` is `az.cmd`; subprocess without shell=True cannot
    # resolve PATHEXT, so we resolve the executable explicitly.
    if args and args[0] == "az":
        import shutil
        resolved = shutil.which("az") or shutil.which("az.cmd")
        if resolved:
            args = [resolved] + list(args[1:])

    last_err = ""
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if r.returncode == 0:
                out = r.stdout.strip()
                if parse_json and out:
                    try:
                        return True, json.loads(out), ""
                    except json.JSONDecodeError:
                        return True, out, ""
                return True, out, ""
            last_err = r.stderr.strip() or r.stdout.strip()
            # Retry on throttle (429) or conflict
            if any(x in last_err.lower() for x in ["throttl", "429", "conflict", "too many requests"]):
                if attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
            return False, "", last_err
        except subprocess.TimeoutExpired as e:
            # Kill the process tree
            if e.cmd and hasattr(e, 'args'):
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(e.args)],
                                   capture_output=True, timeout=5)
                except Exception:
                    pass
            last_err = f"Command timed out after {timeout}s"
            if attempt < retries:
                continue
            return False, "", last_err
        except FileNotFoundError:
            return False, "", "az CLI not found. Install from https://aka.ms/installazurecli"
        except Exception as e:
            return False, "", str(e)
    return False, "", last_err


# ── SRE Agent Token Manager ────────────────────────────────
class TokenManager:
    """Manages SRE Agent access tokens with auto-refresh."""
    
    def __init__(self):
        self._token = None
        self._expires_at = 0  # epoch seconds
    
    def get_token(self):
        """Get a valid token, refreshing if expired or close to expiry."""
        now = time.time()
        # Refresh if token expires within 5 minutes
        if self._token and (self._expires_at - now) > 300:
            return self._token
        
        ok, out, err = run_az(
            ["az", "account", "get-access-token", "--resource",
             "https://azuresre.ai", "--query", "accessToken", "-o", "tsv"],
            timeout=30
        )
        if ok and out:
            self._token = out
            self._expires_at = now + 3600  # tokens are typically 1h
            return self._token
        return None
    
    @property
    def is_valid(self):
        return self._token and (self._expires_at - time.time()) > 300

_token_mgr = TokenManager()


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
SN_URL  = os.environ.get("POWERGRID_SN_URL",  "https://dev268981.service-now.com")
SN_USER = os.environ.get("POWERGRID_SN_USER", "admin")
SN_PASS = os.environ.get("POWERGRID_SN_PASS", "ME@6SkW2d*lc")

# ── Infrastructure naming (override via env to retarget another deployment) ──
RESOURCE_GROUP = os.environ.get("POWERGRID_RESOURCE_GROUP", f"rg-{WORKLOAD}")
VM_NAME        = os.environ.get("POWERGRID_VM_NAME",        "vm-powergrid-arc")
LAW_NAME       = os.environ.get("POWERGRID_LAW_NAME",       f"law-{WORKLOAD}")
SRE_AGENT_NAME = os.environ.get("POWERGRID_SRE_AGENT_NAME", "sre-zavapower-ops")

SRE_AGENT_THREAD_BASE = (
    f"https://sre.azure.com/agents/subscriptions/{EXPECTED_SUBSCRIPTION}"
    f"/resourceGroups/{RESOURCE_GROUP}/providers/Microsoft.App/agents/{SRE_AGENT_NAME}/views/thread"
)

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

# ── Pre-flight Checks ───────────────────────────────────────
def preflight_check(needs_vm=False, needs_ado=False, needs_services=None):
    """Verify dependencies before a scenario. Returns True if all good."""
    ok = True

    # Check Azure CLI login
    try:
        r = subprocess.run('az account show --query name -o tsv',
                          shell=True, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            console.print("[red]  ✗ Not logged into Azure CLI. Run: az login[/]")
            return False
    except Exception:
        console.print("[red]  ✗ Azure CLI not available[/]")
        return False

    # Check VM is running (start if not)
    if needs_vm:
        console.print("[dim]  Checking VM...[/]", end="")
        try:
            r = subprocess.run(
                f'az vm show -g {RESOURCE_GROUP} -n {VM_NAME} --show-details --query powerState -o tsv',
                shell=True, capture_output=True, text=True, timeout=30)
            state = r.stdout.strip()
            if state != "VM running":
                console.print(f" [yellow]{state}[/] — starting VM (this may take 1-2 min)...", end="")
                subprocess.run(
                    f'az vm start --resource-group {RESOURCE_GROUP} --name {VM_NAME} -o none',
                    shell=True, timeout=300)
                console.print("[green] ✓ VM started[/]")
            else:
                console.print("[green] ✓ running[/]")
        except subprocess.TimeoutExpired:
            console.print("[red] ✗ VM start timed out[/]")
            ok = False
        except Exception as e:
            console.print(f"[red] ✗ VM check failed: {e}[/]")
            ok = False

    # Check ADO access
    if needs_ado:
        console.print("[dim]  Checking ADO...[/]", end="")
        try:
            r = subprocess.run(
                f'az pipelines list --project {ADO_PROJECT} --org https://dev.azure.com/{ADO_ORG} --query "[0].name" -o tsv',
                shell=True, capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and r.stdout.strip():
                console.print(f"[green] ✓ {r.stdout.strip()}[/]")
            else:
                console.print("[red] ✗ ADO not accessible[/]")
                ok = False
        except Exception:
            console.print("[red] ✗ ADO check failed[/]")
            ok = False

    # Check service health
    if needs_services:
        for name, url in needs_services:
            console.print(f"[dim]  Checking {name}...[/]", end="")
            code, ms = health_check(url)
            if code == 200:
                console.print(f"[green] ✓ {code} ({ms:.0f}ms)[/]")
            else:
                console.print(f"[red] ✗ {code or 'unreachable'}[/]")
                ok = False

    if not ok:
        console.print("\n[red]  Pre-flight checks failed. Fix issues and retry.[/]")
    else:
        console.print("[green]  All checks passed.[/]")
    console.print()
    return ok

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
    """Phase 1: Display the scenario narrative then proceed automatically."""
    console.clear()
    console.print(Panel(
        f"\n  [bold]BACKSTORY:[/]\n{_indent(backstory)}\n\n"
        f"  [bold]WHAT WILL HAPPEN:[/]\n{_indent(what_happens)}\n",
        title=f"[bold]{emoji} {title}[/]",
        border_style="cyan", width=68,
    ))
    time.sleep(2)

def show_result(emoji, title, lines):
    """Phase 4: Display result summary and wait for Enter."""
    console.print(Panel(
        "\n" + "\n".join(f"  {l}" for l in lines) + "\n",
        title=f"[bold green]{emoji} {title}[/]",
        border_style="green", width=68,
    ))
    console.input("[dim]  Press Enter to return to menu...[/]")

# ── Azure DevOps Pipeline helpers ───────────────────────────
def ado_pipeline_url(run_id):
    """Clickable ADO portal URL for a build/release run."""
    return f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_build/results?buildId={run_id}"

def ado_pr_url(pr_id):
    return f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_git/{ADO_PROJECT}/pullrequest/{pr_id}"

def snow_inc_url(inc_number):
    return f"{SN_URL}/incident.do?sysparm_query=number={inc_number}"

def poll_latest_pipeline_run(pipeline_name, since_iso):
    """Find the most recent run of a pipeline that started at/after since_iso.
    Returns (run_id, status, result) or (None, None, None)."""
    try:
        cmd = (f'az pipelines runs list --pipeline-ids '
               f'$(az pipelines show --name "{pipeline_name}" '
               f'--project {ADO_PROJECT} --org https://dev.azure.com/{ADO_ORG} '
               f'--query id -o tsv) '
               f'--project {ADO_PROJECT} --org https://dev.azure.com/{ADO_ORG} '
               f'--top 5 -o json')
        # PowerShell-friendly: use single command form
        cmd_ps = (
            f'$pipId=(az pipelines show --name "{pipeline_name}" '
            f'--project {ADO_PROJECT} --org https://dev.azure.com/{ADO_ORG} '
            f'--query id -o tsv); '
            f'az pipelines runs list --pipeline-ids $pipId '
            f'--project {ADO_PROJECT} --org https://dev.azure.com/{ADO_ORG} '
            f'--top 5 -o json'
        )
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd_ps],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0 or not r.stdout.strip():
            return None, None, None
        runs = json.loads(r.stdout)
        for run in runs:
            qt = run.get("queueTime", "") or run.get("createdDate", "")
            if qt and qt >= since_iso:
                return run.get("id"), run.get("status"), run.get("result", "")
        return None, None, None
    except Exception:
        return None, None, None

def poll_snow_incident_for(since_iso, contains=None):
    """Find newest SNOW incident created at/after since_iso, optionally matching text.
    Returns (number, sys_id) or (None, None)."""
    try:
        params = {
            "sysparm_query": f"sys_created_on>={since_iso[:19].replace('T',' ')}^ORDERBYDESCsys_created_on",
            "sysparm_limit": "10",
            "sysparm_fields": "number,sys_id,short_description"
        }
        r = requests.get(
            f"{SN_URL}/api/now/table/incident",
            params=params,
            auth=(SN_USER, SN_PASS),
            headers={"Accept": "application/json"},
            timeout=10
        )
        if r.status_code == 200:
            for inc in r.json().get("result", []):
                if contains is None or contains.lower() in inc.get("short_description", "").lower():
                    return inc.get("number"), inc.get("sys_id")
    except Exception:
        pass
    return None, None

def poll_ado_pr(since_iso, source_branch_contains=None):
    """Find newest active PR created at/after since_iso.
    Returns (pr_id, source_branch, title) or (None, None, None)."""
    try:
        cmd_ps = (
            f'az repos pr list --project {ADO_PROJECT} '
            f'--org https://dev.azure.com/{ADO_ORG} '
            f'--repository {ADO_PROJECT} --status active --top 10 -o json'
        )
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd_ps],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0 or not r.stdout.strip():
            return None, None, None
        prs = json.loads(r.stdout)
        for pr in prs:
            ct = pr.get("creationDate", "")
            if ct and ct >= since_iso:
                src = pr.get("sourceRefName", "")
                if source_branch_contains and source_branch_contains.lower() not in src.lower():
                    continue
                return pr.get("pullRequestId"), src, pr.get("title", "")
        return None, None, None
    except Exception:
        return None, None, None

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
    """Trigger PowerGrid-Build; release auto-chains via resources.pipelines.
    Returns dict: {build_id, release_id, build_url, release_url} or None."""
    sim_start = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    console.print("\n[bold cyan]  ▶ Triggering PowerGrid-Build...[/]")
    build_id = run_ado_pipeline("PowerGrid-Build", {
        "failure_scenario": failure_scenario, "services": services,
    })
    if not build_id:
        console.input("[dim]  Press Enter...[/]"); return None

    build_url = ado_pipeline_url(build_id)
    console.print(f"[green]  ✓ Build #{build_id} triggered[/]  "
                  f"[cyan][link={build_url}]view in ADO[/link][/]\n")
    r = poll_pipeline(build_id, "PowerGrid-Build")
    if r == "quit": return None
    if r not in ("succeeded", "partiallySucceeded"):
        console.print(f"[red]  ✗ Build {r}[/]")
        console.input("[dim]  Press Enter...[/]"); return None

    if r == "partiallySucceeded":
        console.print("[yellow]  ⚠ Build partiallySucceeded "
                      "(CSSC compliance warnings — non-blocking)[/]")
    console.print("[green]  ✓ Build succeeded![/]\n")
    console.print("[bold cyan]  ▶ Waiting for PowerGrid-Release auto-trigger (build→release chaining)...[/]")

    release_id = None
    deadline = time.time() + 90
    while time.time() < deadline:
        rid, status, _ = poll_latest_pipeline_run("PowerGrid-Release", sim_start)
        if rid:
            release_id = rid
            break
        time.sleep(5)

    if not release_id:
        console.print("[yellow]  ⚠ Release did not auto-trigger within 90s — falling back to manual trigger[/]")
        release_id = run_ado_pipeline("PowerGrid-Release")
        if not release_id:
            console.input("[dim]  Press Enter...[/]"); return None

    release_url = ado_pipeline_url(release_id)
    console.print(f"[green]  ✓ Release #{release_id} started[/]  "
                  f"[cyan][link={release_url}]view in ADO[/link][/]\n")
    r = poll_pipeline(release_id, "PowerGrid-Release")
    if r == "quit": return None
    if r not in ("succeeded", "partiallySucceeded"):
        console.print(f"[red]  ✗ Release {r}[/]")
        console.input("[dim]  Press Enter...[/]"); return None

    if r == "partiallySucceeded":
        console.print("[yellow]  ⚠ Release partiallySucceeded "
                      "(CSSC compliance warnings — non-blocking)[/]")
    console.print("[green]  ✓ Release succeeded![/]\n")
    return {
        "build_id": build_id, "release_id": release_id,
        "build_url": build_url, "release_url": release_url,
        "sim_start": sim_start,
    }

# ── Alert Polling Helper ────────────────────────────────────
def poll_alert(alert_name_contains, since_time, required_condition="Fired"):
    """Check if an Azure Monitor alert matching the name exists.
    Returns (found: bool, alert_id: str or None, alert_time: str or None).
    - alert_name_contains: substring to match in the alert rule name
    - since_time: only match alerts fired after this ISO timestamp
    - required_condition: "Fired" or "Resolved"
    """
    try:
        result = subprocess.run(
            f'az rest --method GET --url "https://management.azure.com/subscriptions/{EXPECTED_SUBSCRIPTION}/providers/Microsoft.AlertsManagement/alerts?api-version=2019-03-01&targetResourceGroup={RESOURCE_GROUP}" -o json',
            shell=True, timeout=60, capture_output=True, text=True
        )
        if result.returncode == 0:
            import json as _json
            alerts = _json.loads(result.stdout, strict=False)
            for a in alerts.get("value", []):
                props = a.get("properties", {}).get("essentials", {})
                rule = props.get("alertRule", "")
                if alert_name_contains not in rule:
                    continue
                alert_time = props.get("startDateTime", "")
                if alert_time < since_time:
                    continue
                if props.get("monitorCondition") != required_condition:
                    continue
                alert_id = a.get("id", "")
                return True, alert_id, alert_time
    except Exception:
        pass
    return False, None, None


def poll_alert_by_id(alert_id, required_condition="Resolved"):
    """Check if a specific alert has transitioned to the required condition.
    Returns True if the alert matches the required condition."""
    try:
        result = subprocess.run(
            f'az rest --method GET --url "https://management.azure.com{alert_id}?api-version=2019-03-01" -o json',
            shell=True, timeout=30, capture_output=True, text=True
        )
        if result.returncode == 0:
            import json as _json
            data = _json.loads(result.stdout, strict=False)
            condition = data.get("properties", {}).get("essentials", {}).get("monitorCondition", "")
            return condition == required_condition
    except Exception:
        pass
    return False

def poll_agent_thread(keyword, since_time):
    """Check if SRE Agent has a thread matching keyword created since since_time.
    Returns (found: bool, thread_id: str or None)."""
    try:
        result = subprocess.run(
            ["srectl", "thread", "list", "--quiet"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if keyword.lower() in line.lower() and since_time[:10] in line:
                # Try to extract thread ID (UUID format) from the line
                parts = line.strip().split()
                for p in parts:
                    p = p.strip()
                    if len(p) == 36 and p.count("-") == 4:
                        return True, p
                return True, None
    except Exception:
        pass
    return False, None

# ── Health Monitoring (Phase 3) ─────────────────────────────
def monitor_health(url, path, service_name, agent_name,
                   healthy_fn=None, ok_label="HEALTHY", bad_label="UNHEALTHY",
                   alert_name=None, trigger_type="release"):
    """Live health monitor with alert + agent tracking.
    
    alert_name: if set, polls Azure Monitor for this alert (e.g. "http-5xx")
    trigger_type: "release" (deployment scenarios) or "alert" (organic issues)
    """
    if healthy_fn is None:
        healthy_fn = lambda code, ms: code == 200

    sim_start = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    timeline = EventTimeline()
    
    if trigger_type == "release":
        timeline.add(f"⚡ Release trigger fired → {agent_name} investigating", "yellow bold")
    else:
        timeline.add(f"Monitoring {service_name} — waiting for alert", "cyan")

    checks = []
    had_unhealthy = False
    consecutive_ok = 0
    recovered = False
    alert_fired = (trigger_type == "release")  # release trigger = already triggered
    agent_started = (trigger_type == "release")
    last_alert_poll = datetime.min
    last_agent_poll = datetime.min

    with Live(console=console, refresh_per_second=2) as live:
        while not recovered:
            key = check_key()
            if key in (b"q", b"Q"):
                return False

            now = datetime.now()

            # Poll for alert (if applicable and not yet fired)
            if alert_name and not alert_fired and (now - last_alert_poll).seconds >= 10:
                last_alert_poll = now
                fired, _ = poll_alert(alert_name, sim_start)
                if fired:
                    alert_fired = True
                    timeline.add(f"🚨 ALERT FIRED — {alert_name}", "red bold")

            # Poll for agent thread
            if alert_fired and not agent_started and (now - last_agent_poll).seconds >= 10:
                last_agent_poll = now
                found, thread_id = poll_agent_thread(service_name, sim_start)
                if found:
                    agent_started = True
                    timeline.add(f"🤖 {agent_name} picked up — investigating", "yellow bold")
                    if thread_id:
                        thread_url = f"{SRE_AGENT_THREAD_BASE}/{thread_id}"
                        timeline.add(f"🔗 [link={thread_url}]View agent thread[/link]", "cyan")

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

            # Status line with alert + agent state
            color = "green" if healthy else "red"
            icon = "✅" if healthy else "❌"
            label = ok_label if healthy else bad_label
            grid.add_row(Text(
                f"  {icon} {service_name}: {label} ({code} / {ms:.0f}ms)",
                style=f"{color} bold"))

            if alert_name:
                a_status = "[green]🚨 FIRED[/]" if alert_fired else "[yellow]⏳ pending[/]"
                ag_status = "[green]🤖 working[/]" if agent_started else "[dim]waiting[/]"
                grid.add_row(Text(f"  Alert: {a_status}   Agent: {ag_status}"))

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

# ── End-to-End Deployment Monitor (Phase A + Phase B) ──────────────────────
def monitor_deployment_e2e(url, path, service_name, healthy_fn=None,
                           ok_label="HEALTHY", bad_label="UNHEALTHY",
                           alert_name=None, build_info=None,
                           branch_hint=None):
    """E2E deployment-validator watch:
      Phase A (mitigation): detect → SNOW → rollback → recovered
      Phase B (long-term):  fix PR → rebuild → re-deploy → re-validate
    Renders a phase-strip with clickable links and a timeline.
    Returns True when the loop closes (re-validation succeeds OR Phase A
    recovers and we time out waiting for Phase B)."""
    if healthy_fn is None:
        healthy_fn = lambda code, ms: code == 200

    sim_start = (build_info or {}).get("sim_start") or \
                datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    timeline = EventTimeline()

    # Pre-seed timeline with Phase 0/1 (pipelines)
    if build_info:
        timeline.add(
            f"🔨 Build #{build_info['build_id']} succeeded — "
            f"[link={build_info['build_url']}]view[/link]", "green")
        timeline.add(
            f"🚀 Release #{build_info['release_id']} deployed — "
            f"[link={build_info['release_url']}]view[/link]", "green")
        timeline.add("⚡ Post-Deploy Validation trigger fired → deployment-validator", "yellow bold")

    # Phase tracking flags
    phases = {
        "build":      bool(build_info),
        "release":    bool(build_info),
        "deployed":   bool(build_info),
        "detected":   False,
        "snow":       False,
        "rollback":   False,
        "restored":   False,
        "fix_pr":     False,
        "rebuild":    False,
        "redeploy":   False,
        "revalidate": False,
    }
    snow_inc = None
    snow_url = None
    pr_id = None
    pr_url = None
    rebuild_id = None
    rebuild_url = None
    redeploy_id = None
    redeploy_url = None
    new_release_seen_at = None  # when the rebuild→release chain produces new release

    checks = []
    had_unhealthy = False
    consecutive_ok = 0
    alert_fired = False
    agent_started = False
    last_alert_poll = datetime.min
    last_agent_poll = datetime.min
    last_snow_poll  = datetime.min
    last_pr_poll    = datetime.min
    last_pipe_poll  = datetime.min
    overall_done    = False
    rebuild_search_start = None  # set when we know the agent created PR

    def render_phase_strip():
        # 9-step strip
        steps = [
            ("BUILD",      phases["build"]),
            ("RELEASE",    phases["release"]),
            ("DEPLOYED",   phases["deployed"]),
            ("DETECTED",   phases["detected"]),
            ("SNOW",       phases["snow"]),
            ("ROLLBACK",   phases["rollback"]),
            ("FIX PR",     phases["fix_pr"]),
            ("REBUILD",    phases["rebuild"]),
            ("REVALIDATE", phases["revalidate"]),
        ]
        bits = []
        for name, done in steps:
            mark = "[green]✓[/]" if done else "[dim]○[/]"
            color = "green" if done else "dim"
            bits.append(f"{mark} [{color}]{name}[/]")
        return "  " + "  →  ".join(bits)

    with Live(console=console, refresh_per_second=2) as live:
        while not overall_done:
            key = check_key()
            if key in (b"q", b"Q"):
                return False
            now = datetime.now()

            # ---- health probe ----
            code, ms = health_check(url, path)
            healthy = healthy_fn(code, ms)
            checks.append({"ts": datetime.now().strftime("%H:%M:%S"),
                           "code": code, "ms": ms, "ok": healthy})
            if len(checks) > 20:
                checks.pop(0)

            if not healthy:
                had_unhealthy = True
                consecutive_ok = 0
                if not phases["detected"]:
                    phases["detected"] = True
                    timeline.add(f"❌ Regression detected on {service_name} ({code}/{ms:.0f}ms)", "red bold")
            else:
                consecutive_ok += 1

            # ---- alert detection ----
            if alert_name and not alert_fired and (now - last_alert_poll).seconds >= 10:
                last_alert_poll = now
                fired, aid, _ = poll_alert(alert_name, sim_start)
                if fired:
                    alert_fired = True
                    if aid:
                        portal = f"https://portal.azure.com/#blade/Microsoft_Azure_Monitoring/AlertDetailsTemplateBlade/alertId/{aid.replace('/', '%2F')}"
                        timeline.add(f"🚨 Azure Monitor alert FIRED — [link={portal}]view alert[/link]", "red bold")
                    else:
                        timeline.add("🚨 Azure Monitor alert FIRED", "red bold")

            # ---- agent thread detection ----
            if not agent_started and (now - last_agent_poll).seconds >= 10:
                last_agent_poll = now
                found, thread_id = poll_agent_thread(service_name, sim_start)
                if found:
                    agent_started = True
                    if thread_id:
                        thread_url = f"{SRE_AGENT_THREAD_BASE}/{thread_id}"
                        timeline.add(f"🤖 deployment-validator picked up — [link={thread_url}]view thread[/link]", "yellow bold")
                    else:
                        timeline.add("🤖 deployment-validator picked up — investigating", "yellow bold")

            # ---- SNOW INC detection ----
            if not phases["snow"] and (now - last_snow_poll).seconds >= 15:
                last_snow_poll = now
                inc, _ = poll_snow_incident_for(sim_start, contains=service_name)
                if inc:
                    snow_inc = inc
                    snow_url = snow_inc_url(inc)
                    phases["snow"] = True
                    timeline.add(f"📋 SNOW incident created: {inc} — [link={snow_url}]open ticket[/link]", "magenta bold")

            # ---- ROLLBACK + RESTORED detection (consecutive_ok after unhealthy) ----
            if had_unhealthy and consecutive_ok >= RECOVERY_THRESHOLD and not phases["rollback"]:
                phases["rollback"] = True
                phases["restored"] = True
                timeline.add(f"♻️  Rollback executed — service restored", "green bold")
                rebuild_search_start = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

            # ---- FIX PR detection (Phase B starts after rollback) ----
            if phases["rollback"] and not phases["fix_pr"] and (now - last_pr_poll).seconds >= 20:
                last_pr_poll = now
                pid, src, title = poll_ado_pr(sim_start,
                                              source_branch_contains=branch_hint or service_name)
                if pid:
                    pr_id = pid
                    pr_url = ado_pr_url(pid)
                    phases["fix_pr"] = True
                    timeline.add(f"📝 Fix PR opened: !{pid} {title} — [link={pr_url}]review PR[/link]", "cyan bold")

            # ---- REBUILD detection (new build run after rebuild_search_start) ----
            if phases["fix_pr"] and not phases["rebuild"] and rebuild_search_start \
                    and (now - last_pipe_poll).seconds >= 15:
                last_pipe_poll = now
                rid, status, _ = poll_latest_pipeline_run("PowerGrid-Build", rebuild_search_start)
                if rid and (build_info is None or rid != build_info.get("build_id")):
                    rebuild_id = rid
                    rebuild_url = ado_pipeline_url(rid)
                    phases["rebuild"] = True
                    timeline.add(f"🔨 Rebuild #{rid} triggered — [link={rebuild_url}]view[/link]", "yellow")

            # ---- REDEPLOY detection (new release after rebuild) ----
            if phases["rebuild"] and not phases["redeploy"] and (now - last_pipe_poll).seconds >= 15:
                rid, status, result = poll_latest_pipeline_run("PowerGrid-Release", rebuild_search_start)
                if rid and (build_info is None or rid != build_info.get("release_id")):
                    redeploy_id = rid
                    redeploy_url = ado_pipeline_url(rid)
                    if status == "completed" and result == "succeeded":
                        phases["redeploy"] = True
                        new_release_seen_at = datetime.now()
                        timeline.add(f"🚀 Auto-redeployed via release #{rid} — [link={redeploy_url}]view[/link]", "green")

            # ---- REVALIDATE: after redeploy, watch for sustained healthy ----
            if phases["redeploy"] and not phases["revalidate"]:
                # Fresh consecutive-ok count after redeploy time
                ok_after = sum(1 for c in checks
                               if c["ok"] and datetime.strptime(c["ts"], "%H:%M:%S").time()
                               >= new_release_seen_at.time())
                if ok_after >= RECOVERY_THRESHOLD:
                    phases["revalidate"] = True
                    timeline.add(f"🎉 Re-validation passed — fix verified by deployment-validator", "green bold")
                    overall_done = True

            # If Phase B never starts within 8 min after rollback, declare done
            if phases["restored"] and not phases["fix_pr"] and rebuild_search_start:
                elapsed = (datetime.utcnow() - datetime.strptime(
                    rebuild_search_start, "%Y-%m-%dT%H:%M:%SZ")).total_seconds()
                if elapsed > 480:
                    timeline.add("⏱  Phase B (PR+rebuild) did not occur within 8 min — Phase A complete", "dim")
                    overall_done = True

            # ---- build display ----
            grid = Table.grid(padding=1)
            grid.add_column()

            grid.add_row(Panel(
                f"[bold cyan]🛠  END-TO-END DEPLOYMENT WATCH[/]  —  {service_name}\n"
                "[dim]q = return to menu[/]",
                border_style="cyan", width=92))

            grid.add_row(Text.from_markup(render_phase_strip()))

            color = "green" if healthy else "red"
            icon = "✅" if healthy else "❌"
            label = ok_label if healthy else bad_label
            grid.add_row(Text.from_markup(
                f"  {icon} [{color} bold]{service_name}: {label}[/] "
                f"({code} / {ms:.0f}ms)"))

            ht = Table(box=box.ROUNDED, border_style="dim", width=64)
            ht.add_column("Time", style="dim", width=9)
            ht.add_column("Status", width=7, justify="center")
            ht.add_column("Latency", width=10, justify="right")
            ht.add_column("Result", width=10, justify="center")
            for c in checks[-8:]:
                sc = "green" if c["ok"] else "red"
                ht.add_row(c["ts"], f"[{sc}]{c['code']}[/]", f"{c['ms']:.0f}ms",
                           f"[green]{ok_label}[/]" if c["ok"] else f"[red]{bad_label}[/]")
            grid.add_row(ht)

            # Artifacts panel
            artifacts = []
            if build_info:
                artifacts.append(f"  🔨 [link={build_info['build_url']}]Build #{build_info['build_id']}[/]")
                artifacts.append(f"  🚀 [link={build_info['release_url']}]Release #{build_info['release_id']}[/]")
            if snow_inc:
                artifacts.append(f"  📋 [link={snow_url}]SNOW {snow_inc}[/]")
            if pr_id:
                artifacts.append(f"  📝 [link={pr_url}]PR !{pr_id}[/]")
            if rebuild_id:
                artifacts.append(f"  🔨 [link={rebuild_url}]Rebuild #{rebuild_id}[/]")
            if redeploy_id:
                artifacts.append(f"  🚀 [link={redeploy_url}]Re-deploy #{redeploy_id}[/]")
            if artifacts:
                grid.add_row(Panel(
                    "\n".join(artifacts),
                    title="[dim]Artifacts[/]",
                    border_style="dim", width=92))

            grid.add_row(timeline.render())
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


    if not preflight_check(needs_ado=True, needs_services=[("outage-api", OUTAGE_API_URL)]):
        console.input("[dim]  Press Enter...[/]"); return

    build_info = run_build_release("crash", "outage-api")
    if not build_info:
        return
    console.print("[bold yellow]  ⚡ RELEASE TRIGGER FIRED — deployment-validator investigating[/]\n")
    time.sleep(1)

    if monitor_deployment_e2e(OUTAGE_API_URL, "/outages", "outage-api",
                              alert_name="http-5xx",
                              build_info=build_info,
                              branch_hint="outage"):
        show_result("🎉", "DEPLOYMENT VALIDATED — FULL LOOP CLOSED!", [
            "deployment-validator end-to-end:",
            "  Phase A (immediate mitigation):",
            "    - Detected /outages 500s after deploy",
            "    - Created SNOW incident with buildId tag",
            "    - Plotted ONE consolidated metrics chart",
            "    - Rolled back to previous healthy revision",
            "  Phase B (long-term fix):",
            "    - Diagnosed AttributeError in _enrich_outage()",
            "    - Opened fix PR in ADO repo",
            "    - Triggered PowerGrid-Build with fix",
            "    - Build succeeded → release auto-chained",
            "    - Re-validated new deployment → healthy",
            "",
            "Click any link in the timeline above to drill into the artifact.",
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

    if not preflight_check(needs_ado=True, needs_services=[("grid-status-api", GRID_API_URL)]):
        console.input("[dim]  Press Enter...[/]"); return

    build_info = run_build_release("perf", "grid-status-api")
    if not build_info:
        return
    console.print("[bold yellow]  ⚡ RELEASE TRIGGER FIRED — deployment-validator investigating[/]\n")
    time.sleep(1)

    if monitor_deployment_e2e(GRID_API_URL, "/regions", "grid-status-api",
                              healthy_fn=lambda c, ms: c == 200 and ms < 1000,
                              ok_label="FAST", bad_label="SLOW",
                              alert_name="high-latency",
                              build_info=build_info,
                              branch_hint="grid"):
        show_result("🎉", "PERFORMANCE RESTORED — FULL LOOP CLOSED!", [
            "deployment-validator end-to-end:",
            "  Phase A: detected P95 > 1s → SNOW + chart → rollback",
            "  Phase B: diagnosed O(n²) checksum → PR → rebuild → re-validated",
            "Response time: 5200ms → 85ms after rollback",
            "",
            "Click any link in the timeline above to drill into the artifact.",
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

    if not preflight_check(needs_ado=True):
        console.input("[dim]  Press Enter...[/]"); return

    build_info = run_build_release("config", "notification-svc")
    if not build_info:
        return
    console.print("[bold yellow]  ⚡ RELEASE TRIGGER FIRED — deployment-validator investigating[/]\n")
    time.sleep(1)

    if monitor_deployment_e2e(NOTIFY_URL, "/send", "notification-svc",
                              alert_name="http-5xx",
                              build_info=build_info,
                              branch_hint="notif"):
        show_result("🎉", "CONFIG FIXED — FULL LOOP CLOSED!", [
            "deployment-validator end-to-end:",
            "  Phase A: detected /send timeouts → SNOW + chart → rollback",
            "  Phase B: diagnosed GATEWAY_PORT mismatch → PR → rebuild → re-validated",
            "",
            "Click any link in the timeline above to drill into the artifact.",
        ])

# ═══════════════════════════════════════════════════════════
#  SCENARIO 4 — Disk Pressure (VM Alert)
# ═══════════════════════════════════════════════════════════
def scenario_disk():
    show_backstory("💾", "DISK PRESSURE — VM ALERT",
        "The grid management server (gridmgmt01) runs SCADA data\n"
        "collection and stores raw telemetry locally before forwarding\n"
        "to Azure Data Explorer. Over the past week, a misconfigured\n"
        "log rotation policy let C:\\data\\grid-logs grow unchecked.\n\n"
        "Combined with nightly SCADA backups that were never pruned,\n"
        "the C: drive is now at 90%+ capacity and climbing.",

        "1. We inject disk pressure on the VM via az vm run-command\n"
        "2. Azure Monitor fires a disk-pressure alert (< 15% free)\n"
        "3. Alert trigger → vm-ops-agent picks up the alert\n"
        "4. Agent runs commands on the VM and investigates\n"
        "5. Agent cleans old logs and backups\n"
        "6. Agent documents remediation in SNOW")

    if not preflight_check(needs_vm=True):
        console.input("[dim]  Press Enter...[/]"); return

    console.print("[bold cyan]  ▶ Simulating disk pressure on Windows VM...[/]")
    try:
        ps_script = (
            # Clean any previous injection files first
            "Remove-Item C:\\data -Recurse -Force -ErrorAction SilentlyContinue; "
            "New-Item -ItemType Directory -Path C:\\data\\grid-logs, C:\\data\\scada-backups -Force | Out-Null; "
            "$disk = Get-CimInstance Win32_LogicalDisk -Filter \\\"DeviceID='C:'\\\"; "
            "$totalGB = [math]::Floor($disk.Size / 1073741824); "
            "$freeGB = [math]::Floor($disk.FreeSpace / 1073741824); "
            "$freePct = [math]::Round(($disk.FreeSpace / $disk.Size) * 100, 1); "
            # Already under pressure? Skip filling
            "if ($freePct -lt 15) { Write-Output \\\"ALREADY_LOW:$freePct\\\"; exit 0 }; "
            # Target: leave only 8% free (well under 15% threshold)
            "$targetFreeGB = [math]::Max(5, [math]::Floor($totalGB * 0.08)); "
            "$fillGB = $freeGB - $targetFreeGB; "
            "if ($fillGB -lt 5) { Write-Output \\\"ERROR_NOT_ENOUGH:free=${freeGB}GB,need=${fillGB}GB\\\"; exit 1 }; "
            # Create 2 large files (70/30 split)
            "$mainBytes = [math]::Floor($fillGB * 0.70) * 1073741824; "
            "$scadaBytes = [math]::Floor($fillGB * 0.30) * 1073741824; "
            "fsutil file createnew C:\\data\\grid-logs\\grid-manager.log $mainBytes | Out-Null; "
            "fsutil file createnew C:\\data\\scada-backups\\scada-full-2026-04-01.bak $scadaBytes | Out-Null; "
            # Verify the result
            "$after = Get-CimInstance Win32_LogicalDisk -Filter \\\"DeviceID='C:'\\\"; "
            "$afterPct = [math]::Round(($after.FreeSpace / $after.Size) * 100, 1); "
            "$afterFreeGB = [math]::Round($after.FreeSpace / 1073741824, 1); "
            "if ($afterPct -lt 15) { Write-Output \\\"DISK_FILLED:${afterPct}pct:${afterFreeGB}GB\\\" } "
            "else { Write-Output \\\"FILL_INSUFFICIENT:${afterPct}pct:${afterFreeGB}GB\\\" }"
        )
        result = subprocess.run(
            f'az vm run-command invoke --resource-group {RESOURCE_GROUP} '
            f'--name {VM_NAME} --command-id RunPowerShellScript '
            f'--scripts "{ps_script}" '
            f'--query "value[0].message" -o tsv',
            shell=True, timeout=180, capture_output=True, text=True
        )
        out = result.stdout
        if "DISK_FILLED" in out:
            # Parse: DISK_FILLED:8.2pct:10.5GB
            pct = out.split("DISK_FILLED:")[1].split("pct")[0] if "pct" in out else "?"
            console.print(f"[green]  ✓ Disk pressure injected — {pct}% free (threshold: 15%)[/]\n")
        elif "ALREADY_LOW" in out:
            pct = out.split("ALREADY_LOW:")[1].split()[0] if "ALREADY_LOW:" in out else "?"
            console.print(f"[green]  ✓ Disk already under pressure ({pct}% free) — skipping fill[/]\n")
        elif "FILL_INSUFFICIENT" in out:
            pct = out.split("FILL_INSUFFICIENT:")[1].split("pct")[0] if "pct" in out else "?"
            console.print(f"[red]  ✗ Fill incomplete — {pct}% free (need < 15%). Retry or check disk.[/]")
            console.input("[dim]  Press Enter...[/]"); return
        elif "ERROR_NOT_ENOUGH" in out:
            console.print(f"[red]  ✗ Not enough free space to simulate pressure[/]")
            console.input("[dim]  Press Enter...[/]"); return
        elif "OperationNotAllowed" in out or "not running" in out.lower():
            console.print("[red]  ✗ VM is not running![/]")
            console.input("[dim]  Press Enter...[/]"); return
        else:
            console.print(f"[yellow]  ⚠ Unexpected: {out[:120]}[/]")
            console.input("[dim]  Press Enter...[/]"); return
    except subprocess.TimeoutExpired:
        console.print("[red]  ✗ Script timed out[/]")
        console.input("[dim]  Press Enter...[/]"); return
    except Exception as e:
        console.print(f"[red]  ✗ Failed: {e}[/]")
        console.input("[dim]  Press Enter...[/]"); return

    # Phase 2: Wait for Azure Monitor alert to fire
    console.print("[bold yellow]  ⏳ Waiting for Azure Monitor disk alert to fire...[/]\n")
    
    sim_start = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    timeline = EventTimeline()
    timeline.add("Disk pressure injected — OS disk at ~91%", "red")
    timeline.add("⏳ Waiting for alert-powergrid-disk-pressure to fire...", "yellow")
    
    alert_fired = False
    agent_started = False
    alert_resolved = False
    tracked_alert_id = None
    checks = []
    recovered = False
    last_alert_poll = datetime.now()  # delay first poll
    last_agent_poll = datetime.now()
    last_resolve_poll = datetime.now()

    with Live(console=console, refresh_per_second=1) as live:
        while not recovered:
            key = check_key()
            if key in (b"q", b"Q"):
                break

            now = datetime.now()

            # Phase A: Poll for FIRED alert (fresh, after sim_start)
            if not alert_fired and (now - last_alert_poll).seconds >= 10:
                last_alert_poll = now
                fired, aid, _ = poll_alert("disk-pressure", sim_start, "Fired")
                if fired:
                    alert_fired = True
                    tracked_alert_id = aid
                    timeline.add("🚨 ALERT FIRED — alert-powergrid-disk-pressure (Sev2)", "red bold")
                    # Build clickable Azure portal link
                    alert_portal_url = f"https://portal.azure.com/#blade/Microsoft_Azure_Monitoring/AlertDetailsTemplateBlade/alertId/{aid.replace('/', '%2F')}"
                    timeline.add(f"🔗 [link={alert_portal_url}]View alert in Azure Portal[/link]", "cyan")

            # Phase B: Poll for SRE Agent thread
            if alert_fired and not agent_started and (now - last_agent_poll).seconds >= 10:
                last_agent_poll = now
                found, thread_id = poll_agent_thread("disk", sim_start)
                if found:
                    agent_started = True
                    timeline.add("🤖 SRE Agent picked up the alert — investigating!", "yellow bold")
                    if thread_id:
                        thread_url = f"{SRE_AGENT_THREAD_BASE}/{thread_id}"
                        timeline.add(f"🔗 [link={thread_url}]View agent thread[/link]", "cyan")

            # Phase C: Poll for same alert to become RESOLVED
            if alert_fired and tracked_alert_id and not alert_resolved and (now - last_resolve_poll).seconds >= 10:
                last_resolve_poll = now
                if poll_alert_by_id(tracked_alert_id, "Resolved"):
                    alert_resolved = True
                    recovered = True
                    timeline.add("🎉 DISK PRESSURE RESOLVED — alert auto-resolved!", "green bold")

            # Poll disk usage from Log Analytics (every 15s, uses cached Perf data)
            disk_pct = None
            if len(checks) == 0 or (len(checks) > 0 and (datetime.now() - checks[-1].get("_poll_time", datetime.min)).seconds >= 15):
                try:
                    wsid = subprocess.run(
                        f'az monitor log-analytics workspace show -g {RESOURCE_GROUP} -n {LAW_NAME} --query customerId -o tsv',
                        shell=True, timeout=10, capture_output=True, text=True
                    ).stdout.strip()
                    result = subprocess.run(
                        f'az monitor log-analytics query -w {wsid} --analytics-query '
                        '"Perf | where Computer == \'gridmgmt01\' and ObjectName == \'LogicalDisk\' and CounterName == \'% Free Space\' and InstanceName == \'C:\' | top 1 by TimeGenerated | project CounterValue" '
                        '-o tsv',
                        shell=True, timeout=15, capture_output=True, text=True
                    )
                    for line in result.stdout.splitlines():
                        line = line.strip()
                        try:
                            free_pct = float(line)
                            disk_pct = int(100 - free_pct)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

                if disk_pct is not None:
                    checks.append({
                        "ts": datetime.now().strftime("%H:%M:%S"),
                        "pct": disk_pct,
                        "_poll_time": datetime.now(),
                    })
                    if len(checks) > 20:
                        checks.pop(0)

            # Build display
            grid = Table.grid(padding=1)
            grid.add_column()

            grid.add_row(Panel(
                f"[bold cyan]💾 DISK PRESSURE MONITOR[/]  —  {VM_NAME}\n"
                "[dim]q = return to menu[/]",
                border_style="cyan", width=68,
            ))

            # Alert + Agent status line
            if recovered:
                grid.add_row(Panel(
                    "[bold green]🎉🎉🎉  DISK PRESSURE RESOLVED!  🎉🎉🎉[/]\n\n"
                    "[green]The SRE Agent cleaned up the disk![/]",
                    border_style="green bold", width=68,
                ))
            else:
                alert_status = "[green]🚨 FIRED[/]" if alert_fired else "[yellow]⏳ pending...[/]"
                agent_status = "[green]🤖 investigating[/]" if agent_started else "[dim]waiting for alert[/]"
                grid.add_row(Text(
                    f"  Alert: {alert_status}   Agent: {agent_status}",
                    style="bold"))

            # Current status
            if checks:
                last = checks[-1]
                pct = last["pct"]
                if pct > 85:
                    color, icon, label = "red", "🔴", "CRITICAL"
                elif pct > 70:
                    color, icon, label = "yellow", "🟡", "WARNING"
                else:
                    color, icon, label = "green", "🟢", "HEALTHY"
                grid.add_row(Text(
                    f"  {icon} OS Disk: {pct}% used   [{label}]",
                    style=f"{color} bold"))

                # Sparkline bar
                bar_width = 40
                filled = int(pct / 100 * bar_width)
                bar = f"[{color}]{'█' * filled}{'░' * (bar_width - filled)}[/] {pct}%"
                grid.add_row(Text(f"  {bar}"))

            # History table
            if checks:
                dt = Table(box=box.ROUNDED, border_style="dim", width=50)
                dt.add_column("Time", style="dim", width=9)
                dt.add_column("Disk %", width=8, justify="right")
                dt.add_column("Bar", width=25)
                for c in checks[-8:]:
                    p = c["pct"]
                    clr = "red" if p > 85 else "yellow" if p > 70 else "green"
                    bw = 20
                    bf = int(p / 100 * bw)
                    dt.add_row(
                        c["ts"],
                        f"[{clr}]{p}%[/]",
                        f"[{clr}]{'█' * bf}{'░' * (bw - bf)}[/]",
                    )
                grid.add_row(dt)

            grid.add_row(Text(
                "  🤖 vm-ops-agent → sre.azure.com → sre-zavapower-ops",
                style="dim"))
            grid.add_row(timeline.render())
            live.update(grid)
            time.sleep(2)

    show_result("🎉", "DISK PRESSURE RESOLVED!", [
        "SRE Agent (vm-ops-agent):",
        "- Detected disk at 94% via Azure Monitor alert",
        f"- Ran PowerShell diagnostics on {VM_NAME}",
        "- Cleaned C:\\data\\grid-logs (recovered old logs and core dumps)",
        "- Pruned old SCADA backups from C:\\data\\scada-backups",
        "- Removed stale meter data from C:\\data\\meter-data",
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

        "1. We cap replicas to 1 (current provisioned capacity)\n"
        "2. We blast grid-status-api with 100 concurrent clients\n"
        "3. Response times climb as the 0.25 vCPU saturates\n"
        "4. Synthetic monitoring detects the slowness\n"
        "5. HTTP trigger fires → SRE Agent investigates autonomously\n"
        "6. Agent finds NO code defect — scales infrastructure to resolve")


    if not preflight_check(needs_services=[("grid-status-api", GRID_API_URL)], needs_token=True):
        console.input("[dim]  Press Enter...[/]"); return

    # Cap replicas to 1 so autoscale doesn't rescue the service
    console.print("[bold cyan]  ▶ Capping grid-status-api to 1 replica (simulating provisioned capacity)...[/]")
    try:
        result = subprocess.run(
            f'az containerapp update -n ca-{WORKLOAD}-grid -g rg-{WORKLOAD} '
            f'--max-replicas 1 --output none',
            shell=True, timeout=30, capture_output=True, text=True
        )
        if result.returncode == 0:
            console.print("[green]  ✓ Max replicas capped to 1[/]")
        else:
            console.print(f"[yellow]  ⚠ Could not cap replicas (may already be 1)[/]")
    except Exception:
        pass

    # Get auth token BEFORE starting load (az cli is slow under CPU pressure)
    console.print("[dim]  Acquiring SRE Agent auth token...[/]")
    try:
        sre_token = subprocess.run(
            'az account get-access-token --resource "https://azuresre.ai" --query accessToken -o tsv',
            shell=True, capture_output=True, text=True, timeout=30
        ).stdout.strip()
        if not sre_token:
            console.print("[red]  ✗ Failed to get token. Run: az login[/]")
            console.input("[dim]  Press Enter...[/]"); return
    except Exception as e:
        console.print(f"[red]  ✗ Token error: {e}[/]")
        console.input("[dim]  Press Enter...[/]"); return

    # Blast with high concurrency to overwhelm the 0.25 vCPU single replica
    console.print("[bold cyan]  ▶ Generating 50x traffic spike (100 concurrent clients)...[/]")
    console.print(f"  [dim]Open in browser to see impact:[/] [link=https://app-powergrid-portal.azurewebsites.net]https://app-powergrid-portal.azurewebsites.net[/link]\n")
    stop_event = threading.Event()
    request_count = [0]  # mutable counter shared across threads

    def worker():
        """Simulate a customer repeatedly checking grid status."""
        while not stop_event.is_set():
            try:
                requests.get(f"{GRID_API_URL}/regions", timeout=15)
                request_count[0] += 1
            except Exception:
                request_count[0] += 1
            time.sleep(0.05)  # ~20 req/s per worker

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(100)]
    for t in threads:
        t.start()

    # Separate probe thread — short timeout so we get fast readings even under load
    probe_result = [0, 0.0]  # [status_code, latency_ms]
    probe_lock = threading.Lock()

    def prober():
        while not stop_event.is_set():
            start = time.time()
            try:
                r = requests.get(f"{GRID_API_URL}/health", timeout=5)
                elapsed = (time.time() - start) * 1000
                with probe_lock:
                    probe_result[0] = r.status_code
                    probe_result[1] = elapsed
            except requests.exceptions.Timeout:
                elapsed = (time.time() - start) * 1000
                with probe_lock:
                    probe_result[0] = 0
                    probe_result[1] = elapsed  # show actual wait time, not 0
            except Exception:
                with probe_lock:
                    probe_result[0] = 0
                    probe_result[1] = (time.time() - start) * 1000
            time.sleep(0.5)

    probe_thread = threading.Thread(target=prober, daemon=True)
    probe_thread.start()

    sim_start = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    timeline = EventTimeline()
    timeline.add("Replicas capped to 1 (provisioned capacity)", "cyan")
    timeline.add("Traffic spike started — 100 concurrent clients (~2000 req/s)", "cyan")
    checks = []
    had_slow = False
    trigger_sent = False
    agent_thread_id = None

    # SRE Agent HTTP trigger URL
    SRE_TRIGGER_URL = "https://sre-zavapower-ops--5a379588.bc75887b.eastus2.azuresre.ai/api/v1/httptriggers/trigger/9a276c65-c2ed-4e6e-b478-07e79a85a495"

    try:
        with Live(console=console, refresh_per_second=2) as live:
            while True:
                key = check_key()
                if key in (b"q", b"Q"):
                    break

                # Read latest probe result (non-blocking)
                with probe_lock:
                    code, ms = probe_result[0], probe_result[1]

                # Record every reading (including timeouts where ms > 0)
                if ms > 0:
                    is_slow = code != 200 or ms > 500
                    # Only add if timestamp changed (avoid duplicate entries)
                    ts_now = datetime.now().strftime("%H:%M:%S")
                    if not checks or checks[-1]["ts"] != ts_now:
                        checks.append({"ts": ts_now,
                                        "code": code, "ms": ms, "slow": is_slow})
                        if len(checks) > 20:
                            checks.pop(0)

                    if is_slow and not had_slow:
                        had_slow = True
                        timeline.add(f"⚠️ High latency detected: {ms:.0f}ms", "red")

                    # Once we detect sustained slowness (3+ slow checks), fire the HTTP trigger
                    slow_count = sum(1 for c in checks if c["slow"])
                    if slow_count >= 3 and not trigger_sent:
                        trigger_sent = True
                        timeline.add("🔔 Synthetic test FAILED — triggering SRE Agent...", "red bold")
                        try:
                            import json as _json
                            payload = _json.dumps({
                                "service": "grid-status-api",
                                "endpoint": f"{GRID_API_URL}/regions",
                                "containerApp": f"ca-{WORKLOAD}-grid",
                                "resourceGroup": f"rg-{WORKLOAD}",
                                "observedLatencyMs": int(ms),
                                "thresholdMs": 1000,
                                "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                            })
                            # Refresh token if close to expiry
                            sre_token = _token_mgr.get_token() or sre_token
                            r = requests.post(SRE_TRIGGER_URL,
                                headers={"Authorization": f"Bearer {sre_token}", "Content-Type": "application/json"},
                                data=payload, timeout=15)
                            if r.status_code in (200, 201, 202):
                                resp = r.json()
                                agent_thread_id = resp.get("threadId", "")
                                timeline.add("🤖 SRE Agent investigating (autonomous)", "yellow bold")
                                if agent_thread_id:
                                    thread_url = f"{SRE_AGENT_THREAD_BASE}/{agent_thread_id}"
                                    timeline.add(f"🔗 [link={thread_url}]View agent thread[/link]", "cyan")
                            else:
                                timeline.add(f"⚠️ Trigger failed: HTTP {r.status_code}", "red")
                        except Exception as e:
                            timeline.add(f"⚠️ Trigger error: {str(e)[:40]}", "red")

                # Build display
                grid = Table.grid(padding=1)
                grid.add_column()

                color = "red" if code == 0 or ms > 2000 else "yellow" if ms > 500 else "green"
                status_label = "TIMEOUT" if code == 0 else str(code)
                reqs = request_count[0]
                grid.add_row(Text(
                    f"  📈 grid-status-api: {status_label} / {ms:.0f}ms   [{reqs:,} reqs sent]",
                    style=f"{color} bold"))

                # Trigger + agent status line
                t_status = "[green]🔔 TRIGGERED[/]" if trigger_sent else "[yellow]⏳ detecting...[/]"
                ag_status = "[green]🤖 autonomous[/]" if agent_thread_id else "[dim]waiting[/]"
                grid.add_row(Text(f"  Synthetic test: {t_status}   Agent: {ag_status}"))

                ht = Table(box=box.ROUNDED, border_style="dim", width=64)
                ht.add_column("Time", style="dim", width=9)
                ht.add_column("Status", width=7)
                ht.add_column("Latency", width=10, justify="right")
                ht.add_column("", width=8, justify="center")
                for c in checks[-8:]:
                    lc = "red" if c["code"] == 0 or c["ms"] > 2000 else "yellow" if c["ms"] > 500 else "green"
                    status = "TIMEOUT" if c["code"] == 0 else str(c["code"])
                    ht.add_row(c["ts"], status,
                               f"[{lc}]{c['ms']:.0f}ms[/]",
                               "[red]🐌[/]" if c["slow"] else "[green]⚡[/]")
                grid.add_row(ht)
                grid.add_row(timeline.render())
                grid.add_row(Text("  [dim]q = stop load and return to menu[/]"))
                live.update(grid)

                time.sleep(2)
    finally:
        stop_event.set()
        # Restore maxReplicas so autoscale works again
        try:
            subprocess.run(
                f'az containerapp update -n ca-{WORKLOAD}-grid -g rg-{WORKLOAD} '
                f'--max-replicas 3 --output none',
                shell=True, timeout=30, capture_output=True, text=True
            )
        except Exception:
            pass

    show_result("📈", "LOAD SPIKE — SRE AGENT INVESTIGATING", [
        "SRE Agent (autonomous via HTTP trigger):",
        "- Synthetic test detected 9s+ response time on grid-status-api",
        "- Agent triggered autonomously to investigate and resolve",
        "- Agent will query App Insights, check CPU, replica count",
        "- Expected RCA: single 0.25 vCPU replica saturated by traffic",
        "- Expected fix: scale replicas, increase CPU, add autoscale",
        "",
        "Check sre.azure.com for the live investigation thread.",
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


    if not preflight_check(needs_ado=True):
        console.input("[dim]  Press Enter...[/]"); return

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
#  SCENARIO 7 — ServiceNow Laptop Replacement (from Azure Friday)
# ═══════════════════════════════════════════════════════════

_SN_STATES = {
    "1": ("New",         "yellow"),
    "2": ("In Progress", "cyan"),
    "3": ("On Hold",     "bright_yellow"),
    "6": ("Resolved",    "green"),
    "7": ("Closed",      "green bold"),
}

def scenario_servicenow():
    show_backstory("🎫", "SERVICENOW — LAPTOP REPLACEMENT",
        "Employee Shamir Abdul Aziz from the Engineering department\n"
        "submitted a laptop replacement request. His Dell XPS 15 has\n"
        "a failing battery (20 min life), frequent blue screens, and\n"
        "an intermittent trackpad. Device is over 3 years old.\n\n"
        "This ticket goes to the IT Support SRE Agent (sre-zavapower-\n"
        "itsupport) which uses ServiceNow as its native incident platform.",

        "1. We create a laptop replacement ticket in ServiceNow\n"
        "2. SRE Agent (sre-zavapower-itsupport) polls and picks it up\n"
        "3. Agent reads ticket → checks warranty via CheckWarranty tool\n"
        "4. Agent fills laptop request form via Browser Operator\n"
        "5. Agent updates and resolves the ServiceNow ticket\n"
        "6. Agent sends confirmation email to the employee")

    if not preflight_check(needs_snow=True):
        console.input("[dim]  Press Enter...[/]"); return

    ticket_id = None
    ticket_num = None
    poll_log = []
    timeline = EventTimeline()

    def _create():
        nonlocal ticket_id, ticket_num
        payload = {
            "short_description": "Laptop replacement request - Shamir Abdul Aziz",
            "description": (
                "Employee Shamir Abdul Aziz (saziz@microsoft.com, EMP-10042, "
                "Engineering Department) is requesting a laptop replacement.\n\n"
                "Current laptop: Dell XPS 15 9530\n"
                "Serial Number: SN-2023-XPS-4471\n"
                "Issue: Laptop battery only lasts 20 minutes, frequent blue "
                "screens during video calls, and the trackpad is unresponsive "
                "intermittently. Device was purchased in March 2023 and is "
                "over 3 years old.\n\n"
                "This laptop is critical for daily work as a Principal PM and "
                "the issues are significantly impacting productivity.\n\n"
                "Please process this replacement request."
            ),
            "urgency": "2",
            "impact": "2",
            "category": "Hardware",
            "subcategory": "Laptop",
            "caller_id": "admin",
            "assignment_group": "IT Support",
        }
        try:
            r = requests.post(
                f"{SN_URL}/api/now/table/incident",
                json=payload,
                auth=(SN_USER, SN_PASS),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=15,
            )
            if r.status_code in (200, 201):
                d = r.json()["result"]
                ticket_id = d["sys_id"]
                ticket_num = d.get("number", "?")
                return True
            console.print(f"[red]  SNOW error {r.status_code}: {r.text[:200]}[/]")
        except Exception as e:
            console.print(f"[red]  SNOW error: {e}[/]")
        return False

    def _poll():
        if not ticket_id:
            return None
        try:
            r = requests.get(
                f"{SN_URL}/api/now/table/incident/{ticket_id}",
                auth=(SN_USER, SN_PASS),
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()["result"]
        except Exception:
            pass
        return None

    # Create the ticket
    console.print("[bold cyan]  ▶ Creating ServiceNow ticket...[/]")
    if not _create():
        console.input("[dim]  Press Enter...[/]"); return
    console.print(f"[green]  ✓ Ticket {ticket_num} created in ServiceNow[/]")
    console.print(f"[dim]  URL: {SN_URL}/incident.do?sys_id={ticket_id}[/]\n")
    timeline.add(f"Ticket {ticket_num} created", "cyan")
    timeline.add("🤖 sre-zavapower-itsupport polling for new tickets...", "yellow")

    # Live poll until resolved
    try:
        with Live(console=console, refresh_per_second=1) as live:
            while True:
                key = check_key()
                if key in (b"q", b"Q"):
                    break
                if key == b"n":
                    timeline.add("⌨️ Creating new ticket...", "yellow bold")
                    _create()
                    if ticket_num:
                        timeline.add(f"Ticket {ticket_num} created", "cyan")

                data = _poll()
                if data:
                    st = data.get("state", "1")
                    sname, scolor = _SN_STATES.get(st, (f"Unknown({st})", "dim"))
                    
                    # Track state changes
                    prev_state = poll_log[-1]["state"] if poll_log else None
                    if sname != prev_state:
                        timeline.add(f"Ticket state → {sname}", scolor)
                    
                    poll_log.append({"ts": datetime.now().strftime("%H:%M:%S"),
                                     "state": sname, "color": scolor})
                    if len(poll_log) > 20:
                        poll_log.pop(0)

                grid = Table.grid(padding=1)
                grid.add_column()
                grid.add_row(Panel(
                    "[bold cyan]🎫 SERVICENOW LAPTOP REPLACEMENT[/]\n"
                    "[dim]q = quit   n = new ticket[/]",
                    border_style="cyan",
                ))

                if data:
                    st = data.get("state", "1")
                    sname, scolor = _SN_STATES.get(st, (f"Unknown({st})", "dim"))
                    assigned = data.get("assigned_to", "")
                    if isinstance(assigned, dict):
                        assigned = assigned.get("display_value", "Unassigned")
                    assigned = assigned or "Unassigned"
                    resolved = st in ("6", "7")

                    lines = [
                        f"  Ticket:      [bold]{ticket_num}[/]",
                        f"  State:       [{scolor}]{sname}[/]",
                        f"  Short Desc:  {data.get('short_description', '')[:60]}",
                        f"  Urgency:     {data.get('urgency', '')}",
                        f"  Assigned To: {assigned}",
                        f"  Updated:     {data.get('sys_updated_on', '')}",
                        f"  URL:         {SN_URL}/incident.do?sys_id={ticket_id}",
                    ]
                    if resolved:
                        notes = data.get("close_notes", "") or ""
                        if notes:
                            lines.append(f"\n  [green]Resolution: {notes[:120]}[/]")

                    grid.add_row(Panel(
                        "\n".join(lines),
                        border_style="green bold" if resolved else "yellow",
                        title="[green bold]✅ RESOLVED[/]" if resolved else f"[yellow]🎫 {ticket_num}[/]",
                    ))

                    if resolved:
                        grid.add_row(Panel(
                            "[bold green]🎉🎉🎉  INCIDENT RESOLVED!  🎉🎉🎉[/]\n\n"
                            "[green]The SRE Agent picked up the ServiceNow incident\n"
                            "and resolved it automatically![/]",
                            border_style="green bold",
                        ))

                    if poll_log:
                        pt = Table(title="[bold]Ticket State History[/]",
                                   box=box.ROUNDED, border_style="dim")
                        pt.add_column("Time", width=10)
                        pt.add_column("State", width=20)
                        for p in poll_log[-10:]:
                            pt.add_row(p["ts"], f"[{p['color']}]{p['state']}[/]")
                        grid.add_row(pt)
                else:
                    grid.add_row(Panel(
                        "[dim]Waiting for ServiceNow response...[/]",
                        border_style="dim",
                    ))

                grid.add_row(Text(
                    "  🤖 it-support-handler → sre.azure.com → sre-zavapower-itsupport",
                    style="dim"))
                grid.add_row(timeline.render())
                live.update(grid)
                time.sleep(3)
    except KeyboardInterrupt:
        pass

# ═══════════════════════════════════════════════════════════
#  SCENARIO 8 — Reset All (Healthy Baseline)
# ═══════════════════════════════════════════════════════════
def _wake_servicenow(timeout=30):
    """Probe ServiceNow PDI. Returns (ok, detail)."""
    try:
        r = requests.get(f"{SN_URL}/api/now/table/incident?sysparm_limit=1",
                         auth=(SN_USER, SN_PASS),
                         headers={"Accept": "application/json"}, timeout=timeout)
        if r.status_code == 200:
            return True, "awake"
        return False, f"status {r.status_code}"
    except requests.exceptions.Timeout:
        return False, "timeout (hibernating)"
    except Exception as e:
        return False, str(e)[:60]


def _wait_for_http_healthy(url, name, timeout_s=90, interval_s=5):
    """Poll {url}/health until 200 or timeout. Returns (ok, status_code, latency_ms, elapsed_s)."""
    start = time.time()
    code, ms = 0, 0
    while (time.time() - start) < timeout_s:
        code, ms = health_check(url)
        if code == 200:
            return True, code, ms, time.time() - start
        time.sleep(interval_s)
    return False, code, ms, time.time() - start


def _wait_for_aca_healthy(app_name, rg, timeout_s=90, interval_s=5):
    """Poll `az containerapp revision list` until the active revision is
    Healthy+Running or timeout. Used for internal-ingress apps that can't be
    probed via HTTP from outside the ACA environment.
    Returns (ok, detail, elapsed_s).
    """
    start = time.time()
    last = "unknown"
    while (time.time() - start) < timeout_s:
        ok, out, err = run_az(
            ["az", "containerapp", "revision", "list", "-n", app_name, "-g", rg,
             "--query", "[?properties.active].{h:properties.healthState,r:properties.runningState,p:properties.provisioningState} | [0]",
             "-o", "json"],
            timeout=20, parse_json=True,
        )
        if ok and isinstance(out, dict):
            h = (out.get("h") or "").lower()
            r = (out.get("r") or "").lower()
            p = (out.get("p") or "").lower()
            last = f"{out.get('h')}/{out.get('r')}/{out.get('p')}"
            if h == "healthy" and r == "running" and p == "provisioned":
                return True, last, time.time() - start
        elif not ok:
            last = (err or "az error")[:60]
        time.sleep(interval_s)
    return False, last, time.time() - start


def scenario_reset():
    console.clear()
    console.print(Panel(
        "\n  Restoring all services to healthy baseline.\n"
        "  This will:\n"
        "  - Wake up ServiceNow PDI (if sleeping)\n"
        "  - Reset all Container App environment variables\n"
        "  - Reset grid-status-api replicas and CPU to baseline\n"
        "  - Disable chaos mode (if active)\n"
        "  - Clean disk pressure files on VM\n"
        "  - Start VM if stopped\n"
        "  - Restore App Service port configuration\n"
        "  - Validate all service health endpoints + ServiceNow\n",
        title="[bold]🧹 RESET ALL — HEALTHY BASELINE[/]",
        border_style="cyan", width=68,
    ))
    console.input("[dim]  Press Enter to proceed...[/]")

    rg = RESOURCE_GROUP
    console.print("\n[bold cyan]  ▶ Resetting all services...[/]")

    # ── Wake up ServiceNow PDI (dev instances sleep after inactivity) ──
    console.print("[dim]  Waking up ServiceNow PDI...[/]", end="")
    sn_ok, sn_detail = _wake_servicenow(timeout=30)
    if sn_ok:
        console.print("[green] ✓ awake[/]")
    else:
        console.print(f"[yellow] ⚠ {sn_detail} (wake at developer.servicenow.com)[/]")

    # ── Reset Container App env vars and scale settings ──
    # Each entry: (label, az args list)
    reset_cmds = [
        ("outage-api env vars", [
            "az", "containerapp", "update", "-n", f"ca-{WORKLOAD}-outage", "-g", rg,
            "--remove-env-vars", "FORCE_ERROR", "--output", "none"]),
        ("meter-api env vars", [
            "az", "containerapp", "update", "-n", f"ca-{WORKLOAD}-meter", "-g", rg,
            "--remove-env-vars", "SIMULATE_OOM", "--output", "none"]),
        ("grid-status-api env + scale", [
            "az", "containerapp", "update", "-n", f"ca-{WORKLOAD}-grid", "-g", rg,
            "--remove-env-vars", "SIMULATE_DELAY_MS",
            "--min-replicas", "1", "--max-replicas", "5",
            "--cpu", "0.25", "--memory", "0.5Gi", "--output", "none"]),
        ("notification-svc REQUIRED_CONFIG", [
            "az", "containerapp", "update", "-n", f"ca-{WORKLOAD}-notify", "-g", rg,
            "--set-env-vars", "REQUIRED_CONFIG=enabled", "--output", "none"]),
        ("portal WEBSITES_PORT", [
            "az", "webapp", "config", "appsettings", "set",
            "--name", f"app-{WORKLOAD}-portal", "--resource-group", rg,
            "--settings", "WEBSITES_PORT=8080", "--output", "none"]),
    ]
    reset_failures = []
    for label, args in reset_cmds:
        ok, _out, err = run_az(args, timeout=90, retries=1)
        if ok:
            console.print(f"[green]  ✓ {label}[/]")
        else:
            reset_failures.append((label, err))
            console.print(f"[yellow]  ⚠ {label}: {err[:80]}[/]")

    # ── Restart portal App Service so new WEBSITES_PORT takes effect ──
    ok, _out, err = run_az(
        ["az", "webapp", "restart", "--name", f"app-{WORKLOAD}-portal",
         "--resource-group", rg, "--output", "none"],
        timeout=60, retries=1,
    )
    if ok:
        console.print("[green]  ✓ portal restarted[/]")
    else:
        console.print(f"[yellow]  ⚠ portal restart: {err[:80]}[/]")

    # ── Disable chaos mode on grid-status-api (in case scenario 5 left it on) ──
    console.print("[dim]  Disabling chaos mode on grid-status-api...[/]", end="")
    try:
        r = requests.delete(f"{GRID_API_URL}/chaos/latency", timeout=5)
        if r.status_code in (200, 204):
            console.print("[green] ✓ disabled[/]")
        else:
            console.print(f"[yellow] ⚠ status {r.status_code}[/]")
    except Exception as e:
        console.print(f"[yellow] ⚠ {str(e)[:60]}[/]")

    # ── Ensure VM is running and clean disk pressure files ──
    console.print("[dim]  Checking VM status...[/]", end="")
    ok, vm_state, err = run_az(
        ["az", "vm", "get-instance-view", "--name", VM_NAME, "--resource-group", rg,
         "--query", "instanceView.statuses[?starts_with(code, 'PowerState/')].displayStatus | [0]",
         "-o", "tsv"],
        timeout=30,
    )
    if not ok:
        console.print(f"[yellow] ⚠ VM lookup skipped: {err[:60]}[/]")
    else:
        console.print(f" [dim]{vm_state or 'unknown'}[/]")
        if "running" not in (vm_state or "").lower():
            console.print("[dim]  Starting VM (may take 1-2 min)...[/]", end="")
            ok_start, _out, err_start = run_az(
                ["az", "vm", "start", "--name", VM_NAME, "--resource-group", rg, "--output", "none"],
                timeout=300,
            )
            if ok_start:
                console.print("[green] ✓ started[/]")
            else:
                console.print(f"[yellow] ⚠ {err_start[:60]}[/]")
        console.print("[dim]  Cleaning disk pressure files on VM...[/]", end="")
        ok_clean, _out, err_clean = run_az(
            ["az", "vm", "run-command", "invoke",
             "--resource-group", rg, "--name", VM_NAME,
             "--command-id", "RunPowerShellScript",
             "--scripts",
             "Remove-Item C:\\data\\scada-backups\\*.bak -Force -ErrorAction SilentlyContinue;"
             "Remove-Item C:\\data\\grid-logs\\*.log -Force -ErrorAction SilentlyContinue;"
             "Remove-Item C:\\data\\grid-logs\\*.tmp -Force -ErrorAction SilentlyContinue;"
             "Remove-Item C:\\data\\meter-data\\*.dat -Force -ErrorAction SilentlyContinue;"
             "Write-Output CLEANED",
             "--output", "none"],
            timeout=180,
        )
        if ok_clean:
            console.print("[green] ✓ cleaned[/]")
        else:
            console.print(f"[yellow] ⚠ {err_clean[:60]}[/]")

    console.print("[green]\n  ✓ Reset actions complete[/]\n")

    # ── Validate services (with retry for in-flight rollouts) ──
    console.print("[bold cyan]  ▶ Validating services (waiting for rollouts, up to 90s each)...[/]\n")
    all_ok = True

    # External HTTP services — poll /health with backoff
    http_services = [
        ("outage-api",      OUTAGE_API_URL),
        ("grid-status-api", GRID_API_URL),
        ("portal",          PORTAL_URL),
    ]
    for name, url in http_services:
        ok, code, ms, elapsed = _wait_for_http_healthy(url, name, timeout_s=90, interval_s=5)
        if ok:
            console.print(f"  [green]✅ {name}: {code} ({ms:.0f}ms, ready in {elapsed:.0f}s)[/]")
        else:
            console.print(f"  [red]❌ {name}: {code or 'unreachable'} after {elapsed:.0f}s[/]")
            all_ok = False

    # Internal-ingress container apps — validate via ACA revision state
    aca_internal_services = [
        ("notification-svc", f"ca-{WORKLOAD}-notify"),
    ]
    for name, app in aca_internal_services:
        ok, detail, elapsed = _wait_for_aca_healthy(app, rg, timeout_s=90, interval_s=5)
        if ok:
            console.print(f"  [green]✅ {name}: {detail} (ready in {elapsed:.0f}s)[/]")
        else:
            console.print(f"  [red]❌ {name}: {detail} after {elapsed:.0f}s[/]")
            all_ok = False

    # ServiceNow — re-verify API is responding
    sn_ok2, sn_detail2 = _wake_servicenow(timeout=15)
    if sn_ok2:
        console.print(f"  [green]✅ ServiceNow: {sn_detail2}[/]")
    else:
        console.print(f"  [yellow]⚠  ServiceNow: {sn_detail2}[/]")
        # SNOW hibernation is common and not strictly a failure of the lab
        # services, so we warn but don't flip all_ok.

    console.print()
    if all_ok and not reset_failures:
        console.print("[green bold]  ✅ All services healthy![/]\n")
    elif all_ok:
        console.print("[yellow]  ⚠ Services healthy, but some reset commands reported issues:[/]")
        for label, err in reset_failures:
            console.print(f"    [dim]- {label}: {err[:120]}[/]")
        console.print()
    else:
        console.print("[yellow]  ⚠ Some services did not reach a healthy state in time.[/]")
        console.print("[dim]     If a rollout is still in progress, wait ~1 min and re-run Reset.[/]\n")

    console.input("[dim]  Press Enter to return to menu...[/]")

# ── System Status Panel ─────────────────────────────────────
_status_cache = {}  # {key: (timestamp, value)}
_STATUS_CACHE_TTL = 30  # seconds — keeps menu rendering snappy

def _cached(key, ttl, fn):
    """Memoize fn() result for `ttl` seconds under `key`."""
    now = time.time()
    entry = _status_cache.get(key)
    if entry and (now - entry[0]) < ttl:
        return entry[1]
    val = fn()
    _status_cache[key] = (now, val)
    return val


def _notify_aca_status():
    """Check notification-svc ACA revision health (it's internal-only,
    so HTTP probe from outside is impossible). Returns short status string.
    """
    ok, out, _err = run_az(
        ["az", "containerapp", "revision", "list",
         "-n", f"ca-{WORKLOAD}-notify", "-g", f"rg-{WORKLOAD}",
         "--query", "[?properties.active].{h:properties.healthState,r:properties.runningState} | [0]",
         "-o", "json"],
        timeout=10, parse_json=True,
    )
    if not ok or not isinstance(out, dict):
        return None  # az unavailable / not logged in
    h = (out.get("h") or "").lower()
    r = (out.get("r") or "").lower()
    return ("up" if h == "healthy" and r == "running" else
            f"degraded ({out.get('h')}/{out.get('r')})")


def _system_status_panel():
    services = [
        ("Outage API",   OUTAGE_API_URL),
        ("Grid Status",  GRID_API_URL),
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

    # Notification — internal ingress, validate via ACA revision state
    notify_status = _cached("notify_aca", _STATUS_CACHE_TTL, _notify_aca_status)
    if notify_status is None:
        lines.append(f"  {'Notification':<16} [dim]● N/A[/]")
    elif notify_status == "up":
        lines.append(f"  {'Notification':<16} [green]● UP[/]   [dim](internal)[/]")
    else:
        lines.append(f"  {'Notification':<16} [red]● {notify_status}[/]")

    # ServiceNow PDI status
    try:
        r = requests.get(f"{SN_URL}/api/now/table/incident?sysparm_limit=1",
                         auth=(SN_USER, SN_PASS),
                         headers={"Accept": "application/json"}, timeout=5)
        if r.status_code == 200:
            lines.append(f"  {'ServiceNow':<16} [green]● AWAKE[/]")
        elif r.status_code == 401:
            lines.append(f"  {'ServiceNow':<16} [red]● AUTH ERR[/]")
        else:
            lines.append(f"  {'ServiceNow':<16} [yellow]● {r.status_code}[/]")
    except requests.exceptions.Timeout:
        lines.append(f"  {'ServiceNow':<16} [yellow]● HIBERNATING[/]")
    except Exception:
        lines.append(f"  {'ServiceNow':<16} [dim]● N/A[/]")

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
  [bold cyan]7.[/]  🎫  ServiceNow Laptop Replacement
  [bold cyan]8.[/]  🧹  Reset All (Healthy Baseline)
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
    # If launched with --scenario, run that scenario directly (used by new-window launch)
    if len(sys.argv) >= 3 and sys.argv[1] == "--scenario":
        scenarios = {
            "1": scenario_crash, "2": scenario_perf, "3": scenario_config,
            "4": scenario_disk, "5": scenario_load, "6": scenario_build_failure,
            "7": scenario_servicenow, "8": scenario_reset,
        }
        fn = scenarios.get(sys.argv[2])
        if fn:
            fn()
            console.input("\n[dim]  Press Enter to close this window...[/]")
        return

    # Main menu — launches scenarios in new terminal windows
    scenarios = {
        "1": "scenario_crash",
        "2": "scenario_perf",
        "3": "scenario_config",
        "4": "scenario_disk",
        "5": "scenario_load",
        "6": "scenario_build_failure",
        "7": "scenario_servicenow",
        "8": "scenario_reset",
    }
    scenario_names = {
        "1": "Bad Deployment — App Crash",
        "2": "Bad Deployment — Perf Regression",
        "3": "Bad Deployment — Config Error",
        "4": "Disk Pressure (VM)",
        "5": "Organic Load Spike",
        "6": "Pipeline Build Failure",
        "7": "ServiceNow Laptop Replacement",
        "8": "Reset All",
    }
    while True:
        show_menu()
        choice = console.input(
            "[bold cyan]  Select scenario (1-8, Q): [/]").strip().lower()
        if choice == "q":
            console.print("[bold]  Goodbye! ⚡[/]")
            break
        if choice in scenarios:
            name = scenario_names[choice]
            console.print(f"[bold cyan]  Opening '{name}' in new window...[/]")
            script_path = os.path.abspath(__file__)
            subprocess.Popen(
                f'start "PowerGrid — {name}" cmd /k python "{script_path}" --scenario {choice}',
                shell=True
            )
            time.sleep(1)
        else:
            console.print("[red]  Invalid choice.[/]")
            time.sleep(1)


if __name__ == "__main__":
    main()
