#!/usr/bin/env python3
"""Enhance v3 Kentucky data with verified FIPS codes and quality checks."""

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
SCHEMA_DIR = REPO_ROOT / "schema"

def load_ky_fips():
    with open(SCHEMA_DIR / "reference" / "ky_counties.json") as f:
        data = json.load(f)
    return {c["name"]: c["fips"] for c in data["counties"]}

def enhance_resource(r, ky_fips):
    """Enhance a single resource with verified data."""
    changes = []

    # Ensure all locations have correct FIPS
    for loc in r.get("locations", []):
        if loc.get("county_name") and loc["county_name"] in ky_fips:
            if not loc.get("county_fips"):
                loc["county_fips"] = ky_fips[loc["county_name"]]
                changes.append("added_fips")
            elif loc["county_fips"] != ky_fips[loc["county_name"]]:
                loc["county_fips"] = ky_fips[loc["county_name"]]
                changes.append("fixed_fips")

    # Ensure service_areas have FIPS for county type
    for area in r.get("service_areas", []):
        if area["type"] == "county":
            for v in area.get("values", []):
                if v.get("name") in ky_fips:
                    if not v.get("fips"):
                        v["fips"] = ky_fips[v["name"]]
                        changes.append("added_area_fips")

    # Ensure states_served includes KY for Kentucky resources
    if r.get("county") and r["county"] != "Statewide":
        if "KY" not in r.get("states_served", []):
            r["states_served"] = ["KY"]
            changes.append("added_ky_state")
    elif r.get("county") == "Statewide":
        if "KY" not in r.get("states_served", []):
            r["states_served"] = ["KY"]
            changes.append("added_ky_state")

    # Set coverage_scope based on county if not already set
    if not r.get("coverage_scope") or r["coverage_scope"] == "unknown":
        county = r.get("county", "")
        if county == "Statewide":
            r["coverage_scope"] = "state"
            changes.append("set_state_scope")
        elif county:
            r["coverage_scope"] = "county"
            r["service_areas"] = [{
                "type": "county",
                "state": "KY",
                "country": "US",
                "values": [{"name": county, "fips": ky_fips.get(county)}]
            }]
            changes.append("set_county_scope")

    return changes

def generate_report(v3_data):
    """Generate migration quality report."""
    resources = v3_data["resources"]
    report = {
        "total": len(resources),
        "by_coverage": {},
        "by_location_type": {},
        "missing_fips": [],
        "missing_address": [],
        "missing_description": [],
        "missing_phones": [],
        "statewide_count": 0,
        "county_count": 0,
        "multi_county": 0,
        "has_coordinates": 0,
    }

    for r in resources:
        # Coverage
        scope = r.get("coverage_scope", "unknown")
        report["by_coverage"][scope] = report["by_coverage"].get(scope, 0) + 1

        # Location types
        for loc in r.get("locations", []):
            lt = loc.get("location_type", "unknown")
            report["by_location_type"][lt] = report["by_location_type"].get(lt, 0) + 1

        # Missing data
        if not r.get("description"):
            report["missing_description"].append(r["id"])
        if not r.get("phones"):
            report["missing_phones"].append(r["id"])

        # Physical location checks
        has_address = False
        for loc in r.get("locations", []):
            if loc.get("address_line_1"):
                has_address = True
            if loc.get("latitude") and loc.get("longitude"):
                report["has_coordinates"] += 1
            if loc.get("county_name") and not loc.get("county_fips"):
                report["missing_fips"].append(f"{r['id']}.{loc['id']}")

        if not has_address:
            report["missing_address"].append(r["id"])

    return report

def main():
    ky_fips = load_ky_fips()

    with open(DATA_DIR / "v3" / "resources.json") as f:
        v3_data = json.load(f)

    # Enhance all resources
    total_changes = 0
    for r in v3_data["resources"]:
        changes = enhance_resource(r, ky_fips)
        total_changes += len(changes)

    # Save enhanced data
    with open(DATA_DIR / "v3" / "resources.json", "w") as f:
        json.dump(v3_data, f, indent=2)

    # Generate report
    report = generate_report(v3_data)

    # Save report
    with open(DATA_DIR / "v3" / "migration_report.json", "w") as f:
        json.dump(report, f, indent=2)

    # Print summary
    print("=== Kentucky Data Enhancement ===")
    print(f"Enhancements applied: {total_changes}")
    print(f"\n=== Quality Report ===")
    print(f"Total resources: {report['total']}")
    print(f"Coverage breakdown:")
    for scope, count in sorted(report['by_coverage'].items()):
        print(f"  {scope}: {count}")
    print(f"\nLocation types:")
    for lt, count in sorted(report['by_location_type'].items()):
        print(f"  {lt}: {count}")
    print(f"\nMissing data:")
    print(f"  Description: {len(report['missing_description'])}")
    print(f"  Phone: {len(report['missing_phones'])}")
    print(f"  Address: {len(report['missing_address'])}")
    print(f"  FIPS codes: {len(report['missing_fips'])}")
    print(f"\nWith coordinates: {report['has_coordinates']}")

if __name__ == "__main__":
    main()
