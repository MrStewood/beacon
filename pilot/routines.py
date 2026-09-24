#!/usr/bin/env python3
"""Deterministic manual pilot routines for Beacon.

Usage:
    python pilot/routines.py safety
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT_DIR = REPO_ROOT / "pilot"
CONFIG_PATH = PILOT_DIR / "manual_pilot.json"
CASES_DIR = PILOT_DIR / "cases"

EXPECTED_OFF_SWITCHES = {
    "agent_autostart",
    "heartbeats_enabled",
    "routines_enabled",
    "webhook_execution_enabled",
    "auto_assignment_enabled",
    "auto_retry_enabled",
    "auto_state_transitions",
    "discovery_enabled",
    "github_write_enabled",
    "pr_creation_enabled",
    "auto_merge_enabled",
    "production_deployment_enabled",
    "automatic_rollback_enabled",
    "geographic_expansion_enabled",
    "bulk_import_enabled",
}

EXPECTED_TRUE_LIMITS = {
    "no_confidential_address",
    "no_closure_or_deletion",
    "no_geographic_expansion",
    "no_bulk_discovery",
    "no_agent_self_modification",
}

VALID_STATES = {
    "received", "triage-ready", "triage-active", "triage-complete",
    "duplicate-check-ready", "duplicate-check-active", "duplicate-check-complete",
    "research-a-ready", "research-a-active", "research-a-complete",
    "research-b-ready", "research-b-active", "research-b-complete",
    "comparison-ready", "comparison-complete",
    "verification-a-ready", "verification-a-active", "verification-a-complete",
    "verification-b-ready", "verification-b-active", "verification-b-complete",
    "policy-gate-ready", "policy-gate-active",
    "correction-required", "quarantined", "publication-authorized",
    "artifact-generation-ready", "artifact-generated",
    "yaml-generation-ready", "yaml-generated",
    "local-validation-ready", "local-validation-complete",
    "pr-creation-ready", "draft-pr-open",
    "github-ci-active", "github-ci-failed", "github-ci-passed",
    "merge-ready", "merged",
    "deployment-active", "deployment-complete",
    "production-verification-active", "production-verification-failed", "post-deployment-verified",
    "monitoring",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def run_command(args: list[str]) -> tuple[bool, str]:
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.returncode == 0, result.stdout.strip()


def check_config(errors: list[str]) -> dict[str, Any] | None:
    if not CONFIG_PATH.exists():
        fail(errors, f"missing config: {CONFIG_PATH.relative_to(REPO_ROOT)}")
        return None

    try:
        config = load_json(CONFIG_PATH)
    except Exception as exc:  # noqa: BLE001 - exact parse error is reported to operator.
        fail(errors, f"invalid JSON in {CONFIG_PATH.relative_to(REPO_ROOT)}: {exc}")
        return None

    if config.get("mode") != "manual_pilot":
        fail(errors, f"mode is {config.get('mode')!r}, expected 'manual_pilot'")

    if config.get("current_execution_level") != "simulation":
        fail(errors, "current_execution_level is "
             f"{config.get('current_execution_level')!r}, expected 'simulation'")

    switches = config.get("safety_switches", {})
    for key in sorted(EXPECTED_OFF_SWITCHES):
        if key not in switches:
            fail(errors, f"missing safety switch: {key}")
        elif switches[key] is not False:
            fail(errors, f"safety switch {key} is {switches[key]!r}, expected false")

    limits = config.get("pilot_limits", {})
    if limits.get("max_active_cases") != 1:
        fail(errors, f"max_active_cases is {limits.get('max_active_cases')!r}, expected 1")
    if limits.get("max_agents_running") != 1:
        fail(errors, f"max_agents_running is {limits.get('max_agents_running')!r}, expected 1")
    if limits.get("allowed_risk_tiers") != ["low"]:
        fail(errors, f"allowed_risk_tiers is {limits.get('allowed_risk_tiers')!r}, expected ['low']")
    for key in sorted(EXPECTED_TRUE_LIMITS):
        if limits.get(key) is not True:
            fail(errors, f"pilot limit {key} is {limits.get(key)!r}, expected true")

    geography = limits.get("allowed_geography", {})
    if "Laurel" not in geography.get("counties", []):
        fail(errors, "allowed_geography.counties must include 'Laurel'")
    if "KY" not in geography.get("states", []):
        fail(errors, "allowed_geography.states must include 'KY'")

    return config


def check_cases(errors: list[str], max_active_cases: int) -> tuple[int, int]:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    case_count = 0
    active_count = 0
    seen_ids: set[str] = set()

    for path in sorted(CASES_DIR.glob("*.json")):
        case_count += 1
        try:
            case = load_json(path)
        except Exception as exc:  # noqa: BLE001 - exact parse error is reported to operator.
            fail(errors, f"invalid case JSON {path.relative_to(REPO_ROOT)}: {exc}")
            continue

        case_id = case.get("case_id")
        state = case.get("state")
        if not case_id:
            fail(errors, f"{path.relative_to(REPO_ROOT)} missing case_id")
        elif case_id in seen_ids:
            fail(errors, f"duplicate case_id: {case_id}")
        else:
            seen_ids.add(case_id)

        if state not in VALID_STATES:
            fail(errors, f"{path.relative_to(REPO_ROOT)} has invalid state {state!r}")
        elif str(state).endswith("-active"):
            active_count += 1

    if active_count > max_active_cases:
        fail(errors, f"{active_count} active cases found; max_active_cases={max_active_cases}")

    return case_count, active_count


def cmd_safety(_: list[str]) -> int:
    errors: list[str] = []
    config = check_config(errors)
    max_active_cases = 1
    if config:
        max_active_cases = config.get("pilot_limits", {}).get("max_active_cases", 1)

    case_count, active_count = check_cases(errors, max_active_cases)

    status_ok, status_output = run_command([sys.executable, "pilot/stage_controller.py", "status-all"])
    if not status_ok:
        fail(errors, "stage_controller status-all failed:\n" + status_output)

    build_ok, build_output = run_command([sys.executable, "scripts/build.py", "--strict"])
    if not build_ok:
        fail(errors, "build failed:\n" + build_output)

    tests_ok, tests_output = run_command([sys.executable, "-m", "pytest", "tests/", "-q"])
    if not tests_ok:
        fail(errors, "tests failed:\n" + tests_output)

    if errors:
        print("ERROR: Beacon manual pilot safety check failed")
        for error in errors:
            print(f"- {error}")
        return 1

    resources = "unknown"
    data_path = REPO_ROOT / "data" / "resources.json"
    if data_path.exists():
        try:
            resources = str(len(load_json(data_path).get("resources", [])))
        except Exception:  # noqa: BLE001 - not safety critical after build passed.
            resources = "unknown"

    print("OK: Beacon manual pilot safety check passed")
    print("mode=manual_pilot")
    print("execution_level=simulation")
    print(f"cases={case_count}")
    print(f"active_cases={active_count}")
    print(f"resources={resources}")
    print("build=passed")
    print("tests=passed")
    return 0


COMMANDS = {
    "safety": cmd_safety,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"Commands: {', '.join(COMMANDS)}")
        sys.exit(2)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]))


if __name__ == "__main__":
    main()
