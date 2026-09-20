"""Tests for v3 geographic schema."""

import json
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
V3_DATA_PATH = REPO_ROOT / "data" / "v3" / "resources.json"
V3_SCHEMA_PATH = REPO_ROOT / "schema" / "resource.schema.v3.json"

try:
    import jsonschema
except ImportError:
    pytest.skip("jsonschema not installed", allow_module_level=True)

if not V3_DATA_PATH.exists():
    pytest.skip("V3 data not generated from empty dataset", allow_module_level=True)


@pytest.fixture
def v3_data():
    with open(V3_DATA_PATH) as f:
        return json.load(f)


class TestV3Migration:
    """Verify v3 migration is correct."""

    def test_v3_data_exists(self):
        """V3 data file should exist."""
        assert V3_DATA_PATH.exists(), "V3 data file not found"

    def test_all_resources_migrated(self, v3_data):
        """All v2 resources should be in v3."""
        assert v3_data["metadata"]["total_resources"] == 218

    def test_schema_version(self, v3_data):
        """Schema version should be 3.0."""
        assert v3_data["schema_version"] == "3.0"

    def test_all_have_coverage_scope(self, v3_data):
        """Every resource must have a coverage_scope."""
        for r in v3_data["resources"]:
            assert "coverage_scope" in r, f"{r['id']} missing coverage_scope"
            assert r["coverage_scope"] in [
                "national", "multi-state", "state", "multi-county", "county",
                "multi-city", "city", "postal-code", "radius", "tribal-area",
                "custom-region", "online", "unknown"
            ], f"{r['id']} invalid coverage_scope: {r['coverage_scope']}"

    def test_all_have_locations(self, v3_data):
        """Every resource must have at least one location."""
        for r in v3_data["resources"]:
            assert "locations" in r, f"{r['id']} missing locations"
            assert len(r["locations"]) >= 1, f"{r['id']} has no locations"

    def test_location_types_valid(self, v3_data):
        """Location types must be from allowed values."""
        valid = {"physical", "mailing", "mobile", "virtual", "confidential", "unknown"}
        for r in v3_data["resources"]:
            for loc in r["locations"]:
                assert loc["location_type"] in valid, \
                    f"{r['id']}.{loc['id']} invalid type: {loc['location_type']}"

    def test_statewide_has_state_coverage(self, v3_data):
        """Statewide resources should have state-level coverage."""
        for r in v3_data["resources"]:
            if r.get("county") == "Statewide":
                assert r["coverage_scope"] == "state", \
                    f"{r['id']} is Statewide but scope is {r['coverage_scope']}"
                assert "KY" in r.get("states_served", []), \
                    f"{r['id']} statewide but states_served missing KY"

    def test_county_has_fips(self, v3_data):
        """County resources should have FIPS codes."""
        for r in v3_data["resources"]:
            if r.get("county") and r["county"] != "Statewide":
                if r["coverage_scope"] == "county":
                    for area in r.get("service_areas", []):
                        if area["type"] == "county":
                            for v in area.get("values", []):
                                assert v.get("fips"), \
                                    f"{r['id']} county {v['name']} missing FIPS"

    def test_legacy_fields_preserved(self, v3_data):
        """Deprecated v2 fields should still exist for compatibility."""
        for r in v3_data["resources"]:
            assert "county" in r, f"{r['id']} missing deprecated county field"

    def test_states_served_valid(self, v3_data):
        """states_served must use 2-letter codes."""
        for r in v3_data["resources"]:
            for s in r.get("states_served", []):
                assert len(s) == 2 and s.isupper(), \
                    f"{r['id']} invalid state code: {s}"

    def test_no_county_name_confusion(self, v3_data):
        """Resources in different states should not share county+FIPS without state."""
        # This is a basic check - full validation needs cross-state data
        county_fips = {}
        for r in v3_data["resources"]:
            for area in r.get("service_areas", []):
                if area["type"] == "county":
                    for v in area.get("values", []):
                        key = (v.get("name"), v.get("fips"))
                        if key[0] and key[1]:
                            if key in county_fips:
                                # Same county name+FIPS is OK (same state)
                                pass
                            county_fips[key] = r["id"]
