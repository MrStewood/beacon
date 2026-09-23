#!/usr/bin/env python3
"""Build us-zips.json from Census geo-data.csv.

Parses the raw CSV (from scpike/us-state-county-zip) into a JSON lookup
table keyed by ZIP code.  A single ZIP may span multiple counties; this
script keeps every county entry so agents can disambiguate.

Source: https://github.com/scpike/us-state-county-zip
License: Public domain (derived from Census Bureau data)

Usage:
    python3 data/census/build_us_zips.py
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "geo-data.csv"
OUT_PATH = HERE / "us-zips.json"


def build() -> None:
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} not found.", file=sys.stderr)
        print(f"  Download from: https://raw.githubusercontent.com/scpike/us-state-county-zip/master/geo-data.csv", file=sys.stderr)
        print(f"  curl -sL 'https://raw.githubusercontent.com/scpike/us-state-county-zip/master/geo-data.csv' -o {CSV_PATH}", file=sys.stderr)
        sys.exit(1)

    zips: dict[str, list[dict]] = defaultdict(list)
    total = 0

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            zc = row["zipcode"].strip().zfill(5)
            zips[zc].append({
                "state": row["state_abbr"].strip(),
                "state_name": row["state"].strip(),
                "county": row["county"].strip(),
                "city": row["city"].strip(),
                "state_fips": row["state_fips"].strip(),
            })
            total += 1

    # For single-county ZIPs, flatten to a dict.
    # For multi-county, keep the list with a flag.
    out: dict[str, dict | list] = {}
    multi_county = 0
    for zc, entries in sorted(zips.items()):
        if len(entries) == 1:
            out[zc] = entries[0]
        else:
            multi_county += 1
            out[zc] = {"_multi_county": True, "counties": entries}

    OUT_PATH.write_text(
        json.dumps(out, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(out)} ZIP codes ({total} rows, {multi_county} multi-county) → {OUT_PATH}")


if __name__ == "__main__":
    build()
