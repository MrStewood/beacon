#!/usr/bin/env python3
"""Pre-run all 17 Beacon category searches for a given ZIP code.

Outputs a single JSON file with all raw SearXNG results, deduped against
the seen-URL registry. Feed the output to a model for structured extraction.

Usage:
    python3 scripts/presearch.py <ZIP> [--out <file>]
    python3 scripts/presearch.py 40744
    python3 scripts/presearch.py 40744 --out /tmp/results.json

Requires SearXNG accessible at SEARXNG_URL (default: http://localhost:8888).
"""

import json
import subprocess
import sys
import urllib.parse
import datetime
import os
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SEEN_REGISTRY = REPO_ROOT / "leads" / "seen_urls.json"
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")

CATEGORIES = [
    ("food",               ["food bank {county} County {state}", "food pantry {zip} {state}", "soup kitchen {city} {state}", "SNAP WIC office {county} County {state}"]),
    ("shelter",            ["homeless shelter {county} County {state}", "emergency shelter {city} {state} {zip}", "warming center {county} {state}"]),
    ("housing",            ["transitional housing {county} County {state}", "rent assistance {city} {state}", "housing authority {county} County", "Section 8 {county} {state}"]),
    ("health",             ["community health center {county} County {state}", "free clinic {city} {state}", "Medicaid office {county} {state}", "health department {county} County"]),
    ("mental-health",      ["mental health center {county} County {state}", "counseling services {city} {state}", "psychiatric services {county} {state}"]),
    ("addiction",          ["addiction treatment {county} County {state}", "detox rehab {city} {state}", "MAT program {county} {state}", "substance abuse {county} County"]),
    ("crisis",             ["crisis hotline {county} County {state}", "domestic violence shelter {county} {state}", "emergency crisis services {city} {state}"]),
    ("family",             ["childcare assistance {county} County {state}", "youth services {city} {state}", "family services {county} {state}", "foster care {county}"]),
    ("legal",              ["legal aid {county} County {state}", "free attorney {city} {state}", "victim advocacy {county} {state}"]),
    ("documents",          ["ID assistance {county} County {state}", "Social Security office {city} {state}", "birth certificate help {county} {state}"]),
    ("education",          ["GED adult education {county} County {state}", "literacy program {city} {state}", "trade school {county} {state}"]),
    ("jobs",               ["job training employment {county} County {state}", "workforce development {city} {state}", "resume help {county} {state}"]),
    ("transportation",     ["transportation assistance {county} County {state}", "bus ride program {city} {state}", "NEMT {county} {state}"]),
    ("utility-assistance", ["utility bill help {county} County {state}", "LIHEAP {county} {state}", "electric assistance {city} {state}"]),
    ("clothing",           ["clothing bank {county} County {state}", "free clothes {city} {state}", "hygiene supplies {county} {state}"]),
    ("community",          ["community support {county} County {state}", "church outreach {city} {state}", "peer support {county} {state}"]),
    ("veterans",           ["veteran services {county} County {state}", "VSO {city} {state}", "VA office {county} {state}"]),
]

UMBRELLA = [
    ("umbrella", [
        "{county} County {state} community resources social services",
        "211 resources {county} County {state}",
        "United Way {county} County {state}",
        "community action agency {county} County {state}",
    ]),
]


def search(query, max_results=15):
    q = urllib.parse.quote(query)
    cmd = f'curl -s --max-time 10 "{SEARXNG_URL}/search?q={q}&format=json"'
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL)
        data = json.loads(out)
        return [
            {
                "title": r.get("title", ""),
                "url":   r.get("url", ""),
                "snippet": r.get("content", "")[:300],
            }
            for r in data.get("results", [])[:max_results]
        ]
    except Exception as e:
        return [{"error": str(e)}]


def main():
    parser = argparse.ArgumentParser(description="Pre-search Beacon categories for a ZIP code")
    parser.add_argument("zip", help="ZIP code to research")
    parser.add_argument("--county", help="County name (auto-resolved from ZIP if omitted)")
    parser.add_argument("--city",   help="City name (auto-resolved from ZIP if omitted)")
    parser.add_argument("--state",  default="KY", help="State abbreviation (default: KY)")
    parser.add_argument("--out",    help="Output file path (default: /tmp/beacon_presearch_<zip>.json)")
    args = parser.parse_args()

    zip_code = args.zip
    state    = args.state

    # Resolve county/city from census data if not provided
    county = args.county
    city   = args.city
    if not county or not city:
        zips_file = REPO_ROOT / "data" / "census" / "us-zips.json"
        if zips_file.exists():
            zips = json.loads(zips_file.read_text())
            entry = zips.get(zip_code, {})
            county = county or entry.get("county", zip_code)
            city   = city   or entry.get("city", zip_code)
        else:
            county = county or zip_code
            city   = city   or zip_code

    out_path = args.out or f"/tmp/beacon_presearch_{zip_code}.json"

    # Load seen URLs to skip already-evaluated ones
    try:
        evaluated_urls = set(json.loads(SEEN_REGISTRY.read_text()).keys()) if SEEN_REGISTRY.exists() else set()
        print(f"Skipping {len(evaluated_urls)} already-evaluated URLs", file=sys.stderr)
    except Exception as e:
        evaluated_urls = set()
        print(f"Warning: could not load seen_urls registry: {e}", file=sys.stderr)

    seen_urls   = set()
    all_results = {}
    fmt = dict(zip=zip_code, county=county, city=city, state=state)

    groups = UMBRELLA + CATEGORIES
    print(f"Searching {len(groups)} category groups for ZIP {zip_code} ({county} County, {state})...", file=sys.stderr)

    for cat, queries in groups:
        cat_results = []
        for q_template in queries:
            q = q_template.format(**fmt)
            print(f"  [{cat}] {q}", file=sys.stderr)
            for r in search(q):
                url = r.get("url", "")
                if url and url not in seen_urls and url not in evaluated_urls:
                    seen_urls.add(url)
                    r["category_hint"] = cat
                    r["query"] = q
                    cat_results.append(r)
        all_results[cat] = cat_results

    output = {
        "zip":        zip_code,
        "county":     county,
        "city":       city,
        "state":      state,
        "searched_at": datetime.datetime.utcnow().isoformat() + "Z",
        "total_unique_urls": len(seen_urls),
        "results_by_category": all_results,
    }

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDone. {len(seen_urls)} unique URLs across {len(all_results)} categories.", file=sys.stderr)
    print(f"Saved to {out_path}", file=sys.stderr)
    print(out_path)


if __name__ == "__main__":
    main()
