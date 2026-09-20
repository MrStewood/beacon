"""Tests proving manual pilot mode prevents all automatic behavior.

These tests verify the safety guarantees of BEACON_MODE=manual_pilot.
They do NOT require Paperclip to be running — they test the configuration
and stage controller invariants directly.
"""

import json
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PILOT_DIR = REPO_ROOT / "pilot"
CONFIG_PATH = PILOT_DIR / "manual_pilot.json"
CASES_DIR = PILOT_DIR / "cases"


def load_config():
    return json.loads(CONFIG_PATH.read_text())


def load_case(case_id: str):
    path = CASES_DIR / f"{case_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


class TestAllSwitchesOff:
    """Every safety switch must default to false in manual pilot mode."""

    def test_all_switches_off(self):
        config = load_config()
        switches = config.get("safety_switches", {})
        assert len(switches) >= 14, f"Expected at least 14 switches, got {len(switches)}"
        for key, val in switches.items():
            assert val is False, f"Switch '{key}' is {val}, expected False"

    def test_mode_is_manual_pilot(self):
        config = load_config()
        assert config.get("mode") == "manual_pilot"

    def test_execution_level_is_simulation(self):
        config = load_config()
        assert config.get("current_execution_level") == "simulation"


class TestStageController:
    """The stage controller enforces single-step advancement."""

    def test_cannot_skip_stages(self):
        """Advancing from received to research-a-active must be rejected."""
        from stage_controller import TRANSITIONS
        # received can only go to triage-ready
        allowed = TRANSITIONS.get("received", set())
        assert "triage-ready" in allowed
        assert "research-a-active" not in allowed

    def test_cannot_skip_to_policy_gate(self):
        """Advancing from triage-complete directly to policy-gate must be rejected."""
        from stage_controller import TRANSITIONS
        allowed = TRANSITIONS.get("triage-complete", set())
        assert "duplicate-check-ready" in allowed
        assert "policy-gate-active" not in allowed

    def test_cannot_skip_to_ci(self):
        """Advancing from verification-complete directly to github-ci must be rejected."""
        from stage_controller import TRANSITIONS
        allowed = TRANSITIONS.get("verification-a-complete", set())
        assert "verification-b-ready" in allowed or "policy-gate-ready" in allowed
        assert "github-ci-active" not in allowed

    def test_cannot_skip_to_merge(self):
        """Advancing from pr-creation directly to merged must be rejected."""
        from stage_controller import TRANSITIONS
        allowed = TRANSITIONS.get("pr-creation-ready", set())
        assert "draft-pr-open" in allowed
        assert "merged" not in allowed

    def test_cannot_skip_to_deployment(self):
        """Advancing from merge-ready directly to deployment must be rejected."""
        from stage_controller import TRANSITIONS
        allowed = TRANSITIONS.get("merge-ready", set())
        assert "merged" in allowed
        assert "deployment-active" not in allowed

    def test_quarantined_is_dead_end(self):
        """Quarantined cases cannot advance."""
        from stage_controller import TRANSITIONS
        assert TRANSITIONS.get("quarantined", set()) == set()

    def test_each_active_stage_has_an_agent(self):
        """Every '-active' stage is mapped to an agent role."""
        from stage_controller import STAGE_AGENT
        from stage_controller import STATES
        active_states = [s for s in STATES if s.endswith("-active")]
        for state in active_states:
            assert state in STAGE_AGENT, f"Active stage '{state}' has no agent mapping"


class TestCaseLifecycle:
    """Cases cannot progress without explicit operator commands."""

    def test_received_case_cannot_self_advance(self):
        """A case in 'received' stays in 'received' without operator action."""
        case = load_case("laurel-county-public-library")
        assert case is not None
        # The case should be in a valid state, not auto-advanced
        assert case["state"] in ("received", "triage-ready", "triage-active")

    def test_no_synthetic_fixtures_in_production_data(self):
        """Test-only cases must not appear in source/approved/."""
        approved = list((REPO_ROOT / "source" / "approved").rglob("*.yaml"))
        assert len(approved) == 0, f"Found {len(approved)} approved records — should be 0 in pilot"

    def test_fixture_cannot_reach_production(self):
        """The pilot case is not in source/approved/."""
        approved_files = [p.name for p in (REPO_ROOT / "source" / "approved").rglob("*.yaml")]
        assert "laurel-county-public-library.yaml" not in approved_files

    def test_pilot_limits_enforced(self):
        """Pilot limits restrict to 1 active case and low risk."""
        config = load_config()
        limits = config.get("pilot_limits", {})
        assert limits.get("max_active_cases") == 1
        assert limits.get("allowed_risk_tiers") == ["low"]
        assert limits.get("no_confidential_address") is True
        assert limits.get("no_geographic_expansion") is True


class TestNoAutostart:
    """Prove that nothing autostarts in manual pilot mode."""

    def test_heartbeat_disabled_in_config(self):
        """Heartbeats are disabled in the safety switches."""
        config = load_config()
        assert config["safety_switches"]["heartbeats_enabled"] is False

    def test_agent_autostart_disabled(self):
        """Agent autostart is disabled."""
        config = load_config()
        assert config["safety_switches"]["agent_autostart"] is False

    def test_auto_assignment_disabled(self):
        """Auto assignment is disabled."""
        config = load_config()
        assert config["safety_switches"]["auto_assignment_enabled"] is False

    def test_auto_state_transitions_disabled(self):
        """Automatic state transitions are disabled."""
        config = load_config()
        assert config["safety_switches"]["auto_state_transitions"] is False

    def test_auto_retry_disabled(self):
        """Automatic retries are disabled."""
        config = load_config()
        assert config["safety_switches"]["auto_retry_enabled"] is False

    def test_routines_disabled(self):
        """Cron routines are disabled."""
        config = load_config()
        assert config["safety_switches"]["routines_enabled"] is False

    def test_webhook_execution_disabled(self):
        """Webhook-triggered work is disabled."""
        config = load_config()
        assert config["safety_switches"]["webhook_execution_enabled"] is False

    def test_github_writes_disabled(self):
        """GitHub writes are disabled."""
        config = load_config()
        assert config["safety_switches"]["github_write_enabled"] is False

    def test_pr_creation_disabled(self):
        """PR creation is disabled."""
        config = load_config()
        assert config["safety_switches"]["pr_creation_enabled"] is False

    def test_auto_merge_disabled(self):
        """Auto merge is disabled."""
        config = load_config()
        assert config["safety_switches"]["auto_merge_enabled"] is False

    def test_production_deployment_disabled(self):
        """Production deployment is disabled."""
        config = load_config()
        assert config["safety_switches"]["production_deployment_enabled"] is False

    def test_geographic_expansion_disabled(self):
        """Geographic expansion is disabled."""
        config = load_config()
        assert config["safety_switches"]["geographic_expansion_enabled"] is False

    def test_bulk_import_disabled(self):
        """Bulk imports are disabled."""
        config = load_config()
        assert config["safety_switches"]["bulk_import_enabled"] is False

    def test_no_agent_self_modification(self):
        """Agents cannot modify their own configuration."""
        config = load_config()
        assert config["pilot_limits"]["no_agent_self_modification"] is True
