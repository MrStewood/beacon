#!/usr/bin/env python3
"""Generate changed-record report for PRs."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def generate_report(base_ref="origin/main"):
    """Compare current state with base and generate report."""
    import subprocess

    # Get changed files
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    changed_files = [f for f in result.stdout.strip().split('\n') if f]

    report = {
        "generated_at": __import__('datetime').datetime.now().isoformat(),
        "base_ref": base_ref,
        "changed_files": changed_files,
        "added": [],
        "updated": [],
        "removed": [],
        "verification_changes": [],
        "geographic_changes": [],
        "sensitive_changes": []
    }

    # Analyze changes
    for f in changed_files:
        if f.startswith("source/approved/"):
            # Resource file changed
            resource_id = Path(f).stem
            if f.endswith(".yaml"):
                # Check if file existed before
                result = subprocess.run(
                    ["git", "show", f"{base_ref}:{f}"],
                    capture_output=True, text=True, cwd=REPO_ROOT
                )
                if result.returncode != 0:
                    report["added"].append({"id": resource_id, "file": f})
                else:
                    report["updated"].append({"id": resource_id, "file": f})

    # Generate summary
    summary = {
        "total_changes": len(changed_files),
        "resources_added": len(report["added"]),
        "resources_updated": len(report["updated"]),
        "resources_removed": len(report["removed"]),
        "verification_changes": len(report["verification_changes"]),
        "geographic_changes": len(report["geographic_changes"]),
        "sensitive_changes": len(report["sensitive_changes"])
    }
    report["summary"] = summary

    # Save report
    report_path = REPO_ROOT / "data" / "change-report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print("=== Changed Record Report ===")
    print(f"Files changed: {len(changed_files)}")
    print(f"Resources added: {summary['resources_added']}")
    print(f"Resources updated: {summary['resources_updated']}")
    print(f"Resources removed: {summary['resources_removed']}")

    return report


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    generate_report(base)
