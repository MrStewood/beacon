#!/usr/bin/env python3
"""Single entry point for Beacon data pipeline.

Usage:
    python scripts/build.py              # Build everything
    python scripts/build.py --validate   # Build and validate
    python scripts/build.py --test       # Build, validate, and test

Outputs:
    data/         — generated JSON/CSV (gitignored; included in _site/)
    pages/        — resource/county/need HTML pages (gitignored; included in _site/)
    print/        — print-ready HTML guides (gitignored; included in _site/)
    _site/        — complete public website ready for GitHub Pages deployment
                    (gitignored; assembled from the above + static assets)
"""

import shutil
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import REPO_ROOT, DATA_DIR

# Public static files copied verbatim into _site/
_SITE_STATIC_FILES = [
    "index.html",
    "organizations.html",
    "robots.txt",
    "sitemap.xml",
    ".nojekyll",
]

# Public directories copied verbatim into _site/
_SITE_STATIC_DIRS = [
    "assets",
    "embed",
    "schema",
]

# Generated directories assembled into _site/ (built by prior steps).
# data/ is handled separately below to exclude data/census/.
_SITE_GENERATED_DIRS = [
    "pages",
    "print",
]

# Generated files/subdirs inside data/ that belong in the public site.
# data/census/ is excluded: it is operational AI reference data
# (35 MB of JSON + Python scripts), not part of the public web interface.
_SITE_DATA_ENTRIES = [
    "resources.json",
    "resources.csv",
    "index.json",
    "catalog.json",
    "csv-by-county",
    "resources-by-county",
    "resources-by-need",
    "v3",
]


def run_cmd(cmd, description):
    """Run a command and report success/failure."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True, cwd=REPO_ROOT, capture_output=False)
    if result.returncode != 0:
        print(f"\nFAILED: {description}")
        return False
    return True


def assemble_site():
    """Copy public content into _site/ for GitHub Pages deployment.

    Only public-facing content lands here. Operational directories
    (leads/, pilot/, source/candidates/, scripts/, tests/) are never included.
    """
    site = REPO_ROOT / "_site"
    if site.exists():
        shutil.rmtree(site)
    site.mkdir()

    # Static files
    for name in _SITE_STATIC_FILES:
        src = REPO_ROOT / name
        if src.exists():
            shutil.copy2(src, site / name)

    # Static directories
    for dname in _SITE_STATIC_DIRS:
        src = REPO_ROOT / dname
        if src.exists():
            shutil.copytree(src, site / dname)

    # Generated directories (pages/, print/)
    for dname in _SITE_GENERATED_DIRS:
        src = REPO_ROOT / dname
        if src.exists():
            shutil.copytree(src, site / dname)

    # data/ — copy only public entries; exclude data/census/ (operational, 35 MB)
    src_data = REPO_ROOT / "data"
    if src_data.exists():
        (site / "data").mkdir(exist_ok=True)
        for entry in _SITE_DATA_ENTRIES:
            src = src_data / entry
            if src.is_dir():
                shutil.copytree(src, site / "data" / entry)
            elif src.is_file():
                shutil.copy2(src, site / "data" / entry)
    print(f"\n  _site/ assembled ({sum(1 for _ in site.rglob('*') if _.is_file())} files)")


def main():
    """Run the full build pipeline."""
    print("Beacon Data Pipeline")
    print(f"Repository: {REPO_ROOT}")
    print(f"Python: {sys.version}")

    steps = [
        ("python3 scripts/build_from_yaml.py", "Building public data from canonical YAML"),
        ("python3 scripts/generate_csv.py", "Generating CSV exports"),
        ("python3 scripts/build_pages.py", "Generating resource, county, and need pages"),
        ("python3 scripts/build_print.py", "Generating print-ready guides"),
        ("python3 scripts/validate.py", "Validating data against schema"),
        ("python3 scripts/validate_sources.py", "Validating sources and workflow"),
        ("python3 scripts/generate_report.py", "Generating change report"),
    ]

    if "--test" in sys.argv or "-t" in sys.argv:
        steps.append(("python3 -m pytest tests/ -v", "Running tests"))

    failed = False
    for cmd, desc in steps:
        if not run_cmd(cmd, desc):
            failed = True
            if "--strict" in sys.argv:
                break

    # Always assemble _site/ so CI has something to deploy, even on partial failure.
    # A failed validate step will have already set exit code; _site/ contents will
    # be incomplete but the deploy step won't run because CI fails before it.
    print(f"\n{'='*60}")
    print(f"  Assembling _site/ for GitHub Pages")
    print(f"{'='*60}")
    assemble_site()

    print(f"\n{'='*60}")
    if failed:
        print("  BUILD COMPLETED WITH ERRORS")
        print(f"{'='*60}")
        sys.exit(1)
    else:
        print("  BUILD SUCCESSFUL")
        print(f"{'='*60}")

        resources_file = DATA_DIR / "resources.json"
        if resources_file.exists():
            import json
            with open(resources_file) as f:
                data = json.load(f)
            count = len(data.get("resources", []))
            regions = data.get("metadata", {}).get("regions", {})
            counties = sum(len(v) for v in regions.values())
            print(f"\n  Resources: {count}")
            print(f"  Counties:  {counties}")
            print(f"  Output:    _site/")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
