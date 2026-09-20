"""Tests for critical crisis resources (988, 211, etc.)."""

import json
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "data" / "resources.json"


@pytest.fixture
def resources():
    with open(DATA_PATH) as f:
        return json.load(f)["resources"]


class TestCrisisResources:
    """Verify critical crisis resources are correct."""

    def test_988_exists(self, resources):
        """988 Suicide Hotline must exist."""
        r988 = [r for r in resources if "988" in r.get("name", "")]
        assert len(r988) > 0, "988 crisis hotline not found in dataset"

    def test_988_has_phone(self, resources):
        """988 must have phone number 988."""
        r988 = [r for r in resources if "988" in r.get("name", "")][0]
        assert "988" in r988.get("phones", []), f"988 missing phone number. Found: {r988.get('phones')}"

    def test_988_is_crisis(self, resources):
        """988 must be classified as crisis resource."""
        r988 = [r for r in resources if "988" in r.get("name", "")][0]
        assert "crisis" in r988.get("needs", []), f"988 not in crisis category. Found: {r988.get('needs')}"

    def test_988_has_url(self, resources):
        """988 should have a website URL."""
        r988 = [r for r in resources if "988" in r.get("name", "")][0]
        assert r988.get("url"), "988 missing website URL"

    def test_211_exists(self, resources):
        """211 resource must exist."""
        r211 = [r for r in resources if "211" in r.get("name", "")]
        assert len(r211) > 0, "211 resource not found in dataset"

    def test_211_has_phone(self, resources):
        """211 must have phone number."""
        r211 = [r for r in resources if "211" in r.get("name", "")][0]
        phones = r211.get("phones", [])
        assert any("211" in p for p in phones), f"211 missing phone. Found: {phones}"

    def test_crisis_resources_have_phones(self, resources):
        """All crisis resources must have phone numbers."""
        crisis = [r for r in resources if "crisis" in r.get("needs", [])]
        for r in crisis:
            assert r.get("phones"), f"Crisis resource '{r['name']}' has no phone number"

    def test_no_xss_in_names(self, resources):
        """Resource names must not contain HTML/script tags."""
        for r in resources:
            name = r.get("name", "")
            assert "<script" not in name.lower(), f"XSS in name: {name}"
            assert "<img" not in name.lower(), f"XSS in name: {name}"
            assert "javascript:" not in name.lower(), f"XSS in name: {name}"

    def test_urls_are_safe(self, resources):
        """URLs must start with http:// or https://."""
        for r in resources:
            url = r.get("url", "")
            if url:
                assert url.startswith(("http://", "https://")), f"Unsafe URL in {r['id']}: {url}"

    def test_ids_are_unique(self, resources):
        """All resource IDs must be unique."""
        ids = [r["id"] for r in resources]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {[i for i in ids if ids.count(i) > 1]}"
