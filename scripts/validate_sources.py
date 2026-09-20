#!/usr/bin/env python3
"""Validate source evidence and workflow rules."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

ALLOWED_SOURCE_TYPES = {
    'official-provider', 'government', 'official-social',
    'licensing-directory', '211-directory', 'nonprofit-directory',
    'map-listing', 'news', 'other'
}

SENSITIVE_NEEDS = {'crisis', 'domestic-violence'}


def validate_workflow(resources):
    """Check separation of duties."""
    errors = []
    warnings = []

    for r in resources:
        rid = r.get('id', 'unknown')
        workflow = r.get('workflow', {})

        # Check separation: discoverer != verifier
        discovered_by = workflow.get('discovered_by')
        verified_by = workflow.get('verified_by')
        if discovered_by and verified_by and discovered_by == verified_by:
            errors.append(f"{rid}: discovered_by == verified_by (separation violated)")

        # Check publication requires verification
        if r.get('status') == 'active' and not verified_by:
            warnings.append(f"{rid}: active but not verified")

    return errors, warnings


def validate_sources(resources):
    """Check evidence quality."""
    errors = []
    warnings = []

    for r in resources:
        rid = r.get('id', 'unknown')
        sources = r.get('sources', [])

        # Check that sources exist
        if not sources:
            warnings.append(f"{rid}: no sources documented")

        for s in sources:
            source_type = s.get('source_type')
            if source_type not in ALLOWED_SOURCE_TYPES:
                errors.append(f"{rid}: invalid source_type '{source_type}'")

            # Check that high-risk records have official sources
            needs = r.get('needs', [])
            if any(n in SENSITIVE_NEEDS for n in needs):
                if source_type not in ('official-provider', 'government'):
                    warnings.append(f"{rid}: sensitive resource without official source")

    return errors, warnings


def validate_sensitive(resources):
    """Check sensitive resource handling."""
    errors = []
    warnings = []

    for r in resources:
        rid = r.get('id', 'unknown')
        needs = r.get('needs', [])

        # Check confidential locations
        for loc in r.get('locations', []):
            if loc.get('location_type') == 'confidential':
                if loc.get('publicly_displayed', True):
                    errors.append(f"{rid}: confidential location is publicly displayed")
                if loc.get('latitude') or loc.get('longitude'):
                    errors.append(f"{rid}: confidential location has coordinates")

        # Check crisis resources have phones
        if 'crisis' in needs:
            if not r.get('phones'):
                errors.append(f"{rid}: crisis resource without phone")

    return errors, warnings


def main():
    # Load v3 data
    data_path = REPO_ROOT / "data" / "v3" / "resources.json"
    if not data_path.exists():
        print("V3 data not found, skipping source validation")
        return 0

    with open(data_path) as f:
        data = json.load(f)

    resources = data.get('resources', [])

    print("=== Source & Workflow Validation ===\n")

    # Run validations
    all_errors = []
    all_warnings = []

    for validator in [validate_workflow, validate_sources, validate_sensitive]:
        errors, warnings = validator(resources)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    # Report
    print(f"Resources checked: {len(resources)}")
    print(f"Errors: {len(all_errors)}")
    print(f"Warnings: {len(all_warnings)}")

    if all_errors:
        print("\n--- ERRORS ---")
        for e in all_errors:
            print(f"  ERROR: {e}")

    if all_warnings:
        print("\n--- WARNINGS ---")
        for w in all_warnings[:10]:
            print(f"  WARN: {w}")
        if len(all_warnings) > 10:
            print(f"  ... and {len(all_warnings) - 10} more warnings")

    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
