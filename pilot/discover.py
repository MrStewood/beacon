#!/usr/bin/env python3
"""Lead discovery for Beacon — finds community resources in a given area.

Takes a county name, zip code, or city+state and searches for
community resources. Creates lead entries that enter the pipeline
at the 'received' state.

Usage:
    python pilot/discover.py "Laurel County, KY"
    python pilot/discover.py "40741"
    python pilot/discover.py "London, KY"
    python pilot/discover.py --list-sources
    python pilot/discover.py --from-211 "Laurel County, KY"

Discovery modes:
    web         Search the web for resources (default)
    211         Search 211 directory
    government  Search government resource pages
    all         All available sources
"""

from __future__ import annotations

import json
import re
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PILOT_DIR = REPO_ROOT / "pilot"
CASES_DIR = PILOT_DIR / "cases"
DISCOVERY_LOG = PILOT_DIR / "discovery"
CONFIG_PATH = PILOT_DIR / "manual_pilot.json"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def check地理限制(config: dict, county: str | None = None, state: str | None = None) -> bool:
    """Check if the area is within pilot limits."""
    limits = config.get("pilot_limits", {})
    allowed = limits.get("allowed_geography", {})

    if county and county not in allowed.get("counties", []):
        print(f"WARNING: '{county}' is not in allowed counties {allowed.get('counties')}")
        print("  This lead will be created but may be rejected during triage.")
        return False
    if state and state not in allowed.get("states", []):
        print(f"WARNING: '{state}' is not in allowed states {allowed.get('states')}")
        print("  This lead will be created but may be rejected during triage.")
        return False
    return True


def parse_location_input(location: str) -> dict:
    """Parse a location string into structured components."""
    result = {"raw": location}

    # Zip code
    zip_match = re.search(r'\b(\d{5})(?:-\d{4})?\b', location)
    if zip_match:
        result["zip"] = zip_match.group(1)
        result["type"] = "zip"
        return result

    # County pattern
    county_match = re.search(r'(.+?)\s+County', location, re.IGNORECASE)
    if county_match:
        result["county"] = county_match.group(1).strip()
        result["type"] = "county"
        # Try to extract state
        state_match = re.search(r',\s*([A-Z]{2})\b', location)
        if state_match:
            result["state"] = state_match.group(1)
        return result

    # City, State pattern
    city_match = re.match(r'(.+?),\s*([A-Z]{2})', location)
    if city_match:
        result["city"] = city_match.group(1).strip()
        result["state"] = city_match.group(2)
        result["type"] = "city"
        return result

    # Bare state
    state_match = re.match(r'^([A-Z]{2})$', location.strip())
    if state_match:
        result["state"] = state_match.group(1)
        result["type"] = "state"
        return result

    result["type"] = "unknown"
    return result


def generate_case_id(name: str, location: dict) -> str:
    """Generate a stable case ID from resource name and location."""
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    loc_part = ""
    if location.get("county"):
        loc_part = re.sub(r'[^a-z0-9]+', '-', location["county"].lower()).strip('-')
    elif location.get("zip"):
        loc_part = f"zip-{location['zip']}"
    elif location.get("city"):
        loc_part = re.sub(r'[^a-z0-9]+', '-', location["city"].lower()).strip('-')

    if loc_part:
        return f"{loc_part}-{slug}"
    return slug


def check_duplicate(name: str, address: str | None, url: str | None, location: dict) -> str | None:
    """Check if this lead duplicates an existing case or approved record.
    Returns reason string if duplicate, None if unique."""
    name_lower = name.lower().strip()

    # Check existing cases
    for f in CASES_DIR.glob("*.json"):
        case = json.loads(f.read_text())
        lead = case.get("lead", {})
        existing_name = lead.get("name", "").lower().strip()
        # Exact name match
        if existing_name == name_lower:
            return f"exact name match in case {case.get('case_id')}"
        # Fuzzy name match (first 20 chars)
        if len(name_lower) > 10 and len(existing_name) > 10:
            if name_lower[:20] == existing_name[:20]:
                return f"fuzzy name match in case {case.get('case_id')}"
        # Same address
        if address and lead.get("proposed_address"):
            if address.lower().strip() == lead["proposed_address"].lower().strip():
                return f"same address in case {case.get('case_id')}"

    # Check approved records
    approved_dir = REPO_ROOT / "source" / "approved"
    if approved_dir.exists():
        for f in approved_dir.rglob("*.yaml"):
            try:
                import yaml
                rec = yaml.safe_load(f.read_text())
                rec_name = (rec.get("name", "") or "").lower().strip()
                if rec_name == name_lower:
                    return f"approved record exists at {f.relative_to(REPO_ROOT)}"
            except Exception:
                pass

    return None


def check_rejected(name: str) -> bool:
    """Check if this lead was previously rejected."""
    rejected_dir = PILOT_DIR / "rejected"
    if not rejected_dir.exists():
        return False
    for f in rejected_dir.glob("*.json"):
        try:
            rejected = json.loads(f.read_text())
            if rejected.get("name", "").lower().strip() == name.lower().strip():
                return True
        except Exception:
            pass
    return False


def create_lead(
    name: str,
    description: str,
    address: str | None = None,
    phone: str | None = None,
    url: str | None = None,
    category: str = "unknown",
    needs: list[str] | None = None,
    source_type: str = "discovery",
    source_url: str | None = None,
    location: dict | None = None,
    risk_tier: str = "low",
) -> dict:
    """Create a lead entry and save it as a case file.
    Unlimited leads in 'received' state. Only active cases count toward limits."""
    config = load_config()
    loc = location or {}

    case_id = generate_case_id(name, loc)

    # Check if case already exists
    existing = CASES_DIR / f"{case_id}.json"
    if existing.exists():
        print(f"SKIP: Case '{case_id}' already exists for '{name}'")
        return json.loads(existing.read_text())

    # Check for duplicates
    dup_reason = check_duplicate(name, address, url, loc)
    if dup_reason:
        print(f"SKIP: '{name}' is a duplicate — {dup_reason}")
        return {"case_id": case_id, "name": name, "status": "skipped-duplicate", "reason": dup_reason}

    # Check for previously rejected leads
    if check_rejected(name):
        print(f"SKIP: '{name}' was previously rejected")
        return {"case_id": case_id, "name": name, "status": "skipped-rejected"}

    # Check pilot limits (only count ACTIVE cases, not received leads)
    limits = config.get("pilot_limits", {})
    max_active = limits.get("max_active_cases", 1)
    active_count = sum(
        1 for f in CASES_DIR.glob("*.json")
        if json.loads(f.read_text()).get("state", "").endswith("-active")
    )

    # Create case
    case = {
        "case_id": case_id,
        "test_only": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "state": "received",
        "lead": {
            "source_type": source_type,
            "received_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "name": name,
            "description": description,
            "proposed_address": address,
            "proposed_phone": phone,
            "proposed_url": url,
            "proposed_category": category,
            "proposed_needs": needs or [],
            "proposed_risk_tier": risk_tier,
            "proposed_geography": {
                "coverage_scope": "county" if loc.get("county") else "unknown",
                "states_served": [loc["state"]] if loc.get("state") else [],
                "county": loc.get("county"),
            },
            "source_url": source_url,
            "notes": f"Discovered via {source_type} search for '{location.get('raw', 'unknown')}'",
        },
        "history": [
            {
                "from": None,
                "to": "received",
                "triggered_at": datetime.now(timezone.utc).isoformat(),
                "note": f"Lead discovered via {source_type}",
            }
        ],
    }

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    case_path = CASES_DIR / f"{case_id}.json"
    case_path.write_text(json.dumps(case, indent=2) + "\n")

    print(f"CREATED: {case_id}")
    print(f"  Name: {name}")
    print(f"  Address: {address or 'unknown'}")
    print(f"  Phone: {phone or 'unknown'}")
    print(f"  URL: {url or 'unknown'}")
    print(f"  Category: {category}")
    print(f"  Risk tier: {risk_tier}")
    print(f"  State: received")

    return case


def cmd_discover(args: list[str]) -> int:
    """Main discovery command — search for resources in an area."""
    if not args:
        print("Usage: discover.py <county or zip or city,state>")
        print("  e.g. discover.py \"Laurel County, KY\"")
        print("  e.g. discover.py \"40741\"")
        print("  e.g. discover.py \"London, KY\"")
        return 1

    location_str = " ".join(args)
    location = parse_location_input(location_str)

    print(f"=== Discovery: {location_str} ===")
    print(f"Parsed: type={location.get('type')}, county={location.get('county')}, "
          f"city={location.get('city')}, state={location.get('state')}, "
          f"zip={location.get('zip')}")
    print()

    # Check pilot limits
    config = load_config()
    limits = config.get("pilot_limits", {})
    allowed_geo = limits.get("allowed_geography", {})

    if location.get("county") and location["county"] not in allowed_geo.get("counties", []):
        print(f"NOTE: '{location['county']}' is not in pilot scope ({allowed_geo.get('counties')})")
        print("  Leads will still be created for testing, but triage may reject them.")
        print()

    # Generate search queries based on input type
    queries = _build_search_queries(location)
    print(f"Search queries to run:")
    for i, q in enumerate(queries, 1):
        print(f"  {i}. {q}")
    print()

    # Check discovery config
    discovery_enabled = config.get("safety_switches", {}).get("discovery_enabled", False)
    if not discovery_enabled:
        print("NOTE: discovery_enabled is OFF in safety switches.")
        print("  Discovery results will be logged but not automatically processed.")
        print("  To enable discovery, set discovery_enabled=true in manual_pilot.json")
        print()

    print("To run discovery, use the web_search tool with these queries")
    print("and feed results into create_lead().")
    print()
    print("Or run interactively:")
    print(f'  python pilot/discover.py --web "{location_str}"')
    return 0


def _build_search_queries(location: dict) -> list[str]:
    """Build search queries based on location type."""
    queries = []
    loc_str = location.get("raw", "")

    if location.get("type") == "county":
        state = location.get("state", "KY")
        county = location.get("county", "")
        queries = [
            f"{county} County {state} community resources",
            f"{county} County {state} food bank pantry",
            f"{county} County {state} housing assistance",
            f"{county} County {state} crisis hotline",
            f"{county} County {state} health department",
            f"{county} County {state} mental health services",
            f"{county} County {state} addiction recovery",
            f"{county} County {state} veteran services",
        ]
    elif location.get("type") == "zip":
        queries = [
            f"zip code {location['zip']} community resources",
            f"{location['zip']} food bank pantry",
            f"{location['zip']} housing assistance",
            f"{location['zip']} crisis services",
        ]
    elif location.get("type") == "city":
        city = location.get("city", "")
        state = location.get("state", "KY")
        queries = [
            f"{city} {state} community resources",
            f"{city} {state} food bank pantry",
            f"{city} {state} housing assistance",
            f"{city} {state} crisis services",
        ]
    else:
        queries = [f"{loc_str} community resources"]

    return queries


def cmd_from_211(args: list[str]) -> int:
    """Search 211 directory for resources."""
    if not args:
        print("Usage: discover.py --from-211 \"Laurel County, KY\"")
        return 1

    location_str = " ".join(args)
    location = parse_location_input(location_str)

    print(f"=== 211 Discovery: {location_str} ===")
    print("211 directory search requires web access.")
    print("Use the web_search tool with:")
    print(f'  query: "211 {location_str} resources"')
    print(f'  or: "site:211.org {location_str}"')
    print()
    print("Extract resource names, phones, and addresses from results,")
    print("then feed them into create_lead().")
    return 0


def cmd_list_sources(args: list[str]) -> int:
    """List available discovery sources."""
    print("=== Available Discovery Sources ===")
    print()
    print("1. Web search (general)")
    print("   - Community resource directories")
    print("   - Government program pages")
    print("   - Nonprofit listings")
    print()
    print("2. 211 directory")
    print("   - National 211 resource database")
    print("   - State-specific 211 sites")
    print()
    print("3. Government sources")
    print("   - State health department directories")
    print("   - County government resource pages")
    print("   - Federal program directories")
    print()
    print("4. Existing Beacon data (backed up)")
    print(f"   - Backup: /srv/docker/paperclip/backups/beacon-reset-20260920T212034Z/")
    print("   - Can be re-imported as leads for verification")
    return 0


COMMANDS = {
    "discover": cmd_discover,
    "--from-211": cmd_from_211,
    "--list-sources": cmd_list_sources,
}


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    if sys.argv[1] in COMMANDS:
        cmd = sys.argv[1]
        sys.exit(COMMANDS[cmd](sys.argv[2:]))
    else:
        # Default: treat first arg as location for discovery
        sys.exit(cmd_discover(sys.argv[1:]))


if __name__ == "__main__":
    main()
