"""Tests for geocoding address normalization and publication geography gates."""

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


geocode = _load_module("beacon_geocode_for_tests", "scripts/geocode.py")
validate_sources = _load_module("beacon_validate_sources_for_tests", "scripts/validate_sources.py")


class TestGeocodeAddressParsing:
    def test_embedded_address_parts_take_priority_over_lead_postal_code(self):
        loc = {
            "address_line_1": "London Community Center, 529 S. Main Street, London, KY 40741",
            "state": "KY",
            "postal_code": "40744",
        }

        query = geocode._build_query(loc)

        assert query["street"] == "529 S. Main Street"
        assert query["city"] == "London"
        assert query["state"] == "KY"
        assert query["postalcode"] == "40741"

    def test_city_anchor_cleans_address_without_embedded_state_zip(self):
        loc = {
            "address_line_1": "111 North McWhorter Street, London",
            "city": "London",
            "state": "KY",
            "postal_code": "40741",
        }

        assert geocode._build_query(loc)["street"] == "111 North McWhorter Street"


class TestPublicationGeographyValidation:
    def test_local_active_service_requires_service_area(self):
        errors, _ = validate_sources.validate_geography([{
            "id": "local",
            "status": "active",
            "coverage_scope": "county",
            "locations": [],
        }])

        assert "local: local active service missing service_areas" in errors

    def test_public_physical_location_requires_coordinates(self):
        errors, _ = validate_sources.validate_geography([{
            "id": "place",
            "status": "active",
            "coverage_scope": "county",
            "service_areas": [{"type": "county"}],
            "locations": [{
                "location_type": "physical",
                "publicly_displayed": True,
                "address_line_1": "1 Example St",
                "geocoding_status": "failed",
            }],
        }])

        assert "place: public physical location has failed geocoding" in errors
        assert "place: public physical location missing latitude/longitude" in errors

    def test_national_virtual_resource_is_not_gated_by_local_rules(self):
        errors, warnings = validate_sources.validate_geography([{
            "id": "hotline",
            "status": "active",
            "coverage_scope": "national",
            "locations": [{"location_type": "virtual"}],
        }])

        assert errors == []
        assert warnings == []
