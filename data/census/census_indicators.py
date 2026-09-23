#!/usr/bin/env python3
"""Pull Census ACS 5-Year indicators for all US ZIP/ZCTAs.

Requires a free Census API key: https://api.census.gov/data/key_signup.html
Set CENSUS_API_KEY env var or pass --key KEY.

Saves to data/census/us-zips-census.json

Usage:
    python3 data/census/census_indicators.py --key YOUR_KEY
    CENSUS_API_KEY=KEY python3 data/census/census_indicators.py

ZCTAs are national-level geographies — the Census API does not support
state-level filtering for them.  We fetch all ~33K ZCTAs per variable batch.
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_PATH = HERE / "us-zips-census.json"

# ACS 5-Year Detailed Table variables (ZCTA-compatible)
# Grouped into batches to keep URL length manageable.
VARIABLE_BATCHES = [
    # Poverty
    ["B17001_001E", "B17001_002E"],
    # Employment
    ["B23025_001E", "B23025_005E", "B23025_007E"],
    # SNAP
    ["B22003_001E", "B22003_002E"],
    # Income
    ["B19013_001E"],
    # Population + age
    ["B01001_001E"],
    # Tenure
    ["B25003_001E", "B25003_002E", "B25003_003E"],
    # Disability
    ["B18101_001E", "B18101_002E", "B18101_004E",
     "B18101_007E", "B18101_009E", "B18101_020E", "B18101_022E"],
    # Health insurance
    ["B27001_001E", "B27001_005E"],
]


def fetch_batch(variables: list[str], key: str) -> list[list]:
    """Fetch all ZCTAs for a batch of variables."""
    var_str = ",".join(["NAME"] + variables)
    url = (
        f"https://api.census.gov/data/2023/acs/acs5"
        f"?get={var_str}"
        f"&for=zip%20code%20tabulation%20area:*"
        f"&key={key}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Beacon/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"  HTTP {e.code}: {body}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  Error: {e}", file=sys.stderr)
        return []


def merge_batches(batches: list[tuple[list[str], list[list]]]) -> dict[str, dict]:
    """Merge variable batches into per-ZCTA records."""
    # Build header→data mapping per ZCTA
    zcta_data: dict[str, dict[str, str]] = {}

    for variables, raw_rows in batches:
        if not raw_rows or len(raw_rows) < 2:
            continue
        header = raw_rows[0]
        for row in raw_rows[1:]:
            data = dict(zip(header, row))
            zcta = data.get("NAME", "").replace("ZCTA5 ", "").strip()
            if not zcta:
                continue
            if zcta not in zcta_data:
                zcta_data[zcta] = {}
            # Merge all variables except NAME and geography column
            for k, v in data.items():
                if k not in ("NAME", "zip code tabulation area"):
                    zcta_data[zcta][k] = v

    # Compute derived indicators
    records: dict[str, dict] = {}
    for zcta, data in zcta_data.items():
        def _int(key: str) -> int | None:
            v = data.get(key)
            if v in (None, "", "null"):
                return None
            try:
                return int(v)
            except (ValueError, TypeError):
                return None

        poverty_total = _int("B17001_001E")
        poverty_below = _int("B17001_002E")
        emp_total = _int("B23025_001E")
        emp_unemployed = _int("B23025_005E")
        snap_total = _int("B22003_001E")
        snap_received = _int("B22003_002E")
        median_income = _int("B19013_001E")
        total_pop = _int("B01001_001E")
        health_total = _int("B27001_001E")
        uninsured_est = _int("B27001_005E")
        housing_total = _int("B25003_001E")
        owner = _int("B25003_002E")
        renter = _int("B25003_003E")
        civ_total = _int("B18101_001E")
        under18 = _int("B18101_002E")
        under18_dis = _int("B18101_004E")
        age18_64 = _int("B18101_007E")
        age18_64_dis = _int("B18101_009E")
        age65 = _int("B18101_020E")
        age65_dis = _int("B18101_022E")

        def _pct(num, den):
            if num is None or den is None or den == 0:
                return None
            return round(num / den * 100, 1)

        total_disability = ((under18_dis or 0) + (age18_64_dis or 0) + (age65_dis or 0))

        records[zcta] = {
            "poverty_rate": _pct(poverty_below, poverty_total),
            "unemployment_rate": _pct(emp_unemployed, emp_total),
            "snap_rate": _pct(snap_received, snap_total),
            "median_income": median_income,
            "total_population": total_pop,
            "disability_rate": _pct(total_disability, civ_total),
            "no_vehicle_rate": None,
            "renter_rate": _pct(renter, housing_total),
            "senior_pct": _pct(age65, civ_total),
            "child_pct": _pct(under18, civ_total),
            "uninsured_approx": _pct(uninsured_est, health_total),
            "_raw": {
                "poverty_total": poverty_total,
                "poverty_below": poverty_below,
                "emp_total": emp_total,
                "emp_unemployed": emp_unemployed,
                "snap_total": snap_total,
                "snap_received": snap_received,
                "housing_total": housing_total,
                "renter": renter,
                "owner": owner,
                "civ_total": civ_total,
                "total_disability": total_disability,
            },
        }

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull Census ACS indicators for ZCTAs")
    parser.add_argument("--key", default=os.environ.get("CENSUS_API_KEY", ""),
                        help="Census API key (or set CENSUS_API_KEY env var)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds between API requests (default: 1.0)")
    args = parser.parse_args()

    if not args.key:
        print("ERROR: Census API key required.", file=sys.stderr)
        print("  Get one free: https://api.census.gov/data/key_signup.html", file=sys.stderr)
        print("  Then: --key YOUR_KEY  or  CENSUS_API_KEY=KEY python3 ...", file=sys.stderr)
        sys.exit(1)

    all_batches: list[tuple[list[str], list[list]]] = []

    for i, variables in enumerate(VARIABLE_BATCHES):
        label = "+".join(variables[:2]) + ("..." if len(variables) > 2 else "")
        print(f"[{i+1}/{len(VARIABLE_BATCHES)}] Fetching {label}...")
        raw = fetch_batch(variables, args.key)
        count = max(0, len(raw) - 1) if raw else 0
        print(f"  → {count} ZCTAs")
        all_batches.append((variables, raw))
        if i < len(VARIABLE_BATCHES) - 1:
            time.sleep(args.delay)

    records = merge_batches(all_batches)

    OUT_PATH.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWrote {len(records)} ZCTAs → {OUT_PATH}")


if __name__ == "__main__":
    main()
