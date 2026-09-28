"""Data-centric CLI dashboard for the Beacon pipeline.

Renders every pipeline statistic as a single rich-formatted screen:
funnel, per-run counters, goals, category coverage, geography,
recent activity, and health flags.

Requires `rich` (already installed on this host):
    python3 -m app.pipeline.supervisor --dashboard   # one shot
    python3 -m app.pipeline.supervisor --loop        # live view between steps
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from datetime import datetime
import io
from pathlib import Path

from rich import box
from rich.columns import Columns
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
    SENSITIVE_CATEGORIES,
    snapshot_state,
)

# ---------------------------------------------------------------------------
# Goals (derived from repo documentation — do not invent)
# ---------------------------------------------------------------------------

# leads/EXPANSION.md: Wave 0 (Laurel, done) + Wave 1 immediate neighbors.
WAVE1_COUNTIES = ["Laurel", "Knox", "Whitley", "Clay", "Pulaski", "McCreary", "Rockcastle"]

CATEGORIES_SCHEMA = BEACON_ROOT / "schema" / "categories.json"
CENSUS_ZIPS = BEACON_ROOT / "data" / "census" / "us-zips.json"
REVIEWS_DIR = BEACON_ROOT / "leads" / "reviews"
APPROVED_DIR_ = APPROVED_DIR

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
        self.last_action: str = ""
        self.last_target: str = ""
        self.last_at: datetime | None = None

    def record(self, action: str, target: str | None) -> None:
        self.steps += 1
        self.actions[action] += 1
        self.last_action = action
        self.last_target = target or "—"
        self.last_at = datetime.now().astimezone()

    @property
    def elapsed(self) -> str:
        secs = int((datetime.now().astimezone() - self.started).total_seconds())
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


# ---------------------------------------------------------------------------
# Collection (no LLM calls, read-only)
# ---------------------------------------------------------------------------

def _git(*args: str) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(BEACON_ROOT), *args],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def collect(snap: dict | None = None) -> dict:
    """Read every dashboard data source. Pure filesystem/git, no network."""
    snap = snap or snapshot_state()

    # Reviews -----------------------------------------------------------------
    reviews = []
    if REVIEWS_DIR.exists():
        for p in sorted(REVIEWS_DIR.glob("*.json")):
            try:
                reviews.append(json.loads(p.read_text()))
            except Exception:
                pass
    review_decisions = Counter(r.get("decision", "?") for r in reviews)

    # Investigations ----------------------------------------------------------
    inv = {"total": 0, "complete": 0, "incomplete": 0, "findings": 0, "conflicts": 0}
    if INVESTIGATIONS_DIR.exists():
        for p in INVESTIGATIONS_DIR.glob("*/*.json"):
            try:
                d = json.loads(p.read_text())
            except Exception:
                continue
            inv["total"] += 1
            complete = bool(d.get("complete") or (d.get("pass_b") and d.get("summary")))
            if complete:
                inv["complete"] += 1
            else:
                inv["incomplete"] += 1
            findings = d.get("findings", [])
            inv["findings"] += len(findings)
            inv["conflicts"] += len(d.get("conflicts", [])) + sum(
                1 for f in findings if f.get("conflicts_with")
            )

    # Published / rejected vs reviewed ----------------------------------------
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

    # Git ---------------------------------------------------------------------
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "?"
    head = _git("log", "-1", "--format=%h %s")
    commits = []
    raw = _git("log", "--format=%cI|%h|%s", "-n", "200")
    for line in raw.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({"ts": _parse_ts(parts[0]), "hash": parts[1], "subject": parts[2]})

    # Canonical categories -----------------------------------------------------
    needs = _load_json(CATEGORIES_SCHEMA).get("needs", {})
    canonical = list(needs) if isinstance(needs, dict) and needs else list(CATEGORY_PRIORITY)

    # ZIP -> county lookup for lead geography ----------------------------------
    zips = _load_json(CENSUS_ZIPS)

    return {
        "snap": snap,
        "reviews": reviews,
        "review_decisions": dict(review_decisions),
        "investigations": inv,
        "approved_stems": approved_stems,
        "rejected_stems": rejected_stems,
        "unpublished_approve": unpublished_approve,
        "branch": branch,
        "head": head,
        "commits": commits,
        "canonical_categories": canonical,
        "zips": zips,
    }


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

def _bar(done: int, total: int, width: int = 18) -> Text:
    done = max(0, min(done, total)) if total else 0
    filled = round(width * done / total) if total else 0
    t = Text()
    t.append("█" * filled, style="bold green")
    t.append("░" * (width - filled), style="dim")
    pct = round(100 * done / total) if total else 0
    t.append(f" {pct:>3d}%", style="dim")
    return t


def _count(value: int, style: str = "") -> Text:
    return Text(str(value), style=f"bold {style}" if style else "bold")


# ---------------------------------------------------------------------------
# Render sections
# ---------------------------------------------------------------------------

def _render_header(console: Console, d: dict) -> None:
    snap = d["snap"]
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    line1 = Text("BEACON PIPELINE DASHBOARD", style="bold bright_cyan")
    line1.append(f"   {now}", style="dim")
    line2 = Text(f"{d['branch']} @ {d['head']}", style="cyan")
    line2.append("   published: ", style="dim")
    line2.append(str(snap["approved"]["total"]), style="bold green")
    line2.append("   leads: ", style="dim")
    line2.append(str(snap["leads"]["total"]), style="bold bright_white")
    line2.append("   reviews: ", style="dim")
    line2.append(str(len(d["reviews"])), style="bold bright_white")
    console.print(Panel(Text.assemble(line1, "\n", line2), box=box.ROUNDED, border_style="cyan"))


def _render_funnel(console: Console, d: dict) -> None:
    snap = d["snap"]
    l, ca, iv = snap["leads"], snap["candidates"], snap["investigations"]
    inv = d["investigations"]
    pub = snap["approved"]["total"]
    build_done = max(inv["complete"] - iv["needs_candidate"], 0)
    review_done = len(d["reviews"])
    pub_pending = len(d["unpublished_approve"])

    t = Table(title="PIPELINE FUNNEL", box=box.SIMPLE_HEAVY, header_style="bold bright_cyan",
              show_edge=False, expand=True)
    t.add_column("Stage", style="bold", no_wrap=True)
    t.add_column("Pending", justify="right")
    t.add_column("Done", justify="right")
    t.add_column("Progress", width=24)

    t.add_row("1 · Investigate leads",
              Text(str(l["queued_count"]), style="yellow"),
              Text(str(l["investigated_count"]), style="green"),
              _bar(l["investigated_count"], l["total"]))
    t.add_row("2 · Build candidate",
              Text(str(iv["needs_candidate"]), style="yellow"),
              Text(str(build_done), style="green"),
              _bar(build_done, build_done + iv["needs_candidate"]))
    t.add_row("3 · Review candidate",
              Text(str(ca["pending_review"]), style="yellow"),
              Text(str(review_done), style="green"),
              _bar(review_done, review_done + ca["pending_review"]))
    t.add_row("4 · Publish (git push)",
              Text(str(pub_pending), style="red" if pub_pending else "green"),
              Text(str(pub), style="green"),
              _bar(pub, pub + pub_pending))
    t.add_row("5 · Follow-up / requeue",
              Text(str(ca["requeued"]), style="yellow"),
              Text("—", style="dim"),
              Text("—", style="dim"))

    console.print(t)
    detail = Text("  evidence: ", style="dim")
    detail.append(f"{inv['findings']} findings", style="bright_white")
    detail.append(f" from {inv['complete']} complete investigations · conflicts flagged: ", style="dim")
    detail.append(str(inv["conflicts"]), style="green" if inv["conflicts"] == 0 else "red")
    detail.append(f" · review decisions: {d['review_decisions'] or 'none'}", style="dim")
    console.print(detail)


def _render_run_and_health(console: Console, d: dict, run: RunStats | None) -> None:
    snap = d["snap"]

    if run is not None:
        acts = ", ".join(f"{k}×{v}" for k, v in run.actions.most_common()) or "none yet"
        reviews_this = sum(
            1 for r in d["reviews"]
            if (ts := _parse_ts(r.get("reviewed_at"))) and ts >= run.started
        )
        publishes_this = sum(
            1 for p in APPROVED_DIR.rglob("*.yaml")
            if datetime.fromtimestamp(p.stat().st_mtime).astimezone() >= run.started
        ) if APPROVED_DIR.exists() else 0
        run_lines = [
            Text.assemble(
                ("THIS RUN", "bold bright_cyan"),
                f"  since {run.started.strftime('%H:%M:%S')}  ·  {run.elapsed}  ·  step {run.steps}",
                style="dim",
            ),
            Text.assemble(("actions: ", "dim"), acts),
            Text.assemble(
                ("reviews: ", "dim"), (str(reviews_this), "bold bright_white"),
                ("  publishes: ", "dim"), (str(publishes_this), "bold green"),
            ),
            Text.assemble(
                ("last: ", "dim"), (run.last_action or "—", "bold"),
                (" → ", "dim"), (run.last_target[:52], "cyan"),
            ),
        ]
    else:
        run_lines = [Text("One-shot snapshot — start with --loop for a live run view.", style="dim")]
    body = Text()
    for i, line in enumerate(run_lines):
        if i:
            body.append("\n")
        body.append_text(line)
    run_panel = Panel(body, title="run", box=box.ROUNDED, border_style="blue")

    # Health -------------------------------------------------------------------
    al = snap["alerts"]
    health = Text()
    if al["unacknowledged"]:
        health.append(f"⚠ {al['unacknowledged']} unacknowledged alerts\n", style="bold red")
        for a in al["items"][:3]:
            health.append(f"  · {a.get('severity', '?')}: {a.get('message', a.get('title', '?'))}\n", style="red")
    else:
        health.append("✓ no unacknowledged alerts\n", style="green")

    sens = snap["leads"]["sensitive_pending"]
    if sens:
        health.append(f"⚠ {len(sens)} sensitive leads awaiting investigation\n", style="yellow")
        for s in sens[:2]:
            health.append(f"  · {s['name']} ({s['category']})\n", style="yellow")

    if d["unpublished_approve"]:
        health.append(f"⚠ {len(d['unpublished_approve'])} approved review(s) NOT in source/approved/\n",
                      style="bold red")
        for r in d["unpublished_approve"]:
            health.append(f"  · {r.get('candidate_id', '?')}\n", style="red")

    if d["investigations"]["incomplete"]:
        health.append(f"· {d['investigations']['incomplete']} investigation in progress\n", style="dim")
    health_panel = Panel(health, title="health", box=box.ROUNDED, border_style="yellow")

    console.print(Columns([run_panel, health_panel], expand=True, padding=(0, 1)))


def _render_goals(console: Console, d: dict) -> None:
    snap = d["snap"]
    a = snap["approved"]

    county_done = [c for c in WAVE1_COUNTIES if a["by_county"].get(c.lower(), 0) > 0]
    county_missing = [c for c in WAVE1_COUNTIES if c not in county_done]

    cats_pub = [c for c in d["canonical_categories"] if a["by_category"].get(c, 0) > 0]
    total_leads = snap["leads"]["total"]
    inv_done = snap["leads"]["investigated_count"]

    t = Table(title="GOALS", box=box.SIMPLE_HEAVY, header_style="bold bright_cyan",
              show_edge=False, expand=True)
    t.add_column("Goal", style="bold", no_wrap=True)
    t.add_column("Progress", width=26, justify="left")
    t.add_column("Detail", overflow="fold")

    t.add_row(
        f"Wave-1 counties published  {len(county_done)}/{len(WAVE1_COUNTIES)}",
        _bar(len(county_done), len(WAVE1_COUNTIES)),
        Text("missing: " + ", ".join(county_missing) if county_missing else "all covered", style="dim"),
    )
    t.add_row(
        f"Categories published  {len(cats_pub)}/{len(d['canonical_categories'])}",
        _bar(len(cats_pub), len(d["canonical_categories"])),
        Text(", ".join(cats_pub) or "none", style="dim"),
    )
    t.add_row(
        "Lead queue drained",
        _bar(inv_done, total_leads),
        Text(f"{inv_done} investigated · {snap['leads']['queued_count']} still queued", style="dim"),
    )
    geo = snap["geography"]
    t.add_row(
        "ZIP research",
        Text(f"{len(geo['zips_researched'])} zips researched", style="dim"),
        Text(
            f"next: {', '.join(geo['zips_pending'])}" if geo["zips_pending"]
            else "no pending expansion zips",
            style="dim",
        ),
    )
    console.print(t)


def _render_coverage(console: Console, d: dict) -> None:
    snap = d["snap"]
    leads_by_cat = snap["leads"]["by_category"]
    cat_status = snap["leads"].get("by_cat_status", {})
    pub_by_cat = snap["approved"]["by_category"]

    t = Table(title="COVERAGE BY CATEGORY", box=box.SIMPLE_HEAVY, header_style="bold bright_cyan",
              show_edge=False, expand=True)
    t.add_column("P", justify="right", style="dim", width=2)
    t.add_column("Category", style="bold", no_wrap=True)
    t.add_column("Leads", justify="right")
    t.add_column("Investigated", justify="right")
    t.add_column("Published", justify="right")
    t.add_column("Volume", width=20)
    t.add_column("", no_wrap=True)

    max_leads = max(leads_by_cat.values(), default=1)
    for cat, prio in sorted(CATEGORY_PRIORITY.items(), key=lambda x: -x[1]):
        if cat not in leads_by_cat and cat not in pub_by_cat:
            continue
        leads = leads_by_cat.get(cat, 0)
        st = cat_status.get(cat, {})
        pub = pub_by_cat.get(cat, 0)
        gap = pub == 0 and leads > 0
        flags = []
        if gap:
            flags.append(Text("GAP", style="bold red"))
        if cat in SENSITIVE_CATEGORIES:
            flags.append(Text("sensitive", style="yellow"))
        t.add_row(
            Text(str(prio), style="dim"),
            cat,
            Text(str(leads), style="bright_white"),
            Text(str(st.get("investigated", 0)), style="green"),
            Text(str(pub), style="bold green" if pub else "red" if gap else "dim"),
            _bar(leads, max_leads),
            Text("  ".join(str(f) for f in flags)),
        )
    console.print(t)


def _render_geography(console: Console, d: dict) -> None:
    snap = d["snap"]
    county_leads: Counter[str] = Counter()
    county_zips: Counter[str] = Counter()
    unknown_zips = 0
    for z, n in snap["leads"]["by_zip"].items():
        info = d["zips"].get(z)
        if not info:
            unknown_zips += 1
            continue
        county_leads[info.get("county", "?")] += n
        county_zips[info.get("county", "?")] += 1

    pub_by_county = snap["approved"]["by_county"]
    t = Table(title="GEOGRAPHY (lead ZIPs → county)", box=box.SIMPLE_HEAVY,
              header_style="bold bright_cyan", show_edge=False, expand=True)
    t.add_column("County", style="bold")
    t.add_column("Leads", justify="right")
    t.add_column("ZIPs", justify="right")
    t.add_column("Published", justify="right")

    for county, n in county_leads.most_common():
        pub = pub_by_county.get(county.lower(), 0)
        t.add_row(
            county,
            Text(str(n), style="bright_white"),
            Text(str(county_zips[county]), style="dim"),
            Text(str(pub), style="bold green" if pub else "dim"),
        )
    t.add_row("national", Text("—", style="dim"), Text("—", style="dim"),
              Text(str(pub_by_county.get("national", 0)), style="bold green"))
    if unknown_zips:
        t.add_row(Text("unknown ZIPs", style="dim"), Text(str(unknown_zips), style="dim"),
                  Text("—", style="dim"), Text("—", style="dim"))
    console.print(t)


def _render_activity(console: Console, d: dict) -> None:
    rows: list[tuple[datetime, str, str]] = []
    for r in d["reviews"]:
        ts = _parse_ts(r.get("reviewed_at"))
        if ts:
            rows.append((ts, "REVIEW",
                         f"{r.get('decision', '?')} ({r.get('confidence', '?')}) · {r.get('candidate_id', '?')}"))
    for c in d["commits"]:
        if c["ts"]:
            rows.append((c["ts"], "COMMIT", f"{c['hash']} {c['subject']}"))
    rows.sort(key=lambda x: x[0], reverse=True)

    t = Table(title="RECENT ACTIVITY", box=box.SIMPLE_HEAVY, header_style="bold bright_cyan",
              show_edge=False, expand=True)
    t.add_column("When", style="dim", no_wrap=True)
    t.add_column("Kind", style="bold", no_wrap=True)
    t.add_column("Detail", overflow="fold")
    for ts, kind, detail in rows[:8]:
        style = {"REVIEW": "bright_cyan", "COMMIT": "dim"}.get(kind, "")
        decision_style = ""
        if kind == "REVIEW":
            decision_style = "green" if detail.startswith("approve") else "yellow"
        t.add_row(
            ts.astimezone().strftime("%m-%d %H:%M"),
            Text(kind, style=style),
            Text(detail, style=decision_style) if decision_style else detail,
        )
    console.print(t)


def _render_priority(console: Console, d: dict, *, limit: int = 3) -> None:
    order = d["snap"]["recommended_priority"][:limit]
    t = Table(title="PRIORITY QUEUE", box=box.SIMPLE_HEAVY, header_style="bold bright_cyan",
              show_edge=False, expand=True)
    t.add_column("#", justify="right", style="dim", width=3, no_wrap=True)
    t.add_column("Next action", style="bold", overflow="ellipsis")
    for i, item in enumerate(order, 1):
        t.add_row(str(i), item)
    console.print(t)


def _render_body(console: Console, d: dict, run: RunStats | None) -> None:
    height = console.size.height
    _render_header(console, d)
    _render_funnel(console, d)
    _render_run_and_health(console, d, run)
    if height >= 32:
        _render_goals(console, d)
    if height >= 42:
        _render_coverage(console, d)
    if height >= 70:
        _render_geography(console, d)
    if height >= 80:
        _render_activity(console, d)
        _render_priority(console, d)


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
        lines = lines[:height - 1] + ["[dim]… dashboard clipped to one screen; enlarge terminal for more rows[/dim]"]
    console.print("\n".join(lines))
