#!/usr/bin/env python3
"""Geocode approved resources and derive service areas.

Adds to each approved YAML:
  location.latitude / longitude / geocoding_status / geocoding_source / geocoded_at
  service_areas — expressed as zip, city, county, or radius entries

Usage:
  python scripts/geocode.py            # all approved YAMLs missing coords
  python scripts/geocode.py --id <id>  # single resource
  python scripts/geocode.py --all      # re-geocode everything (overwrites)

Nominatim rate limit: 1 req/s.  User-Agent is required.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import yaml

try:
    import urllib.request as _req
    import urllib.parse as _parse
except ImportError:
    pass

REPO_ROOT   = Path(__file__).parent.parent
APPROVED    = REPO_ROOT / "source" / "approved"
SCHEMA_DIR  = REPO_ROOT / "schema" / "reference"

NOMINATIM_URL   = "https://nominatim.openstreetmap.org/search"
NOMINATIM_AGENT = "Beacon-Community-Directory/1.0 (https://mrstewood.github.io/beacon)"
RATE_LIMIT_S    = 1.1   # Nominatim requires ≥1 req/s


# ---------------------------------------------------------------------------
# FIPS reference
# ---------------------------------------------------------------------------

def _load_fips(state: str = "KY") -> dict[str, str]:
    """Return county_name → FIPS for a state."""
    fname = SCHEMA_DIR / f"{state.lower()}_counties.json"
    if not fname.exists():
        return {}
    with open(fname) as f:
        data = json.load(f)
    return {c["name"]: c["fips"] for c in data.get("counties", [])}


# ---------------------------------------------------------------------------
# Address parsing
# ---------------------------------------------------------------------------

def _clean_address_line(raw: str, city: str | None, state: str | None, postal: str | None) -> str:
    """Strip city/state/zip from address_line_1 if the agent embedded them.

    Anchors on the known city name to avoid stripping real street words.
    """
    if not raw:
        return raw
    # Anchor on known city name followed by optional ", STATE ZIP"
    if city:
        pattern = re.compile(
            r",?\s+" + re.escape(city) + r"(?:\s*,\s*[A-Z]{2}(?:\s+\d{5}(?:-\d{4})?)?)?\s*$",
            re.IGNORECASE,
        )
        m = pattern.search(raw)
        if m:
            street = raw[:m.start()].strip().rstrip(",")
            if street:
                return street
    # Fallback: strip trailing STATE ZIP only
    if state and postal:
        p2 = re.compile(
            r",?\s+" + re.escape(state) + r"\s+" + re.escape(postal[:5]) + r"(?:-\d{4})?\s*$"
        )
        m2 = p2.search(raw)
        if m2:
            street = raw[:m2.start()].strip().rstrip(",")
            if street:
                return street
    return raw


def _build_query(loc: dict) -> dict[str, str]:
    """Build Nominatim structured query params from a location dict."""
    raw = loc.get("address_line_1") or ""
    city   = loc.get("city")
    state  = loc.get("state")
    postal = loc.get("postal_code")
    street = _clean_address_line(raw, city, state, postal)

    params: dict[str, str] = {
        "format":          "json",
        "limit":           "1",
        "addressdetails":  "1",
        "countrycodes":    "us",
    }
    if street:
        params["street"] = street
    if city:
        params["city"] = city
    if state:
        params["state"] = state
    if postal:
        params["postalcode"] = postal
    return params


# ---------------------------------------------------------------------------
# Nominatim caller
# ---------------------------------------------------------------------------

_last_call: float = 0.0


def _nominatim(params: dict) -> list[dict]:
    global _last_call
    wait = RATE_LIMIT_S - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)

    qs  = _parse.urlencode(params)
    url = f"{NOMINATIM_URL}?{qs}"
    rq  = _req.Request(url, headers={"User-Agent": NOMINATIM_AGENT})
    try:
        with _req.urlopen(rq, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  WARN: Nominatim error: {e}", file=sys.stderr)
        data = []
    finally:
        _last_call = time.time()
    return data


# ---------------------------------------------------------------------------
# Service area derivation
# ---------------------------------------------------------------------------

def _derive_service_areas(r: dict, fips_map: dict[str, str]) -> list[dict]:
    """
    Derive service_areas list from coverage_scope and location.

    Supported types: postal-code, city, county, radius.
    national/state scopes → no service_area entries (use coverage_scope field).
    """
    scope = r.get("coverage_scope", "unknown")
    loc   = _first_physical(r)
    areas: list[dict] = []

    if scope in ("national", "multi-state", "state", "online", "unknown"):
        return areas   # coverage_scope field carries meaning; no map zones

    state = (loc or {}).get("state") or (r.get("states_served") or [None])[0]

    if scope == "county":
        county_name = (loc or {}).get("county_name")
        if county_name and state:
            fips = fips_map.get(county_name)
            area: dict[str, Any] = {
                "type":    "county",
                "state":   state,
                "country": "US",
                "values":  [{"name": county_name}],
            }
            if fips:
                area["values"][0]["fips"] = fips
            areas.append(area)

    elif scope in ("city", "multi-city"):
        city = (loc or {}).get("city")
        if city and state:
            areas.append({
                "type":    "city",
                "state":   state,
                "country": "US",
                "values":  [{"name": city}],
            })

    elif scope == "postal-code":
        postal = (loc or {}).get("postal_code")
        if postal and state:
            areas.append({
                "type":    "postal-code",
                "state":   state,
                "country": "US",
                "values":  [{"name": postal}],
            })

    elif scope == "radius":
        lat = (loc or {}).get("latitude")
        lon = (loc or {}).get("longitude")
        radius = r.get("radius_miles", 25)
        if lat and lon:
            areas.append({
                "type":         "radius",
                "center":       {"latitude": lat, "longitude": lon},
                "radius_miles": radius,
            })

    elif scope == "multi-county":
        # Only derive if service_areas already absent — can't guess multiple counties
        pass

    return areas


def _first_physical(r: dict) -> dict | None:
    for loc in r.get("locations", []):
        if loc.get("publicly_displayed", True) and loc.get("location_type") != "virtual":
            return loc
    return None


# ---------------------------------------------------------------------------
# Geocode one location
# ---------------------------------------------------------------------------

def geocode_location(loc: dict, force: bool = False) -> bool:
    """Geocode a single location dict in-place. Returns True if updated."""
    if loc.get("location_type") in ("virtual", "confidential"):
        return False
    if not loc.get("address_line_1"):
        return False
    if not force and loc.get("geocoding_status") in ("verified", "approximate"):
        return False

    params  = _build_query(loc)
    results = _nominatim(params)

    if not results:
        # Fallback: try city+state+postal only
        fallback = {k: v for k, v in params.items() if k not in ("street",)}
        results  = _nominatim(fallback)

    if not results:
        loc["geocoding_status"] = "failed"
        loc["geocoding_source"] = "nominatim"
        loc["geocoded_at"]      = str(date.today())
        print(f"  FAIL: no result for {loc.get('address_line_1')!r}")
        return True

    hit = results[0]
    loc["latitude"]         = float(hit["lat"])
    loc["longitude"]        = float(hit["lon"])
    loc["geocoding_status"] = "approximate"
    loc["geocoding_source"] = "nominatim"
    loc["geocoded_at"]      = str(date.today())

    # Also clean address_line_1 if city/state/zip were embedded
    raw    = loc.get("address_line_1", "")
    street = _clean_address_line(raw, loc.get("city"), loc.get("state"), loc.get("postal_code"))
    if street != raw:
        loc["address_line_1"] = street

    # Backfill city/state/postal from Nominatim if missing
    addr = hit.get("address", {})
    if not loc.get("city"):
        loc["city"] = addr.get("city") or addr.get("town") or addr.get("village")
    if not loc.get("state"):
        loc["state"] = addr.get("state_code") or addr.get("ISO3166-2-lvl4", "").split("-")[-1] or None
    if not loc.get("postal_code"):
        loc["postal_code"] = addr.get("postcode")
    if not loc.get("county_name"):
        county_raw = addr.get("county", "")
        loc["county_name"] = re.sub(r"\s+County$", "", county_raw, flags=re.I).strip() or None

    print(f"  OK: ({loc['latitude']:.5f}, {loc['longitude']:.5f})  {hit['display_name'][:80]}")
    return True


# ---------------------------------------------------------------------------
# Process one resource YAML
# ---------------------------------------------------------------------------

def process_yaml(path: Path, fips_map: dict[str, str], force: bool = False) -> bool:
    with open(path) as f:
        # Preserve leading comment
        raw = f.read()
    header = ""
    if raw.startswith("#"):
        lines = raw.splitlines(keepends=True)
        header_lines = []
        for line in lines:
            if line.startswith("#") or line.strip() == "":
                header_lines.append(line)
            else:
                break
        header = "".join(header_lines)

    r = yaml.safe_load(raw)
    changed = False

    # 1. Geocode each physical location
    for loc in r.get("locations", []):
        if geocode_location(loc, force=force):
            changed = True

    # 2. Derive service_areas if missing or empty (candidate.py may have already set them)
    if not r.get("service_areas"):
        areas = _derive_service_areas(r, fips_map)
        if areas:
            r["service_areas"] = areas
            changed = True
    else:
        # Enrich existing county service_areas with FIPS if absent
        for area in r.get("service_areas", []):
            if area.get("type") == "county":
                for v in area.get("values", []):
                    if v.get("name") and not v.get("fips"):
                        fips = fips_map.get(v["name"])
                        if fips:
                            v["fips"] = fips
                            changed = True
        # Attach radius center lat/lng from location if missing
        loc = _first_physical(r)
        for area in r.get("service_areas", []):
            if area.get("type") == "radius" and not area.get("center"):
                if loc and loc.get("latitude") and loc.get("longitude"):
                    area["center"] = {"latitude": loc["latitude"], "longitude": loc["longitude"]}
                    changed = True

    # 3. Add county_fips to locations that have county_name
    for loc in r.get("locations", []):
        if loc.get("county_name") and not loc.get("county_fips"):
            fips = fips_map.get(loc["county_name"])
            if fips:
                loc["county_fips"] = fips
                changed = True

    if changed:
        with open(path, "w") as f:
            if header:
                f.write(header)
            yaml.dump(r, f, allow_unicode=True, sort_keys=False, width=120, default_flow_style=False)
        print(f"  Saved: {path.name}")

    return changed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id",  dest="rid",  help="Single resource ID")
    ap.add_argument("--all", dest="force", action="store_true",
                    help="Re-geocode even already-geocoded locations")
    args = ap.parse_args()

    fips_map = _load_fips("KY")   # expand when we cover more states

    yamls: list[Path] = []
    if args.rid:
        matches = list(APPROVED.rglob(f"*{args.rid}*.yaml"))
        if not matches:
            print(f"No YAML found for id {args.rid!r}", file=sys.stderr)
            sys.exit(1)
        yamls = matches
    else:
        yamls = sorted(APPROVED.rglob("*.yaml"))

    total = changed = 0
    for p in yamls:
        print(f"\n{p.relative_to(REPO_ROOT)}")
        total   += 1
        if process_yaml(p, fips_map, force=args.force):
            changed += 1

    print(f"\nDone: {changed}/{total} files updated")


if __name__ == "__main__":
    main()
