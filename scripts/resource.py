#!/usr/bin/env python3
"""Beacon Resource CLI - safe commands for agents and humans."""

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SOURCE_DIR = REPO_ROOT / "source" / "approved"


def cmd_create(args):
    """Create a new resource from YAML candidate."""
    print(f"Creating resource in {args.state}/{args.county or 'statewide'}...")
    # Implementation would parse YAML and create source file
    print("Use: python scripts/resource.py validate <resource-id>")


def cmd_validate(args):
    """Validate a resource against schema and rules."""
    resource_id = args.resource_id
    # Find the resource file
    for yaml_file in REPO_ROOT.rglob("*.yaml"):
        if resource_id in yaml_file.name:
            print(f"Found: {yaml_file}")
            # Run validation
            result = os.system(f"python scripts/validate.py {yaml_file}")
            return result
    print(f"Resource not found: {resource_id}")
    return 1


def cmd_evidence(args):
    """Show evidence for a resource."""
    resource_id = args.resource_id
    for yaml_file in REPO_ROOT.rglob("*.yaml"):
        if resource_id in yaml_file.name:
            print(f"Evidence for: {yaml_file.name}")
            # Parse and display sources
            import yaml
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            if 'sources' in data:
                for s in data['sources']:
                    print(f"  - {s.get('source_type')}: {s.get('url')}")
                    print(f"    Supports: {', '.join(s.get('supports', []))}")
            return 0
    print(f"Resource not found: {resource_id}")
    return 1


def cmd_diff(args):
    """Show changes between current and target branch."""
    target = args.target or "origin/main"
    os.system(f"git diff {target} --stat")
    os.system(f"git diff {target} -- source/")
    return 0


def cmd_build(args):
    """Run the complete build pipeline."""
    os.system("python scripts/build.py")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Beacon Resource CLI")
    subparsers = parser.add_subparsers(dest="command")

    # create
    create = subparsers.add_parser("create", help="Create new resource")
    create.add_argument("--state", required=True)
    create.add_argument("--county")
    create.add_argument("--candidate", required=True)

    # validate
    validate = subparsers.add_parser("validate", help="Validate resource")
    validate.add_argument("resource_id")

    # evidence
    evidence = subparsers.add_parser("evidence", help="Show resource evidence")
    evidence.add_argument("resource_id")

    # diff
    diff = subparsers.add_parser("diff", help="Show changes")
    diff.add_argument("--target", default="origin/main")

    # build
    subparsers.add_parser("build", help="Run full build")

    args = parser.parse_args()

    if args.command == "create":
        return cmd_create(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "evidence":
        return cmd_evidence(args)
    elif args.command == "diff":
        return cmd_diff(args)
    elif args.command == "build":
        return cmd_build(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
