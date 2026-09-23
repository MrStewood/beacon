#!/usr/bin/env python3
"""Compute composite needs scores for US ZIP codes.

Cross-references Census ACS indicators against existing Beacon resource
coverage to identify areas of highest unmet need.

Requires:
  - data/census/us-zips.json        (ZIP→county/city/state)
  - data/census/us-zips-census.json (ACS indicators)
  - data/resources.json             (existing Beacon resources)

Saves to data/census/needs-analysis.json

Usage:
    python3 data/census/needs_score.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
US_ZIPS_PATH = HERE / "us-zips.json"
CENSUS_PATH = HERE / "us-zips-census.json"
BEACON_DATA = HERE.parent / "resources.json"
STATES_DIR = HERE.parent / "states"
OUT_PATH = HERE / "needs-analysis.json"

# Weights for composite need score (0-100 scale)
WEIGHTS = {
    "poverty_rate": 0.25,
    "unemployment_rate": 0.15,
    "snap_rate": 0.20,
    "disability_rate": 0.15,
    "renter_rate": 0.10,
    "income_inverse": 0.15,  # lower income = higher need
}

# Thresholds for flagging
HIGH_NEED_THRESHOLD = 60  # composite score above this = high need
MODERATE_NEED_THRESHOLD = 35


def load_json(path: Path) -> dict:
    if not path.exists():
        print(f"WARNING: {path} not found", file=sys.stderr)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def count_resources_per_zip(resources: list[dict]) -> dict[str, int]:
    """Count how many Beacon resources exist per ZIP."""
    counts: dict[str, int] = defaultdict(int)
    for r in resources:
        # Check both v2 (zip) and v3 (postal_code) formats
        locs = r.get("locations", [])
        if locs:
            for loc in locs:
                zc = loc.get("postal_code") or loc.get("zip", "")
                if zc:
                    counts[zc.strip().zfill(5)] += 1
        else:
            zc = r.get("zip", "") or r.get("postal_code", "")
            if zc:
                counts[zc.strip().zfill(5)] += 1
    return dict(counts)


def count_resources_per_county(resources: list[dict], zips: dict) -> dict[str, int]:
    """Count resources per county (using ZIP→county mapping)."""
    counts: dict[str, int] = defaultdict(int)
    for r in resources:
        locs = r.get("locations", [])
        zip_codes = []
        if locs:
            for loc in locs:
                zc = loc.get("postal_code") or loc.get("zip", "")
                if zc:
                    zip_codes.append(zc.strip().zfill(5))
        else:
            zc = r.get("zip", "") or r.get("postal_code", "")
            if zc:
                zip_codes.append(zc.strip().zfill(5))

        for zc in zip_codes:
            info = zips.get(zc)
            if info and isinstance(info, dict) and not info.get("_multi_county"):
                county_key = f"{info['state']}|{info['county']}"
                counts[county_key] += 1
            elif info and isinstance(info, dict) and info.get("_multi_county"):
                for c in info.get("counties", []):
                    county_key = f"{c['state']}|{c['county']}"
                    counts[county_key] += 1
    return dict(counts)


def compute_need_score(indicators: dict) -> float | None:
    """Compute composite need score 0-100.  Higher = more need."""
    scores = {}
    missing = 0

    poverty = indicators.get("poverty_rate")
    if poverty is not None:
        scores["poverty_rate"] = min(poverty * 2, 100)  # 50% poverty → 100 score

    unemp = indicators.get("unemployment_rate")
    if unemp is not None:
        scores["unemployment_rate"] = min(unemp * 3, 100)  # 33% unemp → 100

    snap = indicators.get("snap_rate")
    if snap is not None:
        scores["snap_rate"] = min(snap * 2, 100)  # 50% SNAP → 100

    disability = indicators.get("disability_rate")
    if disability is not None:
        scores["disability_rate"] = min(disability * 3, 100)  # 33% → 100

    renter = indicators.get("renter_rate")
    if renter is not None:
        scores["renter_rate"] = min(renter * 1.2, 100)  # 83% renter → 100

    income = indicators.get("median_income")
    if income is not None and income > 0:
        # Inverse: $0 → 100, $100k+ → 0
        scores["income_inverse"] = max(0, 100 - (income / 1000))

    if not scores:
        return None

    total_weight = 0
    weighted_sum = 0
    for metric, weight in WEIGHTS.items():
        if metric in scores:
            weighted_sum += scores[metric] * weight
            total_weight += weight

    if total_weight == 0:
        return None

    return round(weighted_sum / total_weight, 1)


def main() -> None:
    zips = load_json(US_ZIPS_PATH)
    census = load_json(CENSUS_PATH)
    resources_raw = load_json(BEACON_DATA)

    if not zips or not census:
        print("ERROR: Missing us-zips.json or us-zips-census.json", file=sys.stderr)
        print("  Run build_us_zips.py and census_indicators.py first.", file=sys.stderr)
        sys.exit(1)

    # Also load state-level resources
    resources = resources_raw.get("resources", [])
    if STATES_DIR.exists():
        for state_dir in STATES_DIR.iterdir():
            sr = state_dir / "resources.json"
            if sr.exists():
                data = json.loads(sr.read_text(encoding="utf-8"))
                resources.extend(data.get("resources", []))

    zip_counts = count_resources_per_zip(resources)
    county_counts = count_resources_per_county(resources, zips)

    # Build analysis per ZIP
    analysis: dict[str, dict] = {}
    state_summaries: dict[str, dict] = defaultdict(lambda: {
        "zips": 0, "high_need": 0, "moderate_need": 0, "total_pop": 0,
        "avg_poverty": [], "avg_unemployment": [], "avg_snap": [],
        "covered_zips": 0,
    })

    for zc, indicators in census.items():
        score = compute_need_score(indicators)
        pop = indicators.get("total_population") or 0

        # County coverage
        zip_info = zips.get(zc, {})
        county_key = None
        if isinstance(zip_info, dict) and not zip_info.get("_multi_county"):
            county_key = f"{zip_info.get('state', '')}|{zip_info.get('county', '')}"

        county_resources = county_counts.get(county_key, 0) if county_key else 0

        flag = "unknown"
        if score is not None:
            if score >= HIGH_NEED_THRESHOLD:
                flag = "high"
            elif score >= MODERATE_NEED_THRESHOLD:
                flag = "moderate"
            else:
                flag = "low"

        entry = {
            "zip": zc,
            "need_score": score,
            "need_flag": flag,
            "population": pop,
            "existing_resources": zip_counts.get(zc, 0),
            "county": county_key.split("|")[1] if county_key else "Unknown",
            "state": county_key.split("|")[0] if county_key else zip_info.get("state", "Unknown"),
            "poverty_rate": indicators.get("poverty_rate"),
            "unemployment_rate": indicators.get("unemployment_rate"),
            "snap_rate": indicators.get("snap_rate"),
            "median_income": indicators.get("median_income"),
            "disability_rate": indicators.get("disability_rate"),
            "renter_rate": indicators.get("renter_rate"),
            "senior_pct": indicators.get("senior_pct"),
            "child_pct": indicators.get("child_pct"),
            "county_resource_count": county_resources,
        }
        analysis[zc] = entry

        # Aggregate to state
        st = entry["state"]
        if st and st != "Unknown":
            ss = state_summaries[st]
            ss["zips"] += 1
            ss["total_pop"] += pop
            if entry["existing_resources"] > 0:
                ss["covered_zips"] += 1
            if score is not None:
                if flag == "high":
                    ss["high_need"] += 1
                elif flag == "moderate":
                    ss["moderate_need"] += 1
                if indicators.get("poverty_rate") is not None:
                    ss["avg_poverty"].append(indicators["poverty_rate"])
                if indicators.get("unemployment_rate") is not None:
                    ss["avg_unemployment"].append(indicators["unemployment_rate"])
                if indicators.get("snap_rate") is not None:
                    ss["avg_snap"].append(indicators["snap_rate"])

    # Finalize state summaries
    state_final = {}
    for st, ss in sorted(state_summaries.items()):
        def _avg(lst):
            return round(sum(lst) / len(lst), 1) if lst else None
        state_final[st] = {
            "total_zips": ss["zips"],
            "total_population": ss["total_pop"],
            "covered_zips": ss["covered_zips"],
            "coverage_pct": round(ss["covered_zips"] / ss["zips"] * 100, 1) if ss["zips"] > 0 else 0,
            "high_need_zips": ss["high_need"],
            "moderate_need_zips": ss["moderate_need"],
            "avg_poverty_rate": _avg(ss["avg_poverty"]),
            "avg_unemployment_rate": _avg(ss["avg_unemployment"]),
            "avg_snap_rate": _avg(ss["avg_snap"]),
        }

    output = {
        "metadata": {
            "total_zips": len(analysis),
            "total_with_data": sum(1 for v in analysis.values() if v["need_score"] is not None),
            "high_need_count": sum(1 for v in analysis.values() if v["need_flag"] == "high"),
            "moderate_need_count": sum(1 for v in analysis.values() if v["need_flag"] == "moderate"),
            "total_resources": len(resources),
            "source": "US Census ACS 5-Year 2023",
            "methodology": "Composite score: poverty 25%, SNAP 20%, unemployment 15%, disability 15%, income 15%, renter 10%",
        },
        "state_summaries": state_final,
        "zip_analysis": analysis,
    }

    OUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    meta = output["metadata"]
    print(f"Wrote needs analysis: {meta['total_zips']} ZIPs, "
          f"{meta['high_need_count']} high-need, "
          f"{meta['moderate_need_count']} moderate-need, "
          f"{meta['total_resources']} existing resources → {OUT_PATH}")


if __name__ == "__main__":
    main()
