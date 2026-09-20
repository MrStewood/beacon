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
    """Basic validation of a resource record."""
    errors = []
    required = ["id", "name", "coverage_scope"]
    for field in required:
        if not r.get(field):
            errors.append(f"Missing required field: {field}")

    if not r.get("locations"):
        errors.append("No locations defined")

    if not r.get("phones") and r.get("coverage_scope") != "online":
        warnings = ["No phone numbers (may be valid for online-only)"]

    return errors


def build_public_data(resources):
    """Convert canonical resources to public dataset."""
    public_resources = []

    for r in resources:
        # Create public record from canonical YAML
        public = {
            "id": r["id"],
            "name": r.get("name", ""),
            "description": r.get("description", ""),
            "phones": r.get("phones", []),
            "url": r.get("url"),
            "needs": r.get("needs", []),
            "service_types": r.get("service_types", []),
            "populations": r.get("populations", ["anyone"]),
            "coverage_scope": r.get("coverage_scope", "unknown"),
            "locations": r.get("locations", []),
            "verification_status": r.get("verification", {}).get("status", "needs-review"),
            "confidence": "medium" if r.get("verification", {}).get("status") == "website-checked" else "low",
            "source_urls": [s.get("url") for s in r.get("sources", []) if s.get("url")],
            "first_seen": r.get("first_seen"),
        }

        # Add county from first physical location
        for loc in r.get("locations", []):
            if loc.get("county_name"):
                public["county"] = loc["county_name"]
                break
        else:
            public["county"] = "Statewide" if r.get("coverage_scope") == "state" else None

        public_resources.append(public)

    return public_resources


def generate_outputs(resources):
    """Generate all public output files."""
    os.makedirs(DATA_DIR, exist_ok=True)

    # Full JSON
    output = {
        "metadata": {
            "version": "3.0",
            "source": "Canonical YAML records",
            "last_updated": __import__("datetime").datetime.now().strftime("%Y-%m-%d"),
            "total_resources": len(resources),
            "needs": sorted({need for r in resources for need in r.get("needs", [])}),
        },
        "resources": resources
    }
    with open(DATA_DIR / "resources.json", "w") as f:
        json.dump(output, f, indent=2)

    # Compact index
    index = [{
        "id": r["id"],
        "name": r["name"],
        "county": r.get("county"),
        "needs": r.get("needs", []),
        "phones": r.get("phones", []),
        "coverage_scope": r.get("coverage_scope")
    } for r in resources]
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
