#!/usr/bin/env python3
"""Single entry point for Beacon data pipeline.

Usage:
    python scripts/build.py              # Build everything
    python scripts/build.py --validate   # Build and validate
    python scripts/build.py --test       # Build, validate, and test
"""

import sys
import subprocess
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import REPO_ROOT, DATA_DIR


def run_cmd(cmd, description):
    """Run a command and report success/failure."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")
    result = subprocess.run(
        cmd, shell=True, cwd=REPO_ROOT,
        capture_output=False
    )
    if result.returncode != 0:
        print(f"\nFAILED: {description}")
        return False
    return True


def main():
    """Run the full build pipeline."""
    print("Beacon Data Pipeline")
    print(f"Repository: {REPO_ROOT}")
    print(f"Python: {sys.version}")

    steps = [
        ("python3 scripts/parse_resources.py", "Parsing source data → resources.json"),
        ("python3 scripts/generate_csv.py", "Generating CSV exports"),
        ("python3 scripts/build_pages.py", "Generating resource, county, and need pages"),
        ("python3 scripts/build_print.py", "Generating print-ready guides"),
        ("python3 scripts/validate.py", "Validating data against schema"),
    ]

    # Add test step if requested
    if "--test" in sys.argv or "-t" in sys.argv:
        steps.append(("python3 -m pytest tests/ -v", "Running tests"))

    failed = False
    for cmd, desc in steps:
        if not run_cmd(cmd, desc):
            failed = True
            if "--strict" in sys.argv:
                break

    print(f"\n{'='*60}")
    if failed:
        print("  BUILD COMPLETED WITH ERRORS")
        print(f"{'='*60}")
        sys.exit(1)
    else:
        print("  BUILD SUCCESSFUL")
        print(f"{'='*60}")

        # Summary
        resources_file = DATA_DIR / "resources.json"
        if resources_file.exists():
            import json
            with open(resources_file) as f:
                data = json.load(f)
            count = len(data.get("resources", []))
            counties = len(data.get("metadata", {}).get("regions", {}).get("KY", []))
            print(f"\n  Resources: {count}")
            print(f"  Counties: {counties}")
            print(f"  Output: {DATA_DIR}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
