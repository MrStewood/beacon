"""Readable single-screen CLI dashboard for the Beacon pipeline.

Design rules:
- Show only watch-mode essentials by default.
- Prefer labels near values, semantic color, short rows, and whitespace.
- Never require scrollback; output is capped to the terminal height.
"""

from __future__ import annotations

import io
import json
import subprocess
from collections import deque
from collections import Counter
from datetime import datetime
from pathlib import Path
from textwrap import shorten

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.pipeline.supervisor import (
    APPROVED_DIR,
    BEACON_ROOT,
    CATEGORY_PRIORITY,
    INVESTIGATIONS_DIR,
    REJECTED_DIR,
    snapshot_state,
)

REVIEWS_DIR = BEACON_ROOT / "leads" / "reviews"

_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console()
    return _console


class RunStats:
    """Counters for one `--loop` session. Created by the supervisor CLI."""

    def __init__(self) -> None:
        self.started = datetime.now().astimezone()
        self.steps = 0
        self.actions: Counter[str] = Counter()
        self.last_action = ""
        self.last_target = ""
        self.messages: deque[str] = deque(maxlen=200)
        self.log("dashboard started")

    def record(self, action: str, target: str | None = None, reason: str | None = None) -> None:
        self.steps += 1
        self.actions[action] += 1
        self.last_action = action
        self.last_target = target or ""
        message = f"step {self.steps}: {action}"
        if target:
            message += f" → {target}"
        if reason:
            message += f" — {reason}"
        self.log(message)

    def log(self, message: str) -> None:
        ts = datetime.now().astimezone().strftime("%H:%M:%S")
        for line in str(message).splitlines() or [""]:
            line = line.strip()
            if line:
                self.messages.append(f"{ts}  {line}")

    @property
    def elapsed(self) -> str:
        delta = datetime.now().astimezone() - self.started
        seconds = int(delta.total_seconds())
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


# ---------------------------------------------------------------------------
# Collection (no LLM calls, read-only)
# ---------------------------------------------------------------------------


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=BEACON_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def collect(snap: dict | None = None) -> dict:
    """Read every dashboard data source. Pure filesystem/git, no network."""
    snap = snap or snapshot_state()

    reviews = []
    if REVIEWS_DIR.exists():
        for p in sorted(REVIEWS_DIR.glob("*.json")):
            try:
                reviews.append(json.loads(p.read_text()))
            except Exception:
                pass

    inv = {"total": 0, "complete": 0, "incomplete": 0, "findings": 0, "conflicts": 0}
    if INVESTIGATIONS_DIR.exists():
        for p in INVESTIGATIONS_DIR.glob("*/*.json"):
            try:
                d = json.loads(p.read_text())
            except Exception:
                continue
            inv["total"] += 1
            complete = bool(d.get("complete") or (d.get("pass_b") and d.get("summary")))
            inv["complete" if complete else "incomplete"] += 1
            findings = d.get("findings", [])
            inv["findings"] += len(findings)
            inv["conflicts"] += len(d.get("conflicts", [])) + sum(
                1 for f in findings if f.get("conflicts_with")
            )

    approved_stems = {p.stem for p in APPROVED_DIR.rglob("*.yaml")} if APPROVED_DIR.exists() else set()
    rejected_stems = {p.stem for p in REJECTED_DIR.glob("*.yaml")} if REJECTED_DIR.exists() else set()
    unpublished_approve = [
        r for r in reviews
        if (
            r.get("decision") == "approve"
            and r.get("candidate_id") not in approved_stems
            and r.get("candidate_id") not in rejected_stems
        )
    ]

    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "?"
    head = _git("log", "-1", "--format=%h %s") or "?"

    return {
        "snap": snap,
        "reviews": reviews,
        "review_decisions": dict(Counter(r.get("decision", "?") for r in reviews)),
        "investigations": inv,
        "unpublished_approve": unpublished_approve,
        "branch": branch,
        "head": head,
    }


# ---------------------------------------------------------------------------
# Readable render helpers
# ---------------------------------------------------------------------------


def _pct(done: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round(done / total * 100):>3}%"


def _bar(done: int, total: int, width: int = 18) -> Text:
    total = max(total, 1)
    done = max(0, min(done, total))
    filled = round(width * done / total)
    t = Text("█" * filled, style="green")
    t.append("░" * (width - filled), style="dim")
    t.append(f" {_pct(done, total)}", style="dim")
    return t


def _style_count(value: int, *, warn: bool = False) -> str:
    if value == 0:
        return "green"
    return "yellow" if warn else "bright_white"


def _health_line(d: dict) -> Text:
    snap = d["snap"]
    alerts = snap["alerts"]["unacknowledged"]
    sensitive = len(snap["leads"].get("sensitive_pending", []))
    publish = len(d["unpublished_approve"])
    incomplete = d["investigations"]["incomplete"]

    problems = []
    if alerts:
        problems.append((f"{alerts} alert", "red"))
    needs_human = snap.get("needs_human", {}).get("count", 0)
    if needs_human:
        problems.append((f"{needs_human} awaiting human review", "yellow"))
    if sensitive:
        problems.append((f"{sensitive} sensitive queued", "yellow"))
    if publish:
        problems.append((f"{publish} approved not published", "red"))
    if incomplete:
        problems.append((f"{incomplete} investigation running", "yellow"))

    if not problems:
        return Text("OK — no unacknowledged alerts", style="green")

    text = Text("ATTENTION — ", style="bold yellow")
    for i, (label, style) in enumerate(problems):
        if i:
            text.append(" · ", style="dim")
        text.append(label, style=style)
    return text


def _next_focus(d: dict) -> tuple[str, str, str]:
    snap = d["snap"]
    if snap["alerts"]["unacknowledged"]:
        item = snap["alerts"].get("items", [{}])[0]
        return "Alert needs human", item.get("message") or item.get("title") or item.get("file", "unknown alert"), "red"
    nh = snap.get("needs_human", {})
    if nh.get("count"):
        return "Needs human review", nh.get("items", ["candidate"])[0], "yellow"
    if snap["candidates"]["requeued"]:
        item = snap["candidates"].get("requeued_items", [{}])[0]
        return "Follow-up needed", item.get("id") or item.get("path", "candidate"), "yellow"
    if snap["candidates"]["pending_review"]:
        item = snap["candidates"].get("pending_items", [{}])[0]
        return "Review candidate", item.get("id") or item.get("path", "candidate"), "cyan"
    if snap["investigations"]["needs_candidate"]:
        item = snap["investigations"].get("items", [{}])[0]
        return "Build candidate", f"{item.get('name', 'unknown')} · {item.get('category', 'unknown')}", "cyan"
    if snap["leads"]["queued_count"]:
        item = snap["leads"].get("next_queued", [{}])[0]
        return "Investigate lead", f"{item.get('name', 'unknown')} · {item.get('category', 'unknown')} · {item.get('zip', '?')}", "cyan"
    if snap["geography"].get("zips_pending"):
        return "Research ZIP", ", ".join(snap["geography"]["zips_pending"]), "cyan"
    return "Idle", "No pipeline action is currently queued.", "green"


def _render_header(console: Console, d: dict) -> None:
    snap = d["snap"]
    now = datetime.now().astimezone().strftime("%H:%M:%S %Z")
    title = Text("BEACON PIPELINE", style="bold cyan")
    title.append(f"  {now}", style="dim")
    title.append(f"  {d['branch']} @ {shorten(d['head'], width=max(console.size.width - 42, 20), placeholder='…')}", style="dim")
    console.print(title)

    counts = Text()
    counts.append("published ", style="dim")
    counts.append(str(snap["approved"]["total"]), style="bold green")
    counts.append("   leads ", style="dim")
    counts.append(f"{snap['leads']['investigated_count']}/{snap['leads']['total']}", style="bold")
    counts.append(" investigated   queued ", style="dim")
    counts.append(str(snap["leads"]["queued_count"]), style="bold yellow" if snap["leads"]["queued_count"] else "green")
    counts.append("   reviews ", style="dim")
    counts.append(str(len(d["reviews"])), style="bold")
    console.print(counts)
    console.print(_health_line(d))
    console.print()


def _render_focus(console: Console, d: dict, run: RunStats | None) -> None:
    label, detail, style = _next_focus(d)
    body = Text()
    body.append(label.upper(), style=f"bold {style}")
    body.append("\n")
    body.append(shorten(detail, width=max(console.size.width - 8, 20), placeholder="…"), style="bright_white")

    if run is not None:
        body.append("\n\n", style="dim")
        body.append(f"run {run.elapsed} · step {run.steps}", style="dim")
        if run.last_action:
            body.append(" · last ", style="dim")
            body.append(run.last_action, style="bold")
            if run.last_target:
                body.append(" → ", style="dim")
                body.append(shorten(run.last_target, width=max(console.size.width - 42, 12), placeholder="…"), style="dim")
    else:
        body.append("\n\n", style="dim")
        body.append("one-shot view · use --loop to watch live", style="dim")

    console.print(Panel(body, title="now", box=box.ROUNDED, border_style=style, padding=(0, 1)))


def _render_progress(console: Console, d: dict) -> None:
    snap = d["snap"]
    leads = snap["leads"]
    candidates = snap["candidates"]
    inv = snap["investigations"]
    reviewed = len(d["reviews"])
    published = snap["approved"]["total"]
    publish_pending = len(d["unpublished_approve"])
    build_done = max(d["investigations"]["complete"] - inv["needs_candidate"], 0)

    width = console.size.width
    label_width = 16 if width < 100 else 20
    bar_width = 12 if width < 100 else 18
    detail_width = max(width - label_width - bar_width - 10, 12)
    rows = [
        ("Leads", leads["investigated_count"], leads["total"], f"{leads['investigated_count']} done · {leads['queued_count']} queued"),
        ("Candidate build", build_done, build_done + inv["needs_candidate"], f"{build_done} built · {inv['needs_candidate']} to build"),
        ("Review/publish", reviewed, reviewed + candidates["pending_review"], f"{reviewed} reviewed · {candidates['pending_review']} pending · {publish_pending} publish"),
        ("Published", published, published + publish_pending, f"{published} live records"),
    ]

    console.print(Text("PROGRESS", style="bold cyan"))
    for label, done, total, detail in rows:
        line = Text(f"{label:<{label_width}}", style="bold")
        line.append_text(_bar(done, total, width=bar_width))
        line.append("  ")
        line.append(shorten(detail, width=detail_width, placeholder="…"), style="dim")
        console.print(line, overflow="crop", no_wrap=True)
    console.print()


def _render_work_queue(console: Console, d: dict, *, rows: int) -> None:
    snap = d["snap"]
    gaps = snap.get("coverage_gaps", [])[:rows]
    leads = snap["leads"].get("next_queued", [])[:rows]

    t = Table(box=None, show_header=True, header_style="bold dim", pad_edge=False, expand=True)
    t.add_column("Attention", ratio=1, overflow="ellipsis")
    t.add_column("Next queued lead", ratio=2, overflow="ellipsis")
    max_rows = max(len(gaps), len(leads), 1)
    for i in range(max_rows):
        gap = gaps[i] if i < len(gaps) else None
        lead = leads[i] if i < len(leads) else None
        gap_text = (
            Text(f"{gap['category']} gap · {gap['leads_available']} leads", style="yellow")
            if gap else Text("—", style="dim")
        )
        lead_text = (
            Text(f"{lead['category']} · {lead['name']}", style="bright_white")
            if lead else Text("—", style="dim")
        )
        t.add_row(gap_text, lead_text)

    console.print(Text("QUEUE", style="bold cyan"))
    console.print(t)
    console.print()


def _render_messages(console: Console, run: RunStats | None, *, rows: int) -> None:
    if rows <= 0:
        return
    messages = list(run.messages)[-rows:] if run is not None else ["start with --loop to see step messages here"]
    body = Text()
    for i, message in enumerate(messages):
        if i:
            body.append("\n")
        body.append(shorten(message, width=max(console.size.width - 6, 20), placeholder="…"), style="dim")
    console.print(Panel(body, title="messages", box=box.ROUNDED, border_style="dim", padding=(0, 1)))


def _render_footer(console: Console, d: dict) -> None:
    evidence = d["investigations"]
    text = f"evidence {evidence['findings']} findings · {evidence['complete']} investigations"
    if evidence["conflicts"]:
        text += f" · {evidence['conflicts']} conflicts"
    text += "   |   Ctrl+C once: clean stop · twice: force quit"
    console.print(Text(shorten(text, width=console.size.width, placeholder="…"), style="dim"), no_wrap=True)


def _render_body(console: Console, d: dict, run: RunStats | None) -> None:
    height = console.size.height
    _render_header(console, d)
    _render_focus(console, d, run)
    _render_progress(console, d)
    if height >= 34:
        _render_work_queue(console, d, rows=3)
    fixed_rows = len(console.file.getvalue().splitlines()) if isinstance(console.file, io.StringIO) else 0
    message_rows = max(height - fixed_rows - 4, 0)
    if message_rows:
        _render_messages(console, run, rows=message_rows)
    _render_footer(console, d)


def render(snap: dict | None = None, run: RunStats | None = None) -> None:
    """Render the dashboard, capped to the current terminal height."""
    console = get_console()
    d = collect(snap)
    height = max(console.size.height, 12)
    capture_file = io.StringIO()
    capture = Console(
        file=capture_file,
        force_terminal=console.is_terminal,
        color_system=console.color_system,
        width=console.size.width,
        height=height,
    )
    _render_body(capture, d, run)
    lines = capture_file.getvalue().splitlines()
    if len(lines) > height:
        lines = lines[:height - 1] + ["…"]
    console.file.write("\n".join(lines) + "\n")
    console.file.flush()
