#!/usr/bin/env python3
"""
ghap v1.2.0 — GitHub Actions Progress Monitor
https://github.com/sindus/term/tree/main/github-action-progress

Install: curl -fsSL https://raw.githubusercontent.com/sindus/term/main/github-action-progress/install.sh | bash
"""

VERSION  = "1.2.0"
APP_DIR  = __import__('os').path.expanduser("~/.ghap")
RAW_BASE = "https://raw.githubusercontent.com/sindus/term/main/github-action-progress"

import getpass
import os
import select as _select
import shutil
import sys
import termios
import time
import tty
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple, Union

warnings.filterwarnings("ignore")

try:
    import requests
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
except ImportError:
    print("Missing dependencies — run: pip3 install requests rich")
    sys.exit(1)

# ─── Config ───────────────────────────────────────────────────────────────────

INTERVAL      = 15
COMPLETED_TTL = 300
CONFIG_DIR    = os.path.expanduser("~/.config/ghap")
TOKEN_FILE    = os.path.join(CONFIG_DIR, "token")
API_BASE      = "https://api.github.com"

STATUS_STYLE: Dict[str, Tuple[str, str]] = {
    "in_progress": ("▶", "yellow"),
    "queued":      ("⏳", "cyan"),
    "waiting":     ("⏸", "blue"),
    "requested":   ("◌", "dim"),
    "pending":     ("◌", "dim"),
}
CONCLUSION_STYLE: Dict[str, Tuple[str, str]] = {
    "success":         ("✓", "bold green"),
    "failure":         ("✗", "bold red"),
    "cancelled":       ("⊘", "dim"),
    "skipped":         ("↷", "dim"),
    "timed_out":       ("⏱", "red"),
    "action_required": ("!", "yellow"),
    "startup_failure": ("✗", "bold red"),
}

# ─── Update ───────────────────────────────────────────────────────────────────

def _ver_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0,)

def check_update(console: Console) -> None:
    try:
        r = requests.get(f"{RAW_BASE}/version.txt", timeout=4)
        if not r.ok:
            return
        latest = r.text.strip()
        if _ver_tuple(latest) <= _ver_tuple(VERSION):
            return
        console.print(
            f"[yellow]Update available:[/yellow] "
            f"[dim]{VERSION}[/dim] → [bold cyan]{latest}[/bold cyan]"
        )
        try:
            ans = input("Update now? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if ans in ("", "y", "yes"):
            _do_update(console, latest)
    except Exception:
        pass

def _do_update(console: Console, latest: str) -> None:
    url      = f"{RAW_BASE}/ghap.py"
    app_path = os.path.join(APP_DIR, "ghap.py")
    console.print("Downloading update…", end=" ")
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        os.makedirs(APP_DIR, exist_ok=True)
        tmp = app_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(r.text)
        os.chmod(tmp, 0o755)
        os.replace(tmp, app_path)
        console.print(f"[green]✓[/green]  ghap {latest} ready — restarting…\n")
        time.sleep(0.6)
        os.execv(sys.executable, [sys.executable, app_path] + sys.argv[1:])
    except Exception as exc:
        console.print(f"[red]Update failed: {exc}[/red]")

# ─── Token management ─────────────────────────────────────────────────────────

_TOKEN_HOWTO = """
[bold yellow]No GitHub token found.[/bold yellow]

To create one:
  1. Open  [cyan]https://github.com/settings/tokens/new[/cyan]
  2. Give it a name  (e.g. [bold]ghap[/bold])
  3. Select scope:   [bold]repo[/bold]  (or [bold]public_repo[/bold] for public repos only)
  4. Click [bold]Generate token[/bold] and copy it

[dim]To change your token later:  [bold]ghap --reset-token[/bold][/dim]
"""

def _save_token(token: str) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(token)
    os.chmod(TOKEN_FILE, 0o600)

def _prompt_token(console: Console) -> str:
    console.print(_TOKEN_HOWTO)
    try:
        token = getpass.getpass("Paste your GitHub token: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    if not token:
        console.print("[red]No token provided.[/red]")
        sys.exit(1)
    _save_token(token)
    console.print("[green]✓[/green] Token saved to ~/.config/ghap/token\n")
    return token

def load_token(console: Console) -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
        if token:
            return token
    return _prompt_token(console)

def reset_token(console: Console) -> None:
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
    console.print("[dim]Previous token cleared.[/dim]")

# ─── Keyboard input ──────────────────────────────────────────────────────────

def read_key() -> str:
    """Blocking raw read — used inside _checkbox_ui."""
    fd  = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1)
        if ch == b"\x1b":
            ready, _, _ = _select.select([fd], [], [], 0.05)
            if ready:
                ch2 = os.read(fd, 1)
                if ch2 == b"[":
                    ready2, _, _ = _select.select([fd], [], [], 0.05)
                    if ready2:
                        ch3 = os.read(fd, 1)
                        if ch3 == b"A": return "up"
                        if ch3 == b"B": return "down"
            return "esc"
        if ch in (b"\r", b"\n"):       return "enter"
        if ch == b" ":                 return "space"
        if ch == b"\x03":             return "ctrl_c"
        if ch in (b"\x7f", b"\x08"): return "backspace"
        try:
            decoded = ch.decode("utf-8")
            if decoded.isprintable():
                return decoded
        except Exception:
            pass
        return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _wait_for_key(timeout: float) -> Optional[str]:
    """
    Wait up to `timeout` seconds for a keypress during the monitoring loop.
    Uses cbreak mode (keeps OPOST + ISIG) so Rich Live rendering is unaffected
    and Ctrl-C still raises KeyboardInterrupt normally.
    Returns 'esc' or None.
    """
    if not sys.stdin.isatty():
        time.sleep(timeout)
        return None
    fd  = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        new        = termios.tcgetattr(fd)
        new[3]     = new[3] & ~(termios.ECHO | termios.ICANON)  # no echo, immediate chars
        new[6]     = list(new[6])
        new[6][termios.VMIN]  = 0
        new[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, new)

        ready, _, _ = _select.select([fd], [], [], timeout)
        if not ready:
            return None
        ch = os.read(fd, 1)
        if ch == b"\x1b":
            # Drain any following bytes (arrow keys etc.) then return 'esc'
            r2, _, _ = _select.select([fd], [], [], 0.05)
            if r2:
                ch2 = os.read(fd, 1)
                if ch2 == b"[":
                    r3, _, _ = _select.select([fd], [], [], 0.05)
                    if r3:
                        os.read(fd, 1)  # consume A/B/C/D
            return "esc"
        # Ignore any other key pressed during monitoring
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

# ─── Interactive checkbox UI ──────────────────────────────────────────────────

_RST    = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_CYAN   = "\033[1;36m"
_GREEN  = "\033[1;32m"
_YELLOW = "\033[1;33m"
_WHITE  = "\033[1;37m"


def _checkbox_ui(
    items: List[Tuple[str, str]],
    title: str,
    preselected: Optional[Set[str]] = None,
) -> List[str]:
    """
    Keyboard-driven checkbox selector.
    items       : list of (display_label, value)
    preselected : values to mark as checked on entry (used when returning from monitor)
    Returns     : list of selected values (guaranteed non-empty)
    """
    if not sys.stdin.isatty():
        raise RuntimeError("Interactive selection requires a real terminal.")

    selected:   Set[str] = set(preselected) if preselected else set()
    cursor      = 0
    page_start  = 0
    filter_text = ""
    page_size   = 0

    # Place cursor on the first preselected item if any
    if preselected:
        for i, (_, v) in enumerate(items):
            if v in preselected:
                cursor = i
                break

    def filtered() -> List[Tuple[str, str]]:
        if not filter_text:
            return items
        t = filter_text.lower()
        return [(l, v) for l, v in items if t in l.lower()]

    def adjust_page(total: int) -> None:
        nonlocal page_start
        if page_size <= 0:
            return
        if cursor < page_start:
            page_start = cursor
        elif cursor >= page_start + page_size:
            page_start = cursor - page_size + 1

    def render() -> None:
        nonlocal page_size, cursor, page_start
        cols, rows = shutil.get_terminal_size()
        page_size  = max(3, rows - 10)

        vis = filtered()
        if vis:
            cursor = max(0, min(cursor, len(vis) - 1))
        adjust_page(len(vis))

        out: List[str] = []
        out.append(f"{_BOLD}{_CYAN}{title}{_RST}")
        out.append("")
        out.append(
            f"{_DIM}  "
            f"↑ ↓  navigate    "
            f"{_RST}{_BOLD}SPACE{_RST}{_DIM}  select / deselect    "
            f"{_RST}{_BOLD}ENTER{_RST}{_DIM}  confirm    "
            f"{_RST}{_BOLD}A{_RST}{_DIM}  select all    "
            f"{_RST}{_BOLD}Ctrl-C{_RST}{_DIM}  quit"
            f"{_RST}"
        )
        out.append("")

        if filter_text:
            out.append(f"  {_DIM}Filter:{_RST} {_BOLD}{filter_text}{_RST}▌")
        else:
            out.append(f"  {_DIM}Type to filter  ·  {len(selected)} selected{_RST}")
        out.append("")

        out.append(
            f"  {_DIM}↑  {page_start} more above{_RST}" if page_start > 0 else ""
        )

        page_items = vis[page_start:page_start + page_size]
        for i, (label, value) in enumerate(page_items):
            real_idx  = page_start + i
            is_cursor = real_idx == cursor
            is_sel    = value in selected

            check      = f"[{_GREEN}x{_RST}]" if is_sel else f"{_DIM}[ ]{_RST}"
            max_label  = max(20, cols - 12)
            disp_label = label[:max_label] + "…" if len(label) > max_label else label

            if is_cursor:
                arrow       = f"{_YELLOW}▶{_RST}"
                label_style = f"{_BOLD}{_WHITE}"
            else:
                arrow       = " "
                label_style = f"{_CYAN}" if is_sel else ""

            out.append(f" {arrow} {check}  {label_style}{disp_label}{_RST}")

        remaining = len(vis) - (page_start + page_size)
        out.append(
            f"  {_DIM}↓  {remaining} more below{_RST}" if remaining > 0 else ""
        )

        if not vis and filter_text:
            out.append(f"  {_YELLOW}No repos match \"{filter_text}\" — keep typing or press Backspace{_RST}")
        elif not selected:
            out.append(f"  {_DIM}Select at least one repo, then press ENTER{_RST}")
        else:
            preview = list(selected)[:3]
            suffix  = f" and {len(selected) - 3} more" if len(selected) > 3 else ""
            out.append(f"  {_GREEN}{len(selected)} selected{_RST}{_DIM}: {', '.join(preview)}{suffix}{_RST}")

        sys.stdout.write("\033[2J\033[H" + "\n".join(out))
        sys.stdout.flush()

    sys.stdout.write("\033[?25l")
    sys.stdout.flush()
    try:
        while True:
            render()
            key = read_key()
            vis = filtered()

            if key in ("ctrl_c", "esc"):
                raise KeyboardInterrupt
            elif key == "up" and vis:
                cursor = max(0, cursor - 1)
                adjust_page(len(vis))
            elif key == "down" and vis:
                cursor = min(len(vis) - 1, cursor + 1)
                adjust_page(len(vis))
            elif key == "space" and vis and 0 <= cursor < len(vis):
                val = vis[cursor][1]
                if val in selected:
                    selected.discard(val)
                else:
                    selected.add(val)
            elif key == "enter":
                if selected:
                    break
            elif key == "a":
                if len(selected) == len(items):
                    selected.clear()
                else:
                    selected.update(v for _, v in items)
            elif key == "backspace" and filter_text:
                filter_text = filter_text[:-1]
                cursor = 0
                page_start = 0
            elif len(key) == 1 and (key.isalnum() or key in "-_/."):
                filter_text += key
                cursor = 0
                page_start = 0
    finally:
        sys.stdout.write("\033[?25h\033[2J\033[H")
        sys.stdout.flush()

    return [v for _, v in items if v in selected]

# ─── GitHub API client ────────────────────────────────────────────────────────

class GitHub:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept":        "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self.rate_remaining = 5000
        self.rate_limit     = 5000

    def _get(self, path: str, **params) -> Optional[Union[dict, list]]:
        url = path if path.startswith("http") else f"{API_BASE}{path}"
        try:
            r = self.session.get(url, params=params or None, timeout=12)
            self.rate_remaining = int(r.headers.get("X-RateLimit-Remaining", self.rate_remaining))
            self.rate_limit     = int(r.headers.get("X-RateLimit-Limit",     self.rate_limit))
            if r.status_code == 401:
                raise RuntimeError(
                    "GitHub token invalid or expired. Run: ghap --reset-token"
                )
            return r.json() if r.ok else None
        except RuntimeError:
            raise
        except Exception:
            return None

    def validate(self) -> str:
        data = self._get("/user")
        if not data or "login" not in data:
            raise RuntimeError("Cannot authenticate. Run: ghap --reset-token")
        return data["login"]

    def list_repos(self) -> List[dict]:
        repos, page = [], 1
        while True:
            chunk = self._get(
                "/user/repos",
                per_page=100, page=page,
                sort="full_name",
                affiliation="owner,collaborator",
            )
            if not chunk:
                break
            repos.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1
        return sorted(repos, key=lambda r: r["full_name"].lower())

    def get_active_runs(self, full_name: str) -> List[dict]:
        runs: List[dict] = []
        for status in ("in_progress", "queued", "waiting"):
            data = self._get(f"/repos/{full_name}/actions/runs", status=status, per_page=20)
            if data:
                runs.extend(data.get("workflow_runs", []))
        return runs

    def get_jobs(self, full_name: str, run_id: int) -> List[dict]:
        data = self._get(f"/repos/{full_name}/actions/runs/{run_id}/jobs", filter="latest")
        return data.get("jobs", []) if data else []

    def get_run(self, full_name: str, run_id: int) -> Optional[dict]:
        return self._get(f"/repos/{full_name}/actions/runs/{run_id}")

    def get_latest_failed_per_workflow(self, full_name: str) -> List[dict]:
        """
        For each workflow in this repo, return its most recent run if it failed.
        The API returns runs sorted by created_at desc, so the first occurrence
        of each workflow name is its latest run.
        """
        data = self._get(f"/repos/{full_name}/actions/runs", per_page=50)
        if not data:
            return []
        runs = data.get("workflow_runs", [])
        seen_workflows: Set[str] = set()
        failed: List[dict] = []
        for run in runs:
            wname = run.get("name", "")
            if wname in seen_workflows:
                continue
            seen_workflows.add(wname)
            if run.get("status") == "completed" and run.get("conclusion") == "failure":
                failed.append(run)
        return failed

# ─── Helpers ──────────────────────────────────────────────────────────────────

def fmt_duration(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    s  = int((datetime.now(timezone.utc) - dt).total_seconds())
    if s < 60:   return f"{s}s"
    if s < 3600: return f"{s // 60}m {s % 60:02d}s"
    return f"{s // 3600}h {(s % 3600) // 60}m"

def fmt_run_age(run: dict) -> str:
    if run.get("status") == "completed":
        return fmt_duration(run.get("updated_at"))
    return fmt_duration(run.get("run_started_at") or run.get("created_at"))

def mono() -> float:
    return time.monotonic()

# ─── Run state tracker ────────────────────────────────────────────────────────

class RunTracker:
    def __init__(self, repos: List[str]):
        self.repos     = repos
        self.active:    Dict[int, dict]               = {}
        self.completed: Dict[int, Tuple[dict, float]] = {}
        self.jobs:      Dict[int, List[dict]]         = {}
        self.failed:    Dict[str, List[dict]]         = {}

    def update(self, gh: GitHub) -> None:
        seen: Set[int] = set()

        def fetch(repo: str) -> Tuple[List[dict], Dict[int, List[dict]], List[dict]]:
            runs     = gh.get_active_runs(repo)
            jobs_map: Dict[int, List[dict]] = {}
            for run in runs:
                if run.get("status") == "in_progress":
                    jobs = gh.get_jobs(repo, run["id"])
                    if jobs:
                        jobs_map[run["id"]] = jobs
            failed = gh.get_latest_failed_per_workflow(repo)
            return runs, jobs_map, failed

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(fetch, r): r for r in self.repos}
            for fut in as_completed(futures):
                repo_name = futures[fut]
                try:
                    runs, jobs_map, failed_runs = fut.result()
                except Exception:
                    continue
                for run in runs:
                    rid = run["id"]
                    seen.add(rid)
                    self.active[rid] = run
                    if rid in jobs_map:
                        self.jobs[rid] = jobs_map[rid]
                self.failed[repo_name] = failed_runs

        now = mono()
        for rid in list(self.active):
            if rid not in seen:
                run   = self.active[rid]
                repo  = run["repository"]["full_name"]
                final = gh.get_run(repo, rid) or run
                self.completed[rid] = (final, now)
                del self.active[rid]
                self.jobs.pop(rid, None)

        cutoff = now - COMPLETED_TTL
        self.completed = {k: v for k, v in self.completed.items() if v[1] > cutoff}

        all_tracked = set(self.completed) | set(self.active)
        for repo_name in self.failed:
            self.failed[repo_name] = [
                f for f in self.failed[repo_name]
                if f["id"] not in all_tracked
            ]

# ─── Rendering ────────────────────────────────────────────────────────────────

def _run_block(run: dict, jobs: Optional[List[dict]], completed_at: Optional[float]) -> Text:
    t          = Text()
    status     = run.get("status", "unknown")
    conclusion = run.get("conclusion")

    if status == "completed" and conclusion:
        icon, color = CONCLUSION_STYLE.get(conclusion, ("?", "white"))
    else:
        icon, color = STATUS_STYLE.get(status, ("?", "white"))

    repo   = run.get("repository", {}).get("full_name", "?")
    name   = run.get("name", "?")
    branch = run.get("head_branch", "?")
    age    = fmt_duration(run.get("run_started_at") or run.get("created_at"))

    t.append(f" {icon} ", style=color)
    t.append(repo,        style="cyan bold")
    t.append(f"  {name}", style="white bold")
    t.append("  ·  branch: ", style="dim")
    t.append(branch,      style="magenta")
    t.append(f"  ·  {age}", style="dim")

    if status == "completed" and conclusion:
        lbl    = conclusion.upper().replace("_", " ")
        i2, c2 = CONCLUSION_STYLE.get(conclusion, ("?", "white"))
        t.append(f"  [{i2} {lbl}]", style=c2)
        if completed_at is not None:
            elapsed = int(mono() - completed_at)
            t.append(f"  finished {elapsed // 60}m {elapsed % 60:02d}s ago", style="dim")
    elif status == "queued":
        t.append("  waiting for a runner…", style="dim")
    elif status == "waiting":
        t.append("  waiting for approval or dependency…", style="dim")

    if jobs:
        for job in jobs:
            js    = job.get("status", "unknown")
            jc    = job.get("conclusion")
            jname = job.get("name", "?")
            jage  = fmt_duration(job.get("started_at"))

            if js == "completed" and jc:
                ji, jcol = CONCLUSION_STYLE.get(jc, ("?", "white"))
            else:
                ji, jcol = STATUS_STYLE.get(js, ("?", "white"))

            t.append(f"\n     {ji} ", style=jcol)
            t.append(jname, style="white")
            if js not in ("queued", "waiting"):
                t.append(f"  ({jage})", style="dim")

            if js == "in_progress":
                steps       = job.get("steps") or []
                active_step = next((s for s in steps if s.get("status") == "in_progress"), None)
                if active_step:
                    n     = active_step.get("number", "?")
                    total = len(steps)
                    sname = active_step.get("name", "?")
                    t.append("\n        └─ ", style="dim")
                    t.append(f"step {n}/{total}: ", style="dim")
                    t.append(sname, style="dim italic")

    return t


def _failed_line(run: dict) -> Text:
    t      = Text()
    repo   = run.get("repository", {}).get("full_name", "?")
    name   = run.get("name", "?")
    branch = run.get("head_branch", "?")
    ago    = fmt_run_age(run)
    t.append(" ✗ ",  style="bold red")
    t.append(repo,    style="cyan bold")
    t.append(f"  {name}", style="white bold")
    t.append("  ·  branch: ", style="dim")
    t.append(branch,  style="magenta")
    t.append("  ·  failed ", style="dim")
    t.append(f"{ago} ago", style="red")
    return t


def _section(label: str, color: str = "dim") -> Text:
    bar = "─" * 3
    return Text.assemble(
        (f" {bar} ", color),
        (label, f"bold {color}"),
        (f" {bar}\n", color),
    )


def render(
    gh:       GitHub,
    tracker:  RunTracker,
    interval: int,
    next_in:  int,
    loading:  bool,
    username: str,
) -> Panel:
    now_str    = datetime.now().strftime("%H:%M:%S")
    rate_color = "green" if gh.rate_remaining > 1000 else "yellow" if gh.rate_remaining > 200 else "red"
    frac       = max(0.0, min(1.0, 1.0 - next_in / interval))
    bar        = "█" * int(20 * frac) + "░" * (20 - int(20 * frac))

    title = Text.assemble(
        ("⚡ ghap", "bold white"),
        (f" v{VERSION}", "dim"),
        (f"  @{username}", "dim cyan"),
        "  ·  ",
        (now_str, "dim"),
        "  ·  next ",
        (f"{next_in}s", "cyan"),
        (f"  {bar}", "dim"),
        "  ·  API ",
        (f"{gh.rate_remaining}/{gh.rate_limit}", rate_color),
    )

    if loading:
        return Panel(
            Align.center(Text("\n  Fetching…\n", style="dim italic")),
            title=title, border_style="blue",
        )

    body = Text()

    active_runs = sorted(
        tracker.active.values(),
        key=lambda r: (
            r.get("repository", {}).get("full_name", ""),
            r.get("run_started_at") or "",
        ),
    )
    for run in active_runs:
        body.append_text(_run_block(run, tracker.jobs.get(run["id"]), None))
        body.append("\n\n")

    all_failed = [
        run
        for repo_name in sorted(tracker.failed)
        for run in tracker.failed[repo_name]
    ]
    if all_failed:
        body.append_text(_section("last failed", "red"))
        for run in all_failed:
            body.append_text(_failed_line(run))
            body.append("\n")
        body.append("\n")

    completed_sorted = sorted(
        tracker.completed.items(), key=lambda kv: kv[1][1], reverse=True
    )
    if completed_sorted:
        body.append_text(_section("recently completed"))
        for rid, (run, ts) in completed_sorted:
            body.append_text(_run_block(run, None, ts))
            body.append("\n")

    if not active_runs and not all_failed and not completed_sorted:
        body.append(
            f"\n  No active or failed workflows on: {', '.join(tracker.repos)}\n\n"
            "  Waiting for a push to trigger one…\n",
            style="dim italic",
        )

    n_failed = len(all_failed)
    footer = Text(
        f"  {len(active_runs)} active  ·  "
        + (f"{n_failed} last failed  ·  " if n_failed else "")
        + f"{len(completed_sorted)} recently finished  ·  "
        "[ESC] change repos  ·  [Ctrl-C] quit",
        style="dim",
    )
    return Panel(body, title=title, subtitle=footer, border_style="blue", padding=(0, 1))

# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        prog="ghap",
        description="GitHub Actions Progress Monitor — watch workflows live across your repos.",
    )
    parser.add_argument(
        "--interval", "-i", type=int, default=INTERVAL,
        help=f"Refresh interval in seconds (default: {INTERVAL})",
    )
    parser.add_argument(
        "--reset-token", action="store_true",
        help="Clear the saved GitHub token and enter a new one",
    )
    args = parser.parse_args()

    console = Console()
    console.print(
        f"\n[bold blue]⚡ ghap[/bold blue] [dim]v{VERSION}[/dim]  "
        "—  GitHub Actions Progress Monitor"
    )

    check_update(console)

    if args.reset_token:
        reset_token(console)

    token = load_token(console)
    gh    = GitHub(token)

    console.print("Authenticating…", end=" ")
    try:
        username = gh.validate()
    except RuntimeError as exc:
        console.print(f"\n[red]{exc}[/red]")
        sys.exit(1)
    console.print(f"[green]✓[/green] logged in as [cyan bold]{username}[/cyan bold]")

    console.print("Loading repositories…", end=" ")
    try:
        repos = gh.list_repos()
    except Exception as exc:
        console.print(f"\n[red]{exc}[/red]")
        sys.exit(1)
    console.print(f"[green]✓[/green] {len(repos)} repositories found\n")

    items = [
        (
            f"{r['full_name']:<45}  {'private' if r.get('private') else 'public ':7}  "
            f"pushed {fmt_duration(r.get('pushed_at'))} ago",
            r["full_name"],
        )
        for r in repos
    ]

    preselected: Optional[Set[str]] = None

    while True:  # selection ↔ monitoring loop
        selected = _checkbox_ui(
            items,
            title="Select repositories to monitor",
            preselected=preselected,
        )

        console.print(f"[green]Watching {len(selected)} repo(s):[/green]")
        for name in selected:
            console.print(f"  [cyan]•[/cyan] {name}")
        console.print(f"\n[dim]Refreshing every {args.interval}s — ESC to change repos — Ctrl-C to quit[/dim]\n")
        time.sleep(0.5)

        tracker      = RunTracker(selected)
        last_refresh: float = 0.0
        loading      = True
        go_back      = False

        with Live(console=console, refresh_per_second=4, screen=True) as live:
            while True:
                now     = mono()
                elapsed = now - last_refresh
                next_in = max(0, int(args.interval - elapsed))

                if elapsed >= args.interval or last_refresh == 0:
                    loading = True
                    live.update(render(gh, tracker, args.interval, 0, loading, username))
                    try:
                        tracker.update(gh)
                    except RuntimeError as exc:
                        console.print(f"[red]{exc}[/red]")
                        sys.exit(1)
                    last_refresh = mono()
                    next_in  = args.interval
                    loading  = False

                live.update(render(gh, tracker, args.interval, next_in, loading, username))

                key = _wait_for_key(0.25)
                if key == "esc":
                    go_back = True
                    break

        if not go_back:
            break

        # Remember current selection so the checkbox pre-ticks them on return
        preselected = set(selected)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
