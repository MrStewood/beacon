#!/usr/bin/env python3
"""Build public data from canonical YAML source files."""

import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml")
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent
SOURCE_DIR = REPO_ROOT / "source" / "approved"
DATA_DIR = REPO_ROOT / "data"


def load_yaml_resources():
    """Load all canonical YAML resources."""
    resources = []
    for yaml_file in SOURCE_DIR.rglob("*.yaml"):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        if data and "id" in data:
            resources.append(data)
    return resources


def validate_resource(r):
    """Basic validation of a canonical resource record."""
    errors = []
    required = ["id", "name", "status", "coverage_scope", "locations"]
    for field in required:
        if not r.get(field):
            errors.append(f"Missing required field: {field}")

    statuses = {"active", "needs-verification", "closed"}
    if r.get("status") and r["status"] not in statuses:
        errors.append(f"Invalid status: {r['status']}")

    if not r.get("phones") and r.get("coverage_scope") not in {"online"}:
        # Phone-less records are allowed, but later validation warns for local records.
        pass

    return errors


def _first_public_location(r):
    """Return the first public physical-ish location, falling back to any public location."""
    locations = r.get("locations", [])
    for loc in locations:
        if loc.get("publicly_displayed", True) and loc.get("location_type") in {"physical", "mailing", "mobile"}:
            return loc
    for loc in locations:
        if loc.get("publicly_displayed", True):
            return loc
    return {}


def _public_county(r, loc):
    """Derive legacy county label from v3 geography."""
    if loc.get("county_name"):
        return loc["county_name"]
    scope = r.get("coverage_scope")
    if scope == "national":
        return "National"
    if scope in {"state", "multi-county"}:
        return "Statewide"
    return "Unknown"


def _confidence(verification_status):
    if verification_status in {"verified"}:
        return "high"
    if verification_status in {"website-checked"}:
        return "medium"
    return "low"


def _map_url(loc):
    address = loc.get("address_line_1")
    if not address:
        return None
    parts = [
        address,
        loc.get("city"),
        loc.get("state"),
        loc.get("postal_code"),
    ]
    query = "+".join(str(p).replace(" ", "+") for p in parts if p)
    return f"https://www.google.com/maps/search/?api=1&query={query}"


def build_public_data(resources):
    """Convert canonical v3 resources to the public v3+compat dataset."""
    public_resources = []

    for r in resources:
        loc = _first_public_location(r)
        verification = r.get("verification", {})
        verification_status = verification.get("status", "needs-review")
        public = {
            "id": r["id"],
            "name": r.get("name", ""),
            "alternate_names": r.get("alternate_names", []),
            "description": r.get("description", ""),
            "status": r["status"],
            "phones": r.get("phones", []),
            "email": r.get("email"),
            "url": r.get("url"),
            "facebook": r.get("facebook"),
            "needs": r.get("needs", []),
            "service_types": r.get("service_types", []),
            "resource_type": r.get("resource_type", "unknown"),
            "populations": r.get("populations", ["anyone"]),
            "eligibility": r.get("eligibility"),
            "cost": r.get("cost", "unknown"),
            "hours": r.get("hours"),
            "languages": r.get("languages", ["English"]),
            "what_to_bring": r.get("what_to_bring"),
            "referral_required": r.get("referral_required"),
            "intake_hours": r.get("intake_hours"),
            "intake_process": r.get("intake_process"),
            "capacity": r.get("capacity"),
            "waitlist": r.get("waitlist"),
            "accepts_insurance": r.get("accepts_insurance"),
            "coverage_scope": r.get("coverage_scope", "unknown"),
            "service_areas": r.get("service_areas", []),
            "states_served": r.get("states_served", []),
            "remote_service": r.get("remote_service", False),
            "location_restrictions": r.get("location_restrictions"),
            "locations": r.get("locations", []),
            "verification_status": verification_status,
            "last_verified": verification.get("checked_at"),
            "verified_by": verification.get("checked_by"),
            "confidence": _confidence(verification_status),
            "source_urls": [s.get("url") for s in r.get("sources", []) if s.get("url")],
            "first_seen": r.get("first_seen"),
            "tags": r.get("tags", []),
            "notes": r.get("notes"),
            "related": r.get("related", []),
            # Compatibility fields for current site/widgets/API clients.
            "county": _public_county(r, loc),
            "address": loc.get("address_line_1"),
            "city": loc.get("city"),
            "state": loc.get("state") or (r.get("states_served") or [None])[0],
            "zip": loc.get("postal_code"),
            "map_url": _map_url(loc),
        }

        public_resources.append(public)

    return public_resources


def generate_outputs(resources):
    """Generate all public output files."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DATA_DIR / "v3", exist_ok=True)

    regions = {}
    for r in resources:
        state = r.get("state") or "US"
        county = r.get("county")
        if county and county not in {"National", "Statewide", "Unknown"}:
            regions.setdefault(state, set()).add(county)

    metadata = {
        "version": "3.0",
        "source": "Canonical YAML records",
        "last_updated": __import__("datetime").datetime.now().strftime("%Y-%m-%d"),
        "total_resources": len(resources),
        "regions": {state: sorted(counties) for state, counties in sorted(regions.items())},
        "needs": sorted({need for r in resources for need in r.get("needs", [])}),
        "service_types": sorted({svc for r in resources for svc in r.get("service_types", [])}),
        "populations": sorted({pop for r in resources for pop in r.get("populations", [])}),
    }

    output = {
        "metadata": metadata,
        "resources": resources,
    }
    for path in (DATA_DIR / "resources.json", DATA_DIR / "v3" / "resources.json"):
        with open(path, "w") as f:
            json.dump(output, f, indent=2)

    index = {
        "metadata": metadata,
        "resources": [{
            "id": r["id"],
            "name": r["name"],
            "county": r.get("county"),
            "city": r.get("city"),
            "needs": r.get("needs", []),
            "phones": r.get("phones", []),
            "address": r.get("address"),
            "status": r.get("status"),
            "confidence": r.get("confidence"),
            "coverage_scope": r.get("coverage_scope"),
        } for r in resources],
    }
    with open(DATA_DIR / "index.json", "w") as f:
        json.dump(index, f, indent=2)

    print(f"Generated {len(resources)} resources")


def main():
    print("=== Building from Canonical YAML ===\n")

    # Load resources
    resources = load_yaml_resources()
    print(f"Loaded {len(resources)} canonical YAML records")

    # Validate
    all_errors = []
    for r in resources:
        errors = validate_resource(r)
        if errors:
            for e in errors:
                all_errors.append(f"{r.get('id', '?')}: {e}")

    if all_errors:
        print("\nValidation errors:")
        for e in all_errors:
            print(f"  ERROR: {e}")
        return 1

    # Build public data
    public = build_public_data(resources)
    generate_outputs(public)

    print("\nBuild complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
