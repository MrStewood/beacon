"""Tests for JSON Schema validation."""

import json
import pytest
from pathlib import Path

try:
    import jsonschema
except ImportError:
    pytest.skip("jsonschema not installed", allow_module_level=True)

REPO_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = REPO_ROOT / "schema" / "resource.schema.v3.json"
DATA_PATH = REPO_ROOT / "data" / "resources.json"


@pytest.fixture
def schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


@pytest.fixture
def resources():
    with open(DATA_PATH) as f:
        return json.load(f)["resources"]


class TestSchemaValidation:
    """Validate all resources against JSON Schema."""

    def test_all_resources_pass_schema(self, resources, schema):
        """Every resource must validate against the schema."""
        validator = jsonschema.Draft202012Validator(schema)
        errors = []
        for r in resources:
            errs = list(validator.iter_errors(r))
            for e in errs:
                errors.append(f"{r.get('id', '?')}.{e.json_path}: {e.message}")
        assert not errors, f"Schema errors:\n" + "\n".join(errors[:20])

    def test_required_fields_present(self, resources):
        """Required fields (id, name, county, status) must be present."""
        for r in resources:
            assert r.get("id"), f"Missing id in resource"
            assert r.get("name"), f"Missing name in resource"
            assert r.get("county"), f"Missing county in resource"
            assert r.get("status"), f"Missing status in resource"

    def test_valid_status_values(self, resources):
        """Status must be one of: active, needs-verification, closed."""
        valid = {"active", "needs-verification", "closed"}
        for r in resources:
            assert r.get("status") in valid, f"Invalid status in {r['id']}: {r.get('status')}"

    def test_valid_need_values(self, resources):
        """Needs must be from the defined enum."""
        valid = {
            "addiction", "clothing", "community", "crisis", "documents",
            "education", "family", "food", "health", "housing",
            "jobs", "legal", "mental-health", "shelter", "transportation",
            "utility-assistance", "veterans"
        }
        for r in resources:
            for need in r.get("needs", []):
                assert need in valid, f"Invalid need in {r['id']}: {need}"

    def test_valid_cost_values(self, resources):
        """Cost must be from the defined enum."""
        valid = {"free", "sliding-scale", "insurance", "private-pay", "unknown"}
        for r in resources:
            assert r.get("cost") in valid, f"Invalid cost in {r['id']}: {r.get('cost')}"

    def test_valid_confidence_values(self, resources):
        """Confidence must be from the defined enum."""
        valid = {"high", "medium", "low"}
        for r in resources:
            assert r.get("confidence") in valid, f"Invalid confidence in {r['id']}: {r.get('confidence')}"

    def test_id_format(self, resources):
        """IDs must be lowercase, alphanumeric with hyphens."""
        for r in resources:
            rid = r.get("id", "")
            assert rid.islower(), f"ID not lowercase: {rid}"
            assert all(c.isalnum() or c == "-" for c in rid), f"ID has invalid chars: {rid}"
            assert not rid.startswith("-"), f"ID starts with hyphen: {rid}"
            assert not rid.endswith("-"), f"ID ends with hyphen: {rid}"

    def test_at_least_one_need(self, resources):
        """Every resource must have at least one need."""
        for r in resources:
            assert r.get("needs"), f"No needs in {r['id']}"
            assert len(r["needs"]) >= 1, f"Empty needs array in {r['id']}"
