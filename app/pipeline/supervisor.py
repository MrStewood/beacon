"""
Beacon Pipeline Supervisor
==========================
Reads pipeline state, decides the single best next action, optionally executes it.

Usage:
  python -m app.pipeline.supervisor              # decide + execute one step
  python -m app.pipeline.supervisor --loop       # run until idle/alert_human; dashboard between steps; Ctrl+C stops cleanly
  python -m app.pipeline.supervisor --dashboard  # render the data dashboard and exit
  python -m app.pipeline.supervisor --dry-run    # decide, print, don't execute
  python -m app.pipeline.supervisor --status     # print state snapshot only
  python -m app.pipeline.supervisor ack <slug>   # acknowledge a human alert
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

BEACON_ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APPROVED_DIR     = BEACON_ROOT / "source" / "approved"
CANDIDATES_DIR   = BEACON_ROOT / "source" / "candidates"
LEADS_DIR        = BEACON_ROOT / "leads"
INVESTIGATIONS_DIR = LEADS_DIR / "investigations"
REJECTED_DIR     = LEADS_DIR / "rejected"
ALERTS_DIR       = LEADS_DIR / "alerts"
DEDUP_FILE       = LEADS_DIR / "dedup.json"
EXPANSION_FILE   = LEADS_DIR / "EXPANSION.md"

# Category priority weights (higher = more urgent to fill)
CATEGORY_PRIORITY = {
    "crisis":           10,
    "shelter":           9,
    "food":              9,
    "health":            8,
    "mental-health":     8,
    "addiction":         7,
    "housing":           7,
    "family":            6,
    "legal":             6,
    "utility-assistance":5,
    "transportation":    5,
    "veterans":          4,
    "jobs":              4,
    "education":         3,
    "documents":         3,
    "clothing":          2,
    "community":         2,
}

SENSITIVE_CATEGORIES = {"crisis", "domestic-violence"}

# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------

def snapshot_state() -> dict[str, Any]:
    """Read all pipeline state into a structured dict. No LLM calls."""

    snap: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "alerts":       _read_alerts(),
        "approved":     _read_approved(),
        "candidates":   _read_candidates(),
        "investigations": _read_investigations(),
        "leads":        _read_leads(),
        "geography":    _read_geography(),
    }
    snap["coverage_gaps"] = _compute_gaps(snap)
    snap["recommended_priority"] = _priority_order(snap)
    return snap


def _read_alerts() -> dict:
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    alerts = []
    for p in sorted(ALERTS_DIR.glob("*.yaml")):
        try:
            a = yaml.safe_load(p.read_text()) or {}
            a["file"] = p.name
            alerts.append(a)
        except Exception:
            pass
    unacked = [a for a in alerts if not a.get("acknowledged")]
    return {
        "total": len(alerts),
        "unacknowledged": len(unacked),
        "items": unacked,
    }


def _read_approved() -> dict:
    by_category: dict[str, int] = {}
    by_county:   dict[str, int] = {}
    total = 0
    for p in APPROVED_DIR.rglob("*.yaml"):
        try:
            r = yaml.safe_load(p.read_text()) or {}
            for cat in r.get("needs", []):
                by_category[cat] = by_category.get(cat, 0) + 1
            county = p.parent.name
            by_county[county] = by_county.get(county, 0) + 1
            total += 1
        except Exception:
            pass
    return {"total": total, "by_category": by_category, "by_county": by_county}


def _read_candidates() -> dict:
    pending = []
    requeued = []
    for p in CANDIDATES_DIR.rglob("*.yaml"):
        try:
            c = yaml.safe_load(p.read_text()) or {}
            state = c.get("workflow_state", "")
            if state == "research-b-locked":
                pending.append({"path": str(p.relative_to(BEACON_ROOT)), "id": c.get("candidate_id", p.stem)})
            elif state == "needs-followup":
                requeued.append({
                    "path": str(p.relative_to(BEACON_ROOT)),
                    "id":   c.get("candidate_id", p.stem),
                    "questions": c.get("requeue", {}).get("questions_to_answer", []),
                })
        except Exception:
            pass
    return {
        "pending_review": len(pending),
        "requeued":       len(requeued),
        "pending_items":  pending,
        "requeued_items": requeued,
    }


def _read_investigations() -> dict:
    """Find investigations that don't yet have a matching candidate."""
    import re as _re3

    candidate_ids = {p.stem for p in CANDIDATES_DIR.rglob("*.yaml")}

    # Approved resource signals — skip investigations for already-published leads
    approved_names:   set[str] = set()
    approved_phones:  set[str] = set()
    approved_domains: set[str] = set()
    if APPROVED_DIR.exists():
        for p in APPROVED_DIR.rglob("*.yaml"):
            try:
                r = yaml.safe_load(p.read_text()) or {}
                n = (r.get("name") or "").lower().strip()
                if n:
                    approved_names.add(n)
                    approved_names.add(_slug(n, ""))
                for ph in r.get("phones", []):
                    approved_phones.add(_re3.sub(r"\D", "", str(ph)))
                for u in [r.get("url") or ""] + r.get("source_urls", []):
                    m = _re3.search(r"(?:https?://)?(?:www\.)?([^/]+)", u)
                    if m:
                        approved_domains.add(m.group(1).lower())
            except Exception:
                pass

    rejected_names: set[str] = set()
    if REJECTED_DIR.exists():
        for p in REJECTED_DIR.glob("*.yaml"):
            try:
                r = yaml.safe_load(p.read_text()) or {}
                n = (r.get("resource", {}).get("name") or r.get("name") or "").lower().strip()
                if n:
                    rejected_names.add(n)
            except Exception:
                pass

    investigated: list[dict] = []
    if not INVESTIGATIONS_DIR.exists():
        return {"needs_candidate": 0, "items": []}

    for zip_dir in INVESTIGATIONS_DIR.iterdir():
        if not zip_dir.is_dir():
            continue
        for p in zip_dir.glob("*.json"):
            try:
                inv = json.loads(p.read_text())
                is_complete = inv.get("complete") or (inv.get("pass_b") and inv.get("summary"))
                if not is_complete:
                    continue
                lead = inv.get("lead", {})
                name = (lead.get("name") or "").lower().strip()
                cid  = inv.get("candidate_id") or _slug(lead.get("name", ""), zip_dir.name)
                lead_phones = {_re3.sub(r"\D", "", str(ph)) for ph in lead.get("phones", [])}
                lead_domains: set[str] = set()
                for u in [lead.get("source_url") or ""] + lead.get("urls", []) + lead.get("domains", []):
                    m = _re3.search(r"(?:https?://)?(?:www\.)?([^/\s]+)", str(u))
                    if m:
                        lead_domains.add(m.group(1).lower())
                already_done = (
                    cid in candidate_ids
                    or name in approved_names
                    or _slug(name, "") in approved_names
                    or name in rejected_names
                    or bool(lead_phones & approved_phones)
                    or bool(lead_domains & approved_domains)
                )
                if not already_done:
                    investigated.append({
                        "path":     str(p.relative_to(BEACON_ROOT)),
                        "zip":      zip_dir.name,
                        "name":     lead.get("name", p.stem),
                        "category": lead.get("category", "unknown"),
                    })
            except Exception:
                pass
    return {"needs_candidate": len(investigated), "items": investigated}


def _read_leads() -> dict:
    """Aggregate leads from run files — richer than dedup.json (has category)."""
    by_category:  dict[str, int] = {}
    by_zip:       dict[str, int] = {}
    by_status:    dict[str, int] = {}
    by_cat_status: dict[str, dict[str, int]] = {}
    sensitive_pending = []
    all_queued:   list[dict]    = []

    # Load investigated slugs — strip the zip prefix so we can match by name alone
    investigated_name_slugs: set[str] = set()
    if INVESTIGATIONS_DIR.exists():
        for zd in INVESTIGATIONS_DIR.iterdir():
            if zd.is_dir():
                for f in zd.glob("*.json"):
                    # stem is like "40743-cvdvs-london-..." — strip leading zip
                    stem = f.stem
                    import re as _re
                    name_part = _re.sub(r"^\d{5}-", "", stem)
                    investigated_name_slugs.add(stem)          # full slug
                    investigated_name_slugs.add(name_part)     # name-only slug

    # Load rejected lead names
    rejected_names: set[str] = set()
    if REJECTED_DIR.exists():
        for p in REJECTED_DIR.glob("*.yaml"):
            try:
                r = yaml.safe_load(p.read_text()) or {}
                n = (r.get("resource", {}).get("name") or r.get("name") or "").lower().strip()
                if n:
                    rejected_names.add(n)
            except Exception:
                pass

    # Load approved resource signals — leads matching any of these are already published
    import re as _re2
    approved_names:   set[str] = set()
    approved_phones:  set[str] = set()
    approved_domains: set[str] = set()
    if APPROVED_DIR.exists():
        for p in APPROVED_DIR.rglob("*.yaml"):
            try:
                r = yaml.safe_load(p.read_text()) or {}
                n = (r.get("name") or "").lower().strip()
                if n:
                    approved_names.add(n)
                    approved_names.add(_slug(n, ""))
                for ph in r.get("phones", []):
                    approved_phones.add(_re2.sub(r"\D", "", str(ph)))
                for u in [r.get("url", "")] + r.get("source_urls", []):
                    if u:
                        m = _re2.search(r"(?:https?://)?(?:www\.)?([^/]+)", u)
                        if m:
                            approved_domains.add(m.group(1).lower())
            except Exception:
                pass


    # Read dedup.json for canonical lead list + status
    dedup: dict[str, dict] = {}
    if DEDUP_FILE.exists():
        raw = json.loads(DEDUP_FILE.read_text())
        dedup = raw.get("discovered", {})

    # Enrich with category from run files
    cat_by_name: dict[str, str] = {}
    for run_file in LEADS_DIR.glob("leads_*.json"):
        try:
            run = json.loads(run_file.read_text())
            for lead in run.get("new_leads", []):
                cat_by_name[lead["name"].lower().strip()] = lead.get("category", "unknown")
        except Exception:
            pass

    for slug, lead in dedup.items():
        name   = lead.get("name", "")
        cat    = cat_by_name.get(name.lower().strip(), "unknown")
        zip_   = lead.get("zip", "unknown")
        name_slug = _slug(name, "")
        full_slug = _inv_slug(zip_, name)

        # Phone digits from the lead slug key (format: "name|digits")
        lead_phones: set[str] = set()
        if "|" in slug:
            lead_phones.add(slug.split("|", 1)[1].strip())
        for ph in lead.get("phones", []):
            lead_phones.add(_re2.sub(r"\D", "", str(ph)))

        # Domain from lead URL
        lead_domains: set[str] = set()
        for u in ([lead.get("source_url", "")] + lead.get("urls", []) + lead.get("domains", [])):
            if u:
                m = _re2.search(r"(?:https?://)?(?:www\.)?([^/\s]+)", str(u))
                if m:
                    lead_domains.add(m.group(1).lower())

        is_done = (
            full_slug in investigated_name_slugs
            or name_slug in investigated_name_slugs
            or name.lower().strip() in rejected_names
            or name.lower().strip() in approved_names
            or _slug(name, "") in approved_names
            or bool(lead_phones & approved_phones)
            or bool(lead_domains & approved_domains)
        )
        status = "investigated" if is_done else "queued"

        by_category[cat] = by_category.get(cat, 0) + 1
        by_zip[zip_]      = by_zip.get(zip_, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        cs = by_cat_status.setdefault(cat, {"queued": 0, "investigated": 0})
        cs[status] = cs.get(status, 0) + 1

        if cat in SENSITIVE_CATEGORIES and status == "queued":
            sensitive_pending.append({"name": name, "category": cat, "zip": zip_})

        if status == "queued":
            all_queued.append({
                "slug":     slug,
                "name":     name,
                "category": cat,
                "zip":      zip_,
                "priority": CATEGORY_PRIORITY.get(cat, 1),
            })

    # Sort queued leads by category priority desc
    all_queued.sort(key=lambda x: -x["priority"])

    return {
        "total":             len(dedup),
        "by_category":       by_category,
        "by_cat_status":     by_cat_status,
        "by_zip":            by_zip,
        "by_status":         by_status,
        "queued_count":      by_status.get("queued", 0),
        "investigated_count":by_status.get("investigated", 0),
        "sensitive_pending": sensitive_pending,
        "next_queued":       all_queued[:10],   # top 10 for LLM context
    }


def _read_geography() -> dict:
    """Read expansion plan ZIPs."""
    zips_done = []
    zips_next = []
    if DEDUP_FILE.exists():
        raw = json.loads(DEDUP_FILE.read_text())
        zips_done = list(raw.get("processed_zips", {}).keys())

    if EXPANSION_FILE.exists():
        text = EXPANSION_FILE.read_text()
        import re
        # Extract ZIP codes from expansion file lines not marked done
        for line in text.splitlines():
            zips_in_line = re.findall(r"\b4\d{4}\b", line)
            if zips_in_line and "done" not in line.lower() and "complete" not in line.lower():
                for z in zips_in_line:
                    if z not in zips_done and z not in zips_next:
                        zips_next.append(z)

    return {
        "zips_researched": zips_done,
        "zips_pending":    zips_next[:5],
    }


def _compute_gaps(snap: dict) -> list[dict]:
    """Which categories have leads available but zero approved records?"""
    approved_cats = snap["approved"]["by_category"]
    lead_cats     = snap["leads"]["by_category"]
    gaps = []
    for cat, lead_count in sorted(lead_cats.items(), key=lambda x: -CATEGORY_PRIORITY.get(x[0], 1)):
        if cat == "unknown":
            continue
        approved = approved_cats.get(cat, 0)
        if approved == 0 and lead_count > 0:
            gaps.append({
                "category": cat,
                "priority": CATEGORY_PRIORITY.get(cat, 1),
                "leads_available": lead_count,
                "approved": 0,
            })
    return gaps


def _priority_order(snap: dict) -> list[str]:
    """Deterministic priority queue the LLM uses as a tiebreaker."""
    order = []
    if snap["alerts"]["unacknowledged"] > 0:
        order.append("alert_human: unacknowledged alerts exist")
    if snap["candidates"]["requeued"] > 0:
        order.append("run_followup")
    if snap["candidates"]["pending_review"] > 0:
        order.append("review_candidate")
    if snap["investigations"]["needs_candidate"] > 0:
        order.append("build_candidate")
    if snap["leads"]["queued_count"] > 0:
        order.append("investigate_lead")
    if snap["leads"]["queued_count"] < 5 and snap["geography"]["zips_pending"]:
        order.append("research_zip or expand_geography")
    if not order:
        order.append("idle")
    return order


# ---------------------------------------------------------------------------
# Decision (one LLM call)
# ---------------------------------------------------------------------------

async def decide(snap: dict) -> dict:
    """Ask the LLM for one typed action decision. Returns action dict."""
    import app.llm as llm

    # Hard-coded gates — no LLM needed; target is always deterministic here
    if snap["alerts"]["unacknowledged"] > 0:
        alert = snap["alerts"]["items"][0]
        return {"action": "alert_human", "target": alert.get("file", "unknown"),
                "reason": f"Unacknowledged alert: {alert.get('message', 'see alerts dir')}",
                "priority": 5, "auto": True}
    if snap["candidates"]["requeued"] > 0:
        item = snap["candidates"]["requeued_items"][0]
        return {"action": "run_followup", "target": item["id"],
                "reason": "Requeued candidate needs follow-up investigation.",
                "priority": 5, "auto": True}
    if snap["candidates"]["pending_review"] > 0:
        item = snap["candidates"]["pending_items"][0]
        return {"action": "review_candidate", "target": item["id"],
                "reason": "Candidate is ready for AI review.",
                "priority": 5, "auto": True}
    if snap["investigations"]["needs_candidate"] > 0:
        item = snap["investigations"]["items"][0]
        return {"action": "build_candidate", "target": item["path"],
                "reason": f"Investigation complete for {item['name']} — build candidate YAML.",
                "priority": 5, "auto": True}

    # LLM decision for everything else
    prompt = _build_prompt(snap)
    resp = await llm.flash(
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    raw = resp.choices[0].message.content
    try:
        action = json.loads(raw)
        action.setdefault("action", "idle")
        action.setdefault("reason", "")
        action.setdefault("priority", 1)
        action.setdefault("target", None)
        return action
    except Exception as e:
        log.error("Failed to parse LLM decision: %s\nRaw: %s", e, raw)
        return {"action": "idle", "reason": f"parse error: {e}", "priority": 0}


def _build_prompt(snap: dict) -> str:
    approved   = snap["approved"]
    candidates = snap["candidates"]
    leads      = snap["leads"]
    invs       = snap["investigations"]
    gaps       = snap["coverage_gaps"]
    geo        = snap["geography"]
    priority   = snap["recommended_priority"]

    gap_text = "\n".join(
        f"  - {g['category']} (priority {g['priority']}/10): {g['leads_available']} leads available, 0 approved"
        for g in gaps[:8]
    ) or "  none"

    next_leads = "\n".join(
        f"  - [{l['category']} p{l['priority']}] {l['name']} (ZIP {l['zip']})"
        for l in leads["next_queued"][:6]
    ) or "  none"

    requeued_text = "\n".join(
        f"  - {r['id']}: {r['questions'][0][:80] if r['questions'] else 'no questions listed'}"
        for r in candidates["requeued_items"][:3]
    ) or "  none"

    pending_text = "\n".join(
        f"  - {c['id']}"
        for c in candidates["pending_items"][:3]
    ) or "  none"

    needs_cand_text = "\n".join(
        f"  - {i['name']} ({i['category']}, {i['zip']})"
        for i in invs["items"][:3]
    ) or "  none"

    return f"""You are the Beacon Pipeline Supervisor. Decide the single best next pipeline action.

## Current State

### Approved records
Total: {approved['total']}
By category: {json.dumps(approved['by_category'])}
By county: {json.dumps(approved['by_county'])}

### Candidates
Pending review: {candidates['pending_review']}
{pending_text}
Requeued (need follow-up): {candidates['requeued']}
{requeued_text}

### Investigations without a candidate yet
{invs['needs_candidate']} items:
{needs_cand_text}

### Lead queue
Total leads: {leads['total']}
Queued (uninvestigated): {leads['queued_count']}
Already investigated: {leads['investigated_count']}
By category: {json.dumps(leads['by_category'])}

### Coverage gaps (0 approved, leads available)
{gap_text}

### Top queued leads by priority
{next_leads}

### Geography
Researched ZIPs: {geo['zips_researched']}
Next ZIPs in expansion plan: {geo['zips_pending']}

### Deterministic priority order
{chr(10).join(f"  {i+1}. {p}" for i,p in enumerate(priority))}

## Your task

Return a JSON object with exactly these fields:
{{
  "action": one of: investigate_lead | build_candidate | review_candidate | run_followup | research_zip | expand_geography | alert_human | idle,
  "target": the specific lead slug, candidate path, ZIP code, or alert subject (string or null),
  "reason": 1-2 sentence explanation of why this action is the best choice right now,
  "priority": integer 1-5 (5 = most urgent),
  "human_message": only if action=alert_human — what to tell the human (string or null)
}}

Rules:
- Pick exactly ONE action
- Follow the deterministic priority order unless you have a strong specific reason not to
- For investigate_lead: set target to the name of the highest-priority queued lead
- Do not invent leads, candidates, or ZIPs not shown above
- Be terse — reason should be factual, not chatty
""".strip()


# ---------------------------------------------------------------------------
# Execution stubs (wire to real modules)
# ---------------------------------------------------------------------------

def execute(action: dict) -> None:
    """Dispatch the decided action to the appropriate pipeline module."""
    a      = action["action"]
    target = action.get("target")
    meta   = action.get("meta", {})   # extra data the LLM may pass (lead dict, paths, etc.)

    def _run(*args: str) -> None:
        cmd = [sys.executable, "-m"] + list(args)
        log.info("running: %s", " ".join(cmd))
        result = subprocess.run(cmd, cwd=BEACON_ROOT)
        if result.returncode != 0:
            log.warning("command exited %d: %s", result.returncode, " ".join(cmd))

    if a == "investigate_lead":
        # target is the lead name; look it up in dedup.json to get full lead data
        lead_json = _resolve_lead(target)
        if lead_json is None:
            log.error("investigate_lead: could not find lead %r in dedup.json", target)
            return
        _run("app.pipeline.investigate", "--json", json.dumps(lead_json))

    elif a == "build_candidate":
        # target is the investigation JSON file path
        inv_path = _resolve_investigation(target)
        if inv_path is None:
            log.error("build_candidate: no investigation file found for %r", target)
            return
        _run("app.pipeline.candidate", str(inv_path))

    elif a == "review_candidate":
        # target is the candidate YAML path or candidate ID
        cand_path = _resolve_candidate(target)
        if cand_path is None:
            log.error("review_candidate: no candidate file found for %r", target)
            return
        _run("app.pipeline.review_candidate", str(cand_path))

    elif a == "run_followup":
        cand_path = _resolve_candidate(target)
        if cand_path:
            _run("app.pipeline.followup", str(cand_path))

    elif a == "research_zip":
        _run("app.pipeline.research", str(target))

    elif a == "expand_geography":
        _run("app.pipeline.research", str(target))

    elif a == "alert_human":
        _write_alert(action)
        log.info("⚠ Alert written to leads/alerts/")

    elif a == "idle":
        log.info("nothing to do right now")

    else:
        log.warning("unknown action: %r", a)


def _resolve_lead(name: str | None) -> dict | None:
    """Look up a lead by name in dedup.json and return its full dict."""
    if not name or not DEDUP_FILE.exists():
        return None
    dedup = json.loads(DEDUP_FILE.read_text()).get("discovered", {})
    name_lower = name.lower().strip()
    for slug, lead in dedup.items():
        if lead.get("name", "").lower().strip() == name_lower:
            return {**lead, "slug": slug}
    return None


def _resolve_investigation(target: str | None) -> Path | None:
    """Find the most recent investigation JSON file matching target."""
    if not target or not INVESTIGATIONS_DIR.exists():
        return None
    # target may be a path or a name slug
    p = Path(target)
    if p.exists():
        return p
    target_slug = target.lower().replace(" ", "-")
    matches = sorted(INVESTIGATIONS_DIR.rglob(f"*{target_slug}*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _resolve_candidate(target: str | None) -> Path | None:
    """Find a candidate YAML file matching target (path or name slug)."""
    if not target or not CANDIDATES_DIR.exists():
        return None
    p = Path(target)
    if p.exists():
        return p
    target_slug = target.lower().replace(" ", "-")
    matches = sorted(CANDIDATES_DIR.rglob(f"*{target_slug}*.yaml"), key=lambda x: x.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _write_alert(action: dict) -> None:
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug(action.get("target", "unknown"), "alert")
    ts   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = ALERTS_DIR / f"{ts}-{slug[:40]}.yaml"
    with open(path, "w") as f:
        yaml.dump({
            "created_at":    datetime.now(timezone.utc).isoformat(),
            "acknowledged":  False,
            "action":        action["action"],
            "target":        action.get("target"),
            "reason":        action.get("reason"),
            "human_message": action.get("human_message"),
        }, f, allow_unicode=True, sort_keys=False)


def acknowledge_alert(slug: str) -> None:
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    matches = list(ALERTS_DIR.glob(f"*{slug}*"))
    if not matches:
        print(f"No alert matching {slug!r}")
        return
    for p in matches:
        a = yaml.safe_load(p.read_text()) or {}
        a["acknowledged"] = True
        a["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
        with open(p, "w") as f:
            yaml.dump(a, f, allow_unicode=True, sort_keys=False)
        print(f"Acknowledged: {p.name}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(name: str, zip_: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower())[:60].strip("-")


def _inv_slug(zip_: str, name: str) -> str:
    import re
    n = re.sub(r"[^a-z0-9]+", "-", name.lower())[:50].strip("-")
    return f"{zip_}-{n}"


def _print_snapshot(snap: dict) -> None:
    a  = snap["approved"]
    ca = snap["candidates"]
    l  = snap["leads"]
    iv = snap["investigations"]
    g  = snap["coverage_gaps"]
    al = snap["alerts"]

    print("\n" + "="*60)
    print("  BEACON PIPELINE STATUS")
    print("="*60)
    print(f"  Approved records:    {a['total']}")
    print(f"  By category:         {a['by_category'] or 'none'}")
    print(f"  By county:           {a['by_county'] or 'none'}")
    print()
    print(f"  Candidates pending:  {ca['pending_review']}")
    print(f"  Candidates requeued: {ca['requeued']}")
    print(f"  Needs candidate:     {iv['needs_candidate']}")
    print()
    print(f"  Total leads:         {l['total']}")
    print(f"  Queued (uninvestig): {l['queued_count']}")
    print(f"  Investigated:        {l['investigated_count']}")
    print()
    print(f"  Coverage gaps ({len(g)}):")
    for gap in g[:6]:
        print(f"    [{gap['priority']:2d}] {gap['category']:20s} {gap['leads_available']} leads, 0 approved")
    print()
    print(f"  Unacknowledged alerts: {al['unacknowledged']}")
    print()
    print(f"  Priority order:")
    for i, p in enumerate(snap["recommended_priority"]):
        print(f"    {i+1}. {p}")
    print("="*60 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# Actions that require human input before the loop can continue
_STOP_ACTIONS = {"idle", "alert_human"}


def _run_one(*, dry_run: bool = False, view: str = "plain", run=None) -> str:
    """Snapshot → decide → execute. Returns the action taken."""
    import asyncio
    snap = snapshot_state()
    if view == "dashboard":
        from app.pipeline import dashboard
        dash = dashboard.get_console()
        dash.clear()
        dashboard.render(snap=snap, run=run)
        action = asyncio.run(decide(snap))
        if not dry_run:
            execute(action)
        if run is not None:
            run.record(action["action"], action.get("target"))
        dash.clear()
        dashboard.render(snap=snapshot_state(), run=run)
        return action["action"]

    _print_snapshot(snap)
    print("Deciding next action...")
    action = asyncio.run(decide(snap))
    print(f"\n{'='*60}")
    print(f"  DECISION: {action['action'].upper()}")
    print(f"  Target:   {action.get('target') or '—'}")
    print(f"  Priority: {action.get('priority')}/5")
    print(f"  Reason:   {action.get('reason')}")
    if action.get("human_message"):
        print(f"  Message:  {action['human_message']}")
    print(f"{'='*60}\n")
    if not dry_run:
        execute(action)
    else:
        print("(dry-run — not executing)")
    if run is not None:
        run.record(action["action"], action.get("target"))
    return action["action"]


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s — %(message)s")

    ap = argparse.ArgumentParser(description="Beacon Pipeline Supervisor")
    ap.add_argument("--dry-run", action="store_true", help="Decide but don't execute")
    ap.add_argument("--status",  action="store_true", help="Print state snapshot only")
    ap.add_argument("--loop",    action="store_true",
                    help="Run continuously until idle, alert_human, or Ctrl+C")
    ap.add_argument("--dashboard", action="store_true",
                    help="Render the data dashboard once and exit")
    ap.add_argument("command",   nargs="?", help="ack <slug> to acknowledge alert")
    ap.add_argument("slug",      nargs="?", help="Alert slug to acknowledge")
    args = ap.parse_args()

    if args.command == "ack":
        if not args.slug:
            print("Usage: supervisor ack <slug>")
            sys.exit(1)
        acknowledge_alert(args.slug)
        return

    if args.dashboard:
        from app.pipeline import dashboard
        dashboard.render()
        return

    if args.status:
        _print_snapshot(snapshot_state())
        return

    if args.loop:
        import signal, time
        from app.pipeline.dashboard import RunStats
        run = RunStats()
        _stop_requested = False

        def _handle_sigint(sig, frame):
            nonlocal _stop_requested
            if _stop_requested:
                print("\nForce quit.")
                sys.exit(1)
            _stop_requested = True
            print("\n[Ctrl+C] Finishing current step then stopping… (Ctrl+C again to force quit)")

        signal.signal(signal.SIGINT, _handle_sigint)

        step = 0
        print("\nRunning in loop mode.  Ctrl+C = finish current step then stop.\n")
        while True:
            if _stop_requested:
                print("Stopped cleanly.")
                break
            step += 1
            taken = _run_one(dry_run=args.dry_run, view="dashboard", run=run)
            if taken in _STOP_ACTIONS:
                print(f"\nLoop stopped: action={taken}. Nothing more to do right now.")
                break
            time.sleep(3)
        return

    _run_one(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
