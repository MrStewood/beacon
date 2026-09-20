#!/usr/bin/env python3
"""Geocode physical addresses using US Census Geocoder (free, no API key)."""

import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
CACHE_FILE = DATA_DIR / "v3" / "geocode_cache.json"

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

def geocode_address(address, city=None, state="KY", zip_code=None):
    """Geocode an address using US Census Geocoder."""
    # Build address string
    parts = []
    if address:
        parts.append(address)
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    if zip_code:
        parts.append(zip_code)

    address_str = ", ".join(parts)

    params = {
        "address": address_str,
        "benchmark": "Public_AR_Current",
        "format": "json"
    }

    url = f"{CENSUS_GEOCODER_URL}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Beacon/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        result = data.get("result", {})
        matches = result.get("addressMatches", [])

        if matches:
            match = matches[0]
            coords = match["coordinates"]
            return {
                "latitude": coords["y"],
                "longitude": coords["x"],
                "geocoding_status": "verified",
                "geocoding_source": "US Census Geocoder",
                "match_address": match.get("matchedAddress", "")
            }
        else:
            return {
                "latitude": None,
                "longitude": None,
                "geocoding_status": "failed",
                "geocoding_source": "US Census Geocoder",
                "match_address": None
            }
    except Exception as e:
        return {
            "latitude": None,
            "longitude": None,
            "geocoding_status": "failed",
            "geocoding_source": f"Error: {str(e)}",
            "match_address": None
        }

def load_cache():
    """Load geocoding cache."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}

def save_cache(cache):
    """Save geocoding cache."""
    os.makedirs(CACHE_FILE.parent, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def main():
    # Load v3 data
    with open(DATA_DIR / "v3" / "resources.json") as f:
        v3_data = json.load(f)

    # Load cache
    cache = load_cache()

    geocoded = 0
    cached = 0
    failed = 0
    skipped = 0

    for r in v3_data["resources"]:
        for loc in r.get("locations", []):
            # Skip non-physical or confidential locations
            if loc["location_type"] not in ("physical", "mailing"):
                skipped += 1
                continue

            if not loc.get("publicly_displayed", True):
                skipped += 1
                continue

            if not loc.get("address_line_1"):
                skipped += 1
                continue

            # Skip if already geocoded
            if loc.get("geocoding_status") == "verified" and loc.get("latitude"):
                cached += 1
                continue

            # Build cache key
            cache_key = f"{loc.get('address_line_1', '')}, {loc.get('city', '')}, {loc.get('state', 'KY')} {loc.get('postal_code', '')}"

            # Check cache
            if cache_key in cache:
                cached_result = cache[cache_key]
                loc["latitude"] = cached_result.get("latitude")
                loc["longitude"] = cached_result.get("longitude")
                loc["geocoding_status"] = cached_result.get("geocoding_status", "verified")
                loc["geocoding_source"] = cached_result.get("geocoding_source", "cache")
                loc["geocoded_at"] = cached_result.get("geocoded_at", "2026-09-20")
                cached += 1
                continue

            # Geocode
            print(f"Geocoding: {r['name']} - {cache_key}")
            result = geocode_address(
                loc.get("address_line_1"),
                loc.get("city"),
                loc.get("state", "KY"),
                loc.get("postal_code")
            )

            loc["latitude"] = result["latitude"]
            loc["longitude"] = result["longitude"]
            loc["geocoding_status"] = result["geocoding_status"]
            loc["geocoding_source"] = result["geocoding_source"]
            loc["geocoded_at"] = "2026-09-20"

            # Cache result
            cache[cache_key] = {
                "latitude": result["latitude"],
                "longitude": result["longitude"],
                "geocoding_status": result["geocoding_status"],
                "geocoding_source": result["geocoding_source"],
                "geocoded_at": "2026-09-20"
            }

            if result["geocoding_status"] == "verified":
                geocoded += 1
            else:
                failed += 1

            # Rate limit (Census allows 5 req/sec)
            time.sleep(0.25)

    # Save updated data
    with open(DATA_DIR / "v3" / "resources.json", "w") as f:
        json.dump(v3_data, f, indent=2)

    # Save cache
    save_cache(cache)

    # Generate GeoJSON
    features = []
    for r in v3_data["resources"]:
        for loc in r.get("locations", []):
            if loc.get("latitude") and loc.get("longitude") and loc.get("publicly_displayed", True):
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [loc["longitude"], loc["latitude"]]
                    },
                    "properties": {
                        "id": r["id"],
                        "name": r["name"],
                        "county": loc.get("county_name"),
                        "state": loc.get("state"),
                        "needs": r.get("needs", []),
                        "phones": r.get("phones", []),
                        "coverage_scope": r.get("coverage_scope")
                    }
                })

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    with open(DATA_DIR / "v3" / "geojson.json", "w") as f:
        json.dump(geojson, f, indent=2)

    print(f"\n=== Geocoding Results ===")
    print(f"Geocoded: {geocoded}")
    print(f"Cached: {cached}")
    print(f"Failed: {failed}")
    print(f"Skipped: {skipped}")
    print(f"GeoJSON features: {len(features)}")

if __name__ == "__main__":
    main()
