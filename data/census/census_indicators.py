#!/usr/bin/env python3
"""Pull Census ACS 5-Year indicators for all US ZIP/ZCTAs.

Requires a free Census API key: https://api.census.gov/data/key_signup.html
Set CENSUS_API_KEY env var or pass --key KEY.

Saves to data/census/us-zips-census.json

Usage:
    python3 data/census/census_indicators.py --key YOUR_KEY
    CENSUS_API_KEY=KEY python3 data/census/census_indicators.py

The script batches requests by state to stay under URL length limits
and adds a 0.2s delay between requests to be polite to the API.
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
US_ZIPS_PATH = HERE / "us-zips.json"
OUT_PATH = HERE / "us-zips-census.json"

# ACS 5-Year variables (Detailed Tables — ZCTA-compatible)
# B17001: Poverty status by sex by age
# B23025: Employment status
# B22003: Food stamps/SNAP by poverty status
# B19013: Median household income
# B01001: Sex by age
# B27001: Health insurance coverage
# B08006: Means of transportation to work (vehicle ownership proxy)
# B25003: Tenure (owner vs renter)
# B18101: Disability status by age/sex
VARIABLES = [
    # Poverty
    "B17001_001E",  # total (poverty universe)
    "B17001_002E",  # below poverty level (total)
    # Employment
    "B23025_001E",  # total 16+
    "B23025_005E",  # unemployed
    "B23025_007E",  # not in labor force
    # SNAP
    "B22003_001E",  # total households
    "B22003_002E",  # received SNAP
    # Income
    "B19013_001E",  # median household income
    # Population
    "B01001_001E",  # total population
    # Health insurance
    "B27001_001E",  # total (health insurance universe)
    "B27001_005E",  # uninsured (male 0-17) through _017E (uninsured total approx)
    # Tenure
    "B25003_001E",  # total occupied units
    "B25003_002E",  # owner-occupied
    "B25003_003E",  # renter-occupied
    # Disability (simplified: total with/without disability)
    "B18101_001E",  # total civilian noninstitutionalized
    "B18101_002E",  # total under 18
    "B18101_004E",  # under 18 with disability
    "B18101_007E",  # 18-64
    "B18101_009E",  # 18-64 with disability
    "B18101_020E",  # 65+
    "B18101_022E",  # 65+ with disability
    # Vehicle availability (no vehicle = transportation need)
    "B08006_001E",  # total workers 16+
    "B08006_017E",  # worked from home
]

# Descriptive labels for computed indicators
INDICATOR_LABELS = {
    "poverty_rate": "Population below poverty level (%)",
    "unemployment_rate": "Unemployment rate (%)",
    "snap_rate": "Households receiving SNAP (%)",
    "median_income": "Median household income ($)",
    "total_population": "Total population",
    "uninsured_rate": "Uninsured population (est.)",
    "disability_rate": "Population with disability (%)",
    "no_vehicle_rate": "Workers without vehicle (proxy, %)",
    "renter_rate": "Renter-occupied housing (%)",
    "senior_pct": "Population 65+ (%)",
    "child_pct": "Population under 18 (%)",
}

STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR",
]


def fetch_state(state_abbr: str, key: str) -> list[list]:
    """Fetch all ZCTA records for a state."""
    var_str = ",".join(VARIABLES)
    url = (
        f"https://api.census.gov/data/2023/acs/acs5"
        f"?get=NAME,{var_str}"
        f"&for=zip%20code%20tabulation%20area:*"
        f"&in=state:{_state_fips(state_abbr)}"
        f"&key={key}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Beacon/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {state_abbr}: {e.reason}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  Error for {state_abbr}: {e}", file=sys.stderr)
        return []


# State FIPS lookup (subset we need for the API)
_STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13",
    "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29",
    "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45",
    "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
    "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
    "DC": "11", "PR": "72",
}


def _state_fips(abbr: str) -> str:
    return _STATE_FIPS.get(abbr, "00")


def parse_raw(raw_rows: list[list]) -> dict[str, dict]:
    """Parse raw Census API response into structured data keyed by ZCTA."""
    if not raw_rows or len(raw_rows) < 2:
        return {}

    header = raw_rows[0]
    records: dict[str, dict] = {}

    for row in raw_rows[1:]:
        data = dict(zip(header, row))
        zcta = data.get("NAME", "").replace("ZCTA5 ", "").strip()
        if not zcta:
            continue

        def _int(key: str) -> int | None:
            v = data.get(key)
            if v in (None, "", "null"):
                return None
            try:
                return int(v)
            except (ValueError, TypeError):
                return None

        def _float(key: str) -> float | None:
            v = _int(key)
            return float(v) if v is not None else None

        # Compute derived indicators
        poverty_total = _int("B17001_001E")
        poverty_below = _int("B17001_002E")
        emp_total = _int("B23025_001E")
        emp_unemployed = _int("B23025_005E")
        snap_total = _int("B22003_001E")
        snap_received = _int("B22003_002E")
        median_income = _int("B19013_001E")
        total_pop = _int("B01001_001E")
        health_total = _int("B27001_001E")
        # Approximate uninsured: sum of uninsured by age groups
        # B27001_005E-017E alternates insured/uninsured by age/sex
        # Simplified: use a rough total if available
        uninsured_est = _int("B27001_005E")  # partial, will note in metadata
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
        workers = _int("B08006_001E")
        no_vehicle_approx = None  # B08006 doesn't have direct "no vehicle" in our subset

        def _pct(num: int | None, den: int | None) -> float | None:
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
            "no_vehicle_rate": None,  # requires B08006 detailed tables
            "renter_rate": _pct(renter, housing_total),
            "senior_pct": _pct(age65, civ_total),
            "child_pct": _pct(under18, civ_total),
            "uninsured_approx": _pct(uninsured_est, health_total),
            # Keep raw totals for downstream recalculation
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
    parser.add_argument("--states", nargs="*", default=None,
                        help="Limit to specific state abbreviations (default: all)")
    parser.add_argument("--delay", type=float, default=0.2,
                        help="Seconds between API requests (default: 0.2)")
    args = parser.parse_args()

    if not args.key:
        print("ERROR: Census API key required.", file=sys.stderr)
        print("  Get one free: https://api.census.gov/data/key_signup.html", file=sys.stderr)
        print("  Then: --key YOUR_KEY  or  CENSUS_API_KEY=KEY python3 ...", file=sys.stderr)
        sys.exit(1)

    states = args.states if args.states else STATES
    all_records: dict[str, dict] = {}

    for i, state in enumerate(states):
        print(f"[{i+1}/{len(states)}] Fetching {state}...")
        raw = fetch_state(state, args.key)
        parsed = parse_raw(raw)
        all_records.update(parsed)
        print(f"  → {len(parsed)} ZCTAs")
        if i < len(states) - 1:
            time.sleep(args.delay)

    OUT_PATH.write_text(
        json.dumps(all_records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWrote {len(all_records)} ZCTAs → {OUT_PATH}")


if __name__ == "__main__":
    main()
