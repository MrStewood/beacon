#!/usr/bin/env python3
"""Migrate v2 resources to v3 geographic schema."""

import json
import os
import re
import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
SCHEMA_DIR = REPO_ROOT / "schema"

def load_ky_counties():
    """Load Kentucky FIPS codes."""
    with open(SCHEMA_DIR / "reference" / "ky_counties.json") as f:
        data = json.load(f)
    return {c["name"]: c["fips"] for c in data["counties"]}

def generate_stable_id(name, county=None):
    """Generate a stable ID from organization name."""
    slug = name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug[:80].strip('-')

def migrate_resource(r, ky_fips):
    """Migrate a single resource from v2 to v3."""
    # Build locations
    locations = []
    if r.get("address") and r["address"] != "Statewide":
        loc_id = generate_stable_id(r["name"]) + "-main"
        locations.append({
            "id": loc_id,
            "name": None,
            "location_type": "physical",
            "address_line_1": r.get("address"),
            "address_line_2": None,
            "city": r.get("city"),
            "county_name": r.get("county"),
            "county_fips": ky_fips.get(r.get("county", ""), None),
            "state": r.get("state", "KY"),
            "postal_code": r.get("zip"),
            "country": "US",
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "geocoding_status": "not-geocoded",
            "geocoding_source": None,
            "geocoded_at": None,
            "publicly_displayed": True
        })
    else:
        # No physical address - create virtual location
        locations.append({
            "id": generate_stable_id(r["name"]) + "-virtual",
            "name": None,
            "location_type": "virtual",
            "address_line_1": None,
            "address_line_2": None,
            "city": None,
            "county_name": None,
            "county_fips": None,
            "state": r.get("state", "KY"),
            "postal_code": None,
            "country": "US",
            "latitude": None,
            "longitude": None,
            "geocoding_status": "not-geocoded",
            "geocoding_source": None,
            "geocoded_at": None,
            "publicly_displayed": True
        })

    # Build coverage
    county = r.get("county", "")
    if county == "Statewide":
        coverage_scope = "state"
        service_areas = [{"type": "state", "state": "KY", "country": "US"}]
        states_served = ["KY"]
    elif county:
        coverage_scope = "county"
        fips = ky_fips.get(county)
        service_areas = [{
            "type": "county",
            "state": "KY",
            "country": "US",
            "values": [{"name": county, "fips": fips}]
        }]
        states_served = ["KY"]
    else:
        coverage_scope = "unknown"
        service_areas = []
        states_served = []

    # Determine resource type from service_types and description
    resource_type = "unknown"
    svc_types = r.get("service_types", [])
    if "hotline" in svc_types:
        resource_type = "hotline"
    elif "government" in svc_types:
        resource_type = "government"
    elif "residential" in svc_types or "outpatient" in svc_types:
        resource_type = "direct-provider"
    elif "faith-based" in svc_types:
        resource_type = "community-program"
    elif "peer-led" in svc_types:
        resource_type = "community-program"

    # Build v3 record
    v3 = {
        "id": r["id"],
        "legacy_ids": [],
        "name": r["name"],
        "alternate_names": r.get("alternate_names", []),
        "description": r.get("description", ""),
        "organization_id": None,
        "program_id": None,
        "locations": locations,
        "coverage_scope": coverage_scope,
        "service_areas": service_areas,
        "states_served": states_served,
        "remote_service": r.get("service_types", []) and "online" in r.get("service_types", []),
        "location_restrictions": None,
        "phones": r.get("phones", []),
        "email": r.get("email"),
        "url": r.get("url"),
        "facebook": r.get("facebook"),
        "needs": r.get("needs", []),
        "service_types": r.get("service_types", []),
        "resource_type": resource_type,
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
        "verification_status": "source-only",
        "last_verified": r.get("last_verified"),
        "verified_by": r.get("verified_by"),
        "website_last_checked": None,
        "confidence": r.get("confidence", "medium"),
        "source_urls": r.get("source_urls", []),
        "first_seen": r.get("first_seen"),
        "tags": r.get("tags", []),
        "notes": r.get("notes"),
        "related": r.get("related", []),
        # Deprecated v2 fields (kept for compatibility)
        "county": r.get("county"),
        "address": r.get("address"),
        "city": r.get("city"),
        "state": r.get("state"),
        "zip": r.get("zip")
    }
    return v3

def main():
    ky_fips = load_ky_counties()

    # Load v2 data
    with open(DATA_DIR / "resources.json") as f:
        v2_data = json.load(f)

    # Migrate
    v3_resources = []
    stats = {
        "total": 0,
        "migrated": 0,
        "missing_location": 0,
        "unknown_coverage": 0,
        "statewide": 0,
        "county": 0
    }

    for r in v2_data["resources"]:
        stats["total"] += 1
        v3 = migrate_resource(r, ky_fips)
        v3_resources.append(v3)
        stats["migrated"] += 1

        if not v3["locations"] or v3["locations"][0]["location_type"] == "virtual":
            stats["missing_location"] += 1
        if v3["coverage_scope"] == "unknown":
            stats["unknown_coverage"] += 1
        if v3["coverage_scope"] == "state":
            stats["statewide"] += 1
        elif v3["coverage_scope"] == "county":
            stats["county"] += 1

    # Build v3 output
    v3_output = {
        "schema_version": "3.0",
        "metadata": {
            "source": v2_data["metadata"]["source"],
            "source_url": v2_data["metadata"]["source_url"],
            "last_updated": v2_data["metadata"]["last_updated"],
            "total_resources": len(v3_resources),
            "migration_date": "2026-09-20",
            "states": ["KY"]
        },
        "resources": v3_resources
    }

    # Save v3 data
    os.makedirs(DATA_DIR / "v3", exist_ok=True)
    with open(DATA_DIR / "v3" / "resources.json", "w") as f:
        json.dump(v3_output, f, indent=2)

    # Print migration report
    print("=== Migration Report ===")
    print(f"Total resources: {stats['total']}")
    print(f"Successfully migrated: {stats['migrated']}")
    print(f"Missing physical location: {stats['missing_location']}")
    print(f"Unknown coverage: {stats['unknown_coverage']}")
    print(f"Statewide coverage: {stats['statewide']}")
    print(f"County coverage: {stats['county']}")
    print(f"\nV3 data saved to: {DATA_DIR / 'v3' / 'resources.json'}")

if __name__ == "__main__":
    main()
