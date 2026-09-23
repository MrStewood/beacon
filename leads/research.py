#!/usr/bin/env python3
"""Beacon Lead Discovery — ZIP-based community resource research tool.

Usage:
    python3 leads/research.py prompt 40701          # Generate search prompt for a ZIP
    python3 leads/research.py process 40701 results.json  # Dedup and save findings
    python3 leads/research.py status                 # Show processing status
    python3 leads/research.py leads                  # List all discovered leads
    python3 leads/research.py out-of-area            # List resources found outside their ZIP
    python3 leads/research.py needs 40701            # Show Census needs indicators for a ZIP
    python3 leads/research.py needs KY               # Show state-level needs summary
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BEACON_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BEACON_ROOT / "data"
LEADS_DIR = BEACON_ROOT / "leads"
DEDUP_PATH = LEADS_DIR / "dedup.json"
PROMPT_TEMPLATE = LEADS_DIR / "search_prompt.md"

# ---------------------------------------------------------------------------
# ZIP → County lookup (US Census data, ~33K ZIPs)
# Source: data/census/us-zips.json (built by data/census/build_us_zips.py)
# ---------------------------------------------------------------------------

CENSUS_ZIPS_PATH = DATA_DIR / "census" / "us-zips.json"
_census_zips: Optional[Dict[str, Any]] = None


def _load_census_zips() -> Dict[str, Any]:
    """Lazy-load the Census ZIP lookup (33K records, loaded once)."""
    global _census_zips
    if _census_zips is None:
        if CENSUS_ZIPS_PATH.exists():
            _census_zips = json.loads(CENSUS_ZIPS_PATH.read_text(encoding="utf-8"))
        else:
            _census_zips = {}
    return _census_zips


# ---------------------------------------------------------------------------
# Beacon categories
# ---------------------------------------------------------------------------

CATEGORIES = [
    "food", "shelter", "housing", "health", "mental-health",
    "addiction", "crisis", "family", "legal", "documents",
    "education", "jobs", "transportation", "utility-assistance",
    "clothing", "community", "veterans",
]


# ---------------------------------------------------------------------------
# Dedup helpers
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Normalize org name for dedup comparison."""
    n = name.lower().strip()
    n = re.sub(r"[^\w\s]", "", n)
    n = re.sub(r"\s+", " ", n)
    # Remove common suffixes
    for suffix in [
        "inc", "llc", "ltd", "corp", "co", "company",
        "of ky", "of kentucky", "of eastern ky",
    ]:
        n = re.sub(rf"\b{re.escape(suffix)}\b", "", n)
    return n.strip()


def _normalize_phone(phone: str) -> str:
    """Strip to digits for phone dedup."""
    return re.sub(r"\D", "", phone)


def _resource_key(r: Dict[str, Any]) -> str:
    """Generate a dedup key from a resource record."""
    name = _normalize_name(r.get("name", ""))
    phones = sorted(_normalize_phone(p) for p in r.get("phones", []) if p)
    return f"{name}|{'|'.join(phones)}"


def load_dedup() -> Dict[str, Any]:
    if DEDUP_PATH.exists():
        return json.loads(DEDUP_PATH.read_text(encoding="utf-8"))
    return {
        "version": 1,
        "processed_zips": {},
        "discovered": {},
        "out_of_area": {},
        "stats": {
            "total_discovered": 0,
            "total_new": 0,
            "total_duplicates": 0,
            "total_out_of_area": 0,
            "last_run": None,
        },
    }


def save_dedup(dedup: Dict[str, Any]) -> None:
    LEADS_DIR.mkdir(parents=True, exist_ok=True)
    dedup_path = DEDUP_PATH
    dedup_path.write_text(json.dumps(dedup, indent=2, ensure_ascii=False), encoding="utf-8")


def load_existing_resources() -> List[Dict[str, Any]]:
    """Load all resources currently in Beacon's data directory."""
    resources: List[Dict[str, Any]] = []
    # Main resources.json
    main = DATA_DIR / "resources.json"
    if main.exists():
        data = json.loads(main.read_text(encoding="utf-8"))
        resources.extend(data.get("resources", []))
    # State-level
    for state_dir in (DATA_DIR / "states").iterdir() if (DATA_DIR / "states").exists() else []:
        sr = state_dir / "resources.json"
        if sr.exists():
            data = json.loads(sr.read_text(encoding="utf-8"))
            resources.extend(data.get("resources", []))
    return resources


def build_exclude_list(existing: List[Dict[str, Any]]) -> str:
    """Build a text list of existing resource names for the prompt."""
    names = sorted(set(r.get("name", "") for r in existing if r.get("name")))
    lines = [f"- {n}" for n in names]
    return "\n".join(lines) if lines else "(no existing resources to exclude)"


def resolve_zip(zip_code: str) -> Dict[str, str]:
    """Resolve ZIP code to county/state/city via Census data."""
    z = zip_code.strip().zfill(5)
    zips = _load_census_zips()
    entry = zips.get(z)
    if entry is None:
        return {"zip": z, "county": "Unknown", "state": "Unknown", "city": "Unknown"}
    # Multi-county ZIP: pick the first county entry
    if isinstance(entry, dict) and entry.get("_multi_county"):
        first = entry["counties"][0]
        return {"zip": z, "county": first["county"], "state": first["state"], "city": first["city"]}
    # Single-county ZIP
    if isinstance(entry, dict):
        return {"zip": z, "county": entry.get("county", "Unknown"), "state": entry.get("state", "Unknown"), "city": entry.get("city", "Unknown")}
    return {"zip": z, "county": "Unknown", "state": "Unknown", "city": "Unknown"}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_prompt(args: List[str]) -> None:
    """Generate a search prompt for the given ZIP code."""
    if len(args) < 1:
        print("Usage: research.py prompt <zip>", file=sys.stderr)
        sys.exit(1)
    zip_code = args[0]
    info = resolve_zip(zip_code)
    area = f"{info['county']} County, {info['state']}" if info["county"] != "Unknown" else f"ZIP {zip_code}"

    existing = load_existing_resources()
    exclude = build_exclude_list(existing)

    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    # Order matters: exclude_list is last because it may contain characters
    # that collide with other variable patterns. All $county/$zip/$state
    # references appear before the exclusion block in the template.
    prompt = (
        template
        .replace("$area_description", area)
        .replace("$zip", info["zip"])
        .replace("$county", info["county"])
        .replace("$state", info["state"])
        .replace("$exclude_list", exclude)
    )

    output = {
        "zip": info["zip"],
        "county": info["county"],
        "state": info["state"],
        "city": info.get("city", ""),
        "area_description": area,
        "prompt": prompt,
        "categories": CATEGORIES,
        "existing_resource_count": len(existing),
        "guidance": (
            "Feed this prompt to a research agent. "
            "It will search for resources and return structured JSON. "
            "Then run: python3 leads/research.py process <zip> <results.json>"
        ),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def cmd_process(args: List[str]) -> None:
    """Process research results: dedup and save."""
    if len(args) < 2:
        print("Usage: research.py process <zip> <results.json>", file=sys.stderr)
        sys.exit(1)
    zip_code = args[0].strip().zfill(5)
    results_path = Path(args[1])

    if not results_path.exists():
        print(f"Results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    results = json.loads(results_path.read_text(encoding="utf-8"))
    info = resolve_zip(zip_code)

    # Load existing for dedup
    existing = load_existing_resources()
    existing_keys = {_resource_key(r) for r in existing}

    # Load dedup store
    dedup = load_dedup()
    discovered_keys = set(dedup.get("discovered", {}).keys())

    new_leads = []
    duplicates = []
    out_of_area = []
    now = datetime.now(timezone.utc).isoformat()

    for resource in results.get("resources_found", []):
        key = _resource_key(resource)

        # Check against existing Beacon data
        if key in existing_keys:
            duplicates.append({"resource": resource, "reason": "already_in_beacon"})
            continue

        # Check against previously discovered leads
        if key in discovered_keys:
            duplicates.append({"resource": resource, "reason": "already_discovered"})
            continue

        # Check for near-duplicates (same name, similar phone)
        name_norm = _normalize_name(resource.get("name", ""))
        is_near_dup = False
        for dk in discovered_keys:
            dk_name = dk.split("|")[0] if "|" in dk else dk
            if dk_name and name_norm and dk_name == name_norm:
                is_near_dup = True
                duplicates.append({"resource": resource, "reason": f"near_dup:{dk}"})
                break

        if is_near_dup:
            continue

        # New lead!
        resource["first_seen"] = now
        resource["dedup_key"] = key
        new_leads.append(resource)
        discovered_keys.add(key)

        # Check if out of area
        found_zip = resource.get("found_outside_zip")
        if found_zip and found_zip != zip_code:
            out_of_area.append(resource)

    # Update dedup store
    for lead in new_leads:
        dedup["discovered"][lead["dedup_key"]] = {
            "name": lead.get("name", ""),
            "zip": lead.get("found_in_zip", zip_code),
            "first_seen": lead.get("first_seen", now),
            "county": info["county"],
            "state": info["state"],
        }

    for ooa in out_of_area:
        key = ooa.get("dedup_key", _resource_key(ooa))
        actual_zip = ooa.get("found_outside_zip", "unknown")
        dedup["out_of_area"][key] = {
            "name": ooa.get("name", ""),
            "serves_zip": zip_code,
            "located_zip": actual_zip,
            "county": info["county"],
            "first_seen": now,
        }

    dedup["processed_zips"][zip_code] = {
        "county": info["county"],
        "state": info["state"],
        "processed_at": now,
        "resources_found": len(results.get("resources_found", [])),
        "new_leads": len(new_leads),
        "duplicates": len(duplicates),
        "out_of_area": len(out_of_area),
    }

    dedup["stats"]["total_discovered"] = len(dedup.get("discovered", {}))
    dedup["stats"]["total_new"] = dedup["stats"].get("total_new", 0) + len(new_leads)
    dedup["stats"]["total_duplicates"] = dedup["stats"].get("total_duplicates", 0) + len(duplicates)
    dedup["stats"]["total_out_of_area"] = len(dedup.get("out_of_area", {}))
    dedup["stats"]["last_run"] = now

    save_dedup(dedup)

    # Write new leads file
    leads_file = LEADS_DIR / f"leads_{zip_code}_{now[:10]}.json"
    leads_file.write_text(
        json.dumps({
            "zip": zip_code,
            "county": info["county"],
            "state": info["state"],
            "processed_at": now,
            "new_leads": new_leads,
            "duplicates": duplicates,
            "out_of_area": out_of_area,
            "summary": {
                "total_found": len(results.get("resources_found", [])),
                "new": len(new_leads),
                "duplicates": len(duplicates),
                "out_of_area": len(out_of_area),
            },
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Print summary
    summary = {
        "ok": True,
        "zip": zip_code,
        "county": info["county"],
        "state": info["state"],
        "total_found": len(results.get("resources_found", [])),
        "new_leads": len(new_leads),
        "duplicates": len(duplicates),
        "out_of_area": len(out_of_area),
        "leads_file": str(leads_file),
        "dedup_total": dedup["stats"]["total_discovered"],
        "out_of_area_total": dedup["stats"]["total_out_of_area"],
    }
    print(json.dumps(summary, indent=2))


def cmd_status(args: List[str]) -> None:
    """Show processing status."""
    dedup = load_dedup()
    zips = dedup.get("processed_zips", {})
    stats = dedup.get("stats", {})
    summary = {
        "processed_zips": len(zips),
        "zip_list": sorted(zips.keys()),
        "total_discovered": stats.get("total_discovered", 0),
        "total_new": stats.get("total_new", 0),
        "total_duplicates": stats.get("total_duplicates", 0),
        "total_out_of_area": stats.get("total_out_of_area", 0),
        "last_run": stats.get("last_run"),
    }
    print(json.dumps(summary, indent=2))


def cmd_leads(args: List[str]) -> None:
    """List all discovered leads."""
    dedup = load_dedup()
    discovered = dedup.get("discovered", {})
    leads = [
        {
            "key": k,
            "name": v.get("name", ""),
            "zip": v.get("zip", ""),
            "county": v.get("county", ""),
            "first_seen": v.get("first_seen", ""),
        }
        for k, v in sorted(discovered.items(), key=lambda x: x[1].get("name", ""))
    ]
    print(json.dumps({"total": len(leads), "leads": leads}, indent=2))


def cmd_out_of_area(args: List[str]) -> None:
    """List resources found outside their target ZIP."""
    dedup = load_dedup()
    ooa = dedup.get("out_of_area", {})
    resources = [
        {
            "key": k,
            "name": v.get("name", ""),
            "serves_zip": v.get("serves_zip", ""),
            "located_zip": v.get("located_zip", ""),
            "county": v.get("county", ""),
        }
        for k, v in sorted(ooa.items(), key=lambda x: x[1].get("name", ""))
    ]
    print(json.dumps({"total": len(resources), "resources": resources}, indent=2))


def cmd_needs(args: List[str]) -> None:
    """Show Census needs indicators and resource coverage for a ZIP (or state)."""
    if len(args) < 1:
        print("Usage: research.py needs <zip|state_abbr>", file=sys.stderr)
        sys.exit(1)

    target = args[0].strip()
    # Load Census data
    census_path = DATA_DIR / "census" / "us-zips-census.json"
    if not census_path.exists():
        print(json.dumps({"error": "Census indicators not found. Run data/census/census_indicators.py first."}))
        sys.exit(1)
    census_data = json.loads(census_path.read_text(encoding="utf-8"))

    # Load needs analysis if available
    needs_path = DATA_DIR / "census" / "needs-analysis.json"
    needs_data = json.loads(needs_path.read_text(encoding="utf-8")) if needs_path.exists() else {}

    # Load existing resources
    existing = load_existing_resources()
    zip_counts: Dict[str, int] = {}
    for r in existing:
        locs = r.get("locations", [])
        if locs:
            for loc in locs:
                zc = (loc.get("postal_code") or loc.get("zip", "")).strip().zfill(5)
                if zc:
                    zip_counts[zc] = zip_counts.get(zc, 0) + 1
        else:
            zc = (r.get("zip", "") or r.get("postal_code", "")).strip().zfill(5)
            if zc:
                zip_counts[zc] = zip_counts.get(zc, 0) + 1

    # State-level summary
    if len(target) == 2 and target.isalpha():
        state = target.upper()
        state_summary = needs_data.get("state_summaries", {}).get(state)
        state_zips = {z: d for z, d in needs_data.get("zip_analysis", {}).items()
                      if d.get("state") == state}
        total_resources = sum(1 for z in state_zips if zip_counts.get(z, 0) > 0)
        output = {
            "type": "state",
            "state": state,
            "summary": state_summary,
            "resource_coverage": {
                "zips_with_resources": total_resources,
                "total_zips": len(state_zips),
            },
            "high_need_zips_sample": [
                {"zip": z, "need_score": d.get("need_score"), "poverty_rate": d.get("poverty_rate"),
                 "snap_rate": d.get("snap_rate"), "existing_resources": zip_counts.get(z, 0)}
                for z, d in sorted(state_zips.items(), key=lambda x: x[1].get("need_score") or 0, reverse=True)
                if d.get("need_flag") == "high"
            ][:20],
        }
        print(json.dumps(output, indent=2))
        return

    # ZIP-level
    zc = target.zfill(5)
    indicators = census_data.get(zc, {})
    needs = needs_data.get("zip_analysis", {}).get(zc, {})
    info = resolve_zip(zc)

    # Find nearby ZIPs in same county for context
    county = info.get("county", "Unknown")
    state = info.get("state", "Unknown")
    county_zips = {z: d for z, d in needs_data.get("zip_analysis", {}).items()
                   if d.get("county") == county and d.get("state") == state}
    county_resources = sum(zip_counts.get(z, 0) for z in county_zips)

    output = {
        "zip": zc,
        "county": county,
        "state": state,
        "city": info.get("city", ""),
        "census_indicators": indicators,
        "needs_score": needs.get("need_score"),
        "need_flag": needs.get("need_flag"),
        "existing_resources": zip_counts.get(zc, 0),
        "county_context": {
            "total_zips": len(county_zips),
            "county_total_resources": county_resources,
            "avg_poverty": round(sum(d.get("poverty_rate", 0) or 0 for d in county_zips.values()) / max(len(county_zips), 1), 1),
            "avg_snap": round(sum(d.get("snap_rate", 0) or 0 for d in county_zips.values()) / max(len(county_zips), 1), 1),
        },
    }
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

COMMANDS = {
    "prompt": cmd_prompt,
    "process": cmd_process,
    "status": cmd_status,
    "leads": cmd_leads,
    "out-of-area": cmd_out_of_area,
    "needs": cmd_needs,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: research.py <{'|'.join(COMMANDS.keys())}> [args...]", file=sys.stderr)
        print("Commands:", file=sys.stderr)
        print("  prompt <zip>                   Generate search prompt for a ZIP", file=sys.stderr)
        print("  process <zip> <results.json>   Dedup and save research results", file=sys.stderr)
        print("  status                         Show processing status", file=sys.stderr)
        print("  leads                          List all discovered leads", file=sys.stderr)
        print("  out-of-area                    List out-of-area resources", file=sys.stderr)
        print("  needs <zip|state>              Show Census needs indicators for a ZIP or state", file=sys.stderr)
        sys.exit(2)
    cmd = sys.argv[1]
    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
