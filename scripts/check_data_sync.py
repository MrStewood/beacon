#!/usr/bin/env python3
"""Verify committed data/resources.json is in sync with source/approved/.

Checks semantic equivalence — every approved YAML has a matching entry in
resources.json by ID, and the counts match. Does NOT require byte-for-byte
identity, which is fragile across platforms and Python versions.

Exit 0: in sync.
Exit 1: out of sync — print what's missing or extra.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# --- Collect approved resource IDs from source/approved/**/*.yaml ---
try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed", file=sys.stderr)
    sys.exit(1)

approved_ids = set()
approved_dir = REPO / "source" / "approved"
for p in sorted(approved_dir.rglob("*.yaml")):
    try:
        doc = yaml.safe_load(p.read_text()) or {}
        rid = doc.get("id") or doc.get("resource", {}).get("id")
        if rid:
            approved_ids.add(rid)
        else:
            print(f"WARN: {p.relative_to(REPO)} has no id field", file=sys.stderr)
    except Exception as e:
        print(f"ERROR reading {p}: {e}", file=sys.stderr)
        sys.exit(1)

# --- Collect resource IDs from committed data/resources.json ---
resources_file = REPO / "data" / "resources.json"
if not resources_file.exists():
    print("FAIL: data/resources.json does not exist — run scripts/build_from_yaml.py and commit", file=sys.stderr)
    sys.exit(1)

try:
    data = json.loads(resources_file.read_text())
    published_ids = {r["id"] for r in data.get("resources", [])}
except Exception as e:
    print(f"FAIL: could not parse data/resources.json: {e}", file=sys.stderr)
    sys.exit(1)

# --- Compare ---
missing  = approved_ids - published_ids   # approved but not in JSON
extra    = published_ids - approved_ids   # in JSON but not approved

ok = True
if missing:
    print(f"FAIL: {len(missing)} approved resource(s) missing from data/resources.json:")
    for rid in sorted(missing):
        print(f"  - {rid}")
    print("Run 'python scripts/build_from_yaml.py' and commit data/resources.json")
    ok = False

if extra:
    print(f"FAIL: {len(extra)} resource(s) in data/resources.json have no approved YAML:")
    for rid in sorted(extra):
        print(f"  - {rid}")
    ok = False

# --- Also check index.json and v3/resources.json contain the same IDs ---
for label, path in [
    ("data/index.json",        REPO / "data" / "index.json"),
    ("data/v3/resources.json", REPO / "data" / "v3" / "resources.json"),
]:
    if not path.exists():
        print(f"FAIL: {label} does not exist — run scripts/build_from_yaml.py and commit")
        ok = False
        continue
    try:
        d = json.loads(path.read_text())
        ids = {r["id"] for r in d.get("resources", [])}
    except Exception as e:
        print(f"FAIL: could not parse {label}: {e}")
        ok = False
        continue
    missing2 = approved_ids - ids
    extra2   = ids - approved_ids
    if missing2 or extra2:
        print(f"FAIL: {label} out of sync with source/approved/")
        for rid in sorted(missing2): print(f"  missing: {rid}")
        for rid in sorted(extra2):   print(f"  extra:   {rid}")
        print(f"Run 'python scripts/build_from_yaml.py' and commit {label}")
        ok = False
    else:
        print(f"OK: {label} in sync — {len(approved_ids)} resource(s)")

if ok and not missing and not extra:
    print(f"OK: data/resources.json in sync — {len(approved_ids)} resource(s) match source/approved/")

sys.exit(0 if ok else 1)
