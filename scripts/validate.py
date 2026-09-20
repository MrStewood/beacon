#!/usr/bin/env python3
"""Validate Beacon resource data against schema and business rules."""

import json
import os
import sys
import re
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("ERROR: jsonschema not installed. Run: pip install jsonschema")
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "resource.schema.json"
DATA_PATH = REPO_ROOT / "data" / "resources.json"

# Known crisis short codes
KNOWN_CRISIS_PHONES = {'988', '211', '741741'}

# Required resources that must exist and be correct
CRITICAL_RESOURCES = [
    {'name_contains': '988', 'required_phones': ['988'], 'required_needs': ['crisis']},
    {'name_contains': '211', 'required_phones': [], 'required_needs': ['community']},
]


def load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def load_data():
    with open(DATA_PATH) as f:
        return json.load(f)


def validate_schema(resources, schema):
    """Validate all resources against JSON Schema."""
    errors = []
    validator = jsonschema.Draft202012Validator(schema)
    for i, resource in enumerate(resources):
        for error in validator.iter_errors(resource):
            errors.append({
                'resource_id': resource.get('id', f'index-{i}'),
                'field': '.'.join(str(p) for p in error.absolute_path) or '(root)',
                'message': error.message,
                'severity': 'error'
            })
    return errors


def validate_business_rules(resources):
    """Apply business rules beyond schema validation."""
    warnings = []
    errors = []

    ids = [r.get('id') for r in resources]
    phones_seen = {}

    for r in resources:
        rid = r.get('id', 'unknown')

        # Rule: ID must be unique
        if ids.count(r.get('id')) > 1:
            errors.append({'resource_id': rid, 'field': 'id', 'message': f'Duplicate ID: {r["id"]}', 'severity': 'error'})

        # Rule: Name must not be empty
        if not r.get('name', '').strip():
            errors.append({'resource_id': rid, 'field': 'name', 'message': 'Empty name', 'severity': 'error'})

        # Rule: At least one phone for non-statewide resources
        if r.get('county') != 'Statewide' and not r.get('phones'):
            warnings.append({'resource_id': rid, 'field': 'phones', 'message': 'No phone number for local resource', 'severity': 'warning'})

        # Rule: Crisis resources must have phone numbers
        if 'crisis' in r.get('needs', []) and not r.get('phones'):
            errors.append({'resource_id': rid, 'field': 'phones', 'message': 'Crisis resource has no phone number', 'severity': 'error'})

        # Rule: URL must start with http:// or https://
        url = r.get('url', '')
        if url and not url.startswith(('http://', 'https://')):
            errors.append({'resource_id': rid, 'field': 'url', 'message': f'Malformed URL: {url}', 'severity': 'error'})

        # Rule: Detect duplicate phone numbers
        for phone in r.get('phones', []):
            if phone in phones_seen:
                warnings.append({
                    'resource_id': rid,
                    'field': 'phones',
                    'message': f'Duplicate phone {phone} also in {phones_seen[phone]}',
                    'severity': 'warning'
                })
            phones_seen[phone] = rid

        # Rule: Status should not be 'active' if never verified
        if r.get('status') == 'active' and r.get('verification_status') == 'unverified':
            warnings.append({'resource_id': rid, 'field': 'status', 'message': 'Status is active but verification is unverified', 'severity': 'warning'})

        # Rule: Suspicious category assignments
        needs = r.get('needs', [])
        svc = r.get('service_types', [])
        if 'hotline' in svc and 'documents' in needs:
            warnings.append({'resource_id': rid, 'field': 'needs', 'message': 'Hotline classified as documents need - likely incorrect', 'severity': 'warning'})

    return errors, warnings


def validate_critical_resources(resources):
    """Check that critical crisis resources are correct."""
    errors = []
    for crit in CRITICAL_RESOURCES:
        name_contains = crit['name_contains']
        matches = [r for r in resources if name_contains in r.get('name', '')]
        if not matches:
            errors.append({'resource_id': f'critical-{name_contains}', 'field': 'name', 'message': f'Critical resource containing "{name_contains}" not found', 'severity': 'error'})
            continue
        r = matches[0]
        # Check phones
        for phone in crit.get('required_phones', []):
            if phone not in r.get('phones', []):
                errors.append({'resource_id': r['id'], 'field': 'phones', 'message': f'Critical resource missing required phone: {phone}', 'severity': 'error'})
        # Check needs
        for need in crit.get('required_needs', []):
            if need not in r.get('needs', []):
                errors.append({'resource_id': r['id'], 'field': 'needs', 'message': f'Critical resource missing required need: {need}', 'severity': 'error'})
    return errors


def main():
    print("=== Beacon Data Validation ===\n")

    schema = load_schema()
    data = load_data()
    resources = data.get('resources', [])

    print(f"Loaded {len(resources)} resources\n")

    # Schema validation
    print("1. Schema validation...")
    schema_errors = validate_schema(resources, schema)
    print(f"   {len(schema_errors)} schema errors")

    # Business rules
    print("2. Business rules...")
    rule_errors, rule_warnings = validate_business_rules(resources)
    print(f"   {len(rule_errors)} errors, {len(rule_warnings)} warnings")

    # Critical resources
    print("3. Critical resource checks...")
    critical_errors = validate_critical_resources(resources)
    print(f"   {len(critical_errors)} errors")

    # Summary
    all_errors = schema_errors + rule_errors + critical_errors
    print(f"\n=== Summary ===")
    print(f"Total errors: {len(all_errors)}")
    print(f"Total warnings: {len(rule_warnings)}")

    if all_errors:
        print("\n--- ERRORS ---")
        for e in all_errors:
            print(f"  [{e['severity'].upper()}] {e['resource_id']}.{e['field']}: {e['message']}")

    if rule_warnings:
        print("\n--- WARNINGS ---")
        for w in rule_warnings[:20]:  # Limit output
            print(f"  [WARN] {w['resource_id']}.{w['field']}: {w['message']}")
        if len(rule_warnings) > 20:
            print(f"  ... and {len(rule_warnings) - 20} more warnings")

    # Exit code
    if all_errors:
        print("\nVALIDATION FAILED")
        sys.exit(1)
    else:
        print("\nVALIDATION PASSED")
        sys.exit(0)


if __name__ == '__main__':
    main()
