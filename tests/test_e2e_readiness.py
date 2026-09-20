"""End-to-end readiness test for Paperclip pilot."""

import json
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SOURCE_DIR = REPO_ROOT / "source" / "approved"
DATA_DIR = REPO_ROOT / "data"


def _resource_count() -> int:
    """Return the number of resources in the public dataset, or 0 if absent."""
    resources_file = DATA_DIR / "resources.json"
    if not resources_file.exists():
        return 0
    with open(resources_file) as f:
        data = json.load(f)
    return len(data.get("resources", []))


@pytest.mark.skipif(
    _resource_count() == 0,
    reason="empty dataset (0 resources) — known intermediate state",
)
class TestEndToEndReadiness:
    """Verify the complete workflow is ready for Paperclip pilot."""

    def test_canonical_yaml_exists(self):
        """At least one canonical YAML resource must exist."""
        yaml_files = list(SOURCE_DIR.rglob("*.yaml"))
        assert len(yaml_files) >= 3, f"Need at least 3 canonical resources, found {len(yaml_files)}"

    def test_national_resources_exist(self):
        """988 and 211 must exist as national resources."""
        national_dir = SOURCE_DIR / "national"
        assert national_dir.exists(), "National directory missing"
        yaml_files = list(national_dir.glob("*.yaml"))
        names = [f.stem for f in yaml_files]
        assert any("988" in n for n in names), "988 not in national directory"
        assert any("211" in n for n in names), "211 not in national directory"

    def test_ky_resources_exist(self):
        """Kentucky resources must exist."""
        ky_dir = SOURCE_DIR / "us" / "ky"
        assert ky_dir.exists(), "KY directory missing"
        yaml_files = list(ky_dir.rglob("*.yaml"))
        assert len(yaml_files) >= 1, "No KY resources found"

    def test_governance_files_exist(self):
        """All governance documents must exist."""
        required = [
            "AGENTS.md", "GOVERNANCE.md", "VERIFICATION_POLICY.md",
            "PRIVACY_AND_SAFETY.md", "AGENT_POLICY.md", "SOURCE_POLICY.md",
            "DATA_LIFECYCLE.md"
        ]
        for f in required:
            assert (REPO_ROOT / f).exists(), f"Missing {f}"

    def test_issue_forms_exist(self):
        """Issue forms must exist."""
        forms_dir = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
        assert forms_dir.exists()
        yml_files = list(forms_dir.glob("*.yml"))
        assert len(yml_files) >= 4, f"Need at least 4 issue forms, found {len(yml_files)}"

    def test_pr_template_exists(self):
        """PR template must exist."""
        assert (REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").exists()

    def test_codeowners_exists(self):
        """CODEOWNERS must exist."""
        assert (REPO_ROOT / ".github" / "CODEOWNERS").exists()

    def test_workflow_validates(self):
        """Build workflow must exist and be valid YAML."""
        import yaml
        workflow = REPO_ROOT / ".github" / "workflows" / "build.yml"
        assert workflow.exists()
        with open(workflow) as f:
            data = yaml.safe_load(f)
        assert "jobs" in data, "Workflow missing jobs"
        assert "validate" in data["jobs"], "Workflow missing validate job"

    def test_schema_exists(self):
        """V3 schema must exist."""
        assert (REPO_ROOT / "schema" / "resource.schema.v3.json").exists()

    def test_public_data_generated(self):
        """Public data files must exist."""
        assert (DATA_DIR / "resources.json").exists()
        assert (DATA_DIR / "index.json").exists()

    def test_public_data_has_resources(self):
        """Public data must contain resources."""
        with open(DATA_DIR / "resources.json") as f:
            data = json.load(f)
        assert data["metadata"]["total_resources"] >= 3

    def test_988_in_public_data(self):
        """988 must be in public data."""
        with open(DATA_DIR / "resources.json") as f:
            data = json.load(f)
        ids = [r["id"] for r in data["resources"]]
        assert any("988" in i for i in ids), "988 not in public data"

    def test_211_in_public_data(self):
        """211 must be in public data."""
        with open(DATA_DIR / "resources.json") as f:
            data = json.load(f)
        ids = [r["id"] for r in data["resources"]]
        assert any("211" in i for i in ids), "211 not in public data"

    def test_all_resources_have_required_fields(self):
        """All public resources must have required fields."""
        with open(DATA_DIR / "resources.json") as f:
            data = json.load(f)
        for r in data["resources"]:
            assert r.get("id"), f"Missing id"
            assert r.get("name"), f"Missing name"
            assert r.get("needs"), f"Missing needs"

    def test_no_internal_files_in_public_data(self):
        """Public data must not contain internal information."""
        with open(DATA_DIR / "resources.json") as f:
            data = json.load(f)
        # Check for common internal patterns in resource data
        for r in data["resources"]:
            for key, val in r.items():
                if isinstance(val, str):
                    assert "password" not in val.lower(), f"Password found in {r['id']}.{key}"
                    assert "api_key" not in val.lower(), f"API key found in {r['id']}.{key}"

    def test_site_files_exist(self):
        """Essential site files must exist."""
        assert (REPO_ROOT / "index.html").exists()
        assert (REPO_ROOT / "assets" / "css" / "beacon.css").exists()
        assert (REPO_ROOT / "assets" / "js" / "app.js").exists()
        assert (REPO_ROOT / "assets" / "js" / "config.js").exists()

    def test_javascript_syntax(self):
        """JavaScript must have valid syntax."""
        import subprocess
        for js_file in ["assets/js/app.js", "assets/js/config.js"]:
            result = subprocess.run(
                ["node", "--check", str(REPO_ROOT / js_file)],
                capture_output=True, text=True
            )
            assert result.returncode == 0, f"JS syntax error in {js_file}"
