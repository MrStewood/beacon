#!/usr/bin/env python3
"""Manual stage controller for Beacon pilot.

Advances one case by exactly one permitted transition.
Enforces preconditions, prevents skipping, records transitions.

Usage:
    python pilot/stage_controller.py advance <case-id> <expected-state> <next-state>
    python pilot/stage_controller.py status [case-id]
    python pilot/stage_controller.py pause-all
    python pilot/stage_controller.py status-all
    python pilot/stage_controller.py reset <case-id> <target-state>
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PILOT_DIR = REPO_ROOT / "pilot"
CASES_DIR = PILOT_DIR / "cases"
CONFIG_PATH = PILOT_DIR / "manual_pilot.json"
AUDIT_DIR = PILOT_DIR / "audit"

# 41-stage workflow from the spec
STATES = [
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
]

# Legal transitions: current -> set of allowed next states
TRANSITIONS: dict[str, set[str]] = {}
_ordered = STATES
for i, s in enumerate(_ordered):
    if s in ("correction-required", "quarantined", "publication-authorized"):
        # Branch points: from policy-gate-active
        continue
    if s in ("github-ci-failed", "production-verification-failed"):
        # Failure endpoints
        continue
    if i + 1 < len(_ordered):
        nxt = _ordered[i + 1]
        # Skip over branch-point placeholders
        if nxt not in ("correction-required", "quarantined", "publication-authorized"):
            TRANSITIONS.setdefault(s, set()).add(nxt)

# From policy-gate-active, three possible outcomes
TRANSITIONS["policy-gate-active"] = {"correction-required", "quarantined", "publication-authorized"}
# From github-ci-active, two outcomes
TRANSITIONS["github-ci-active"] = {"github-ci-failed", "github-ci-passed"}
# From production-verification-active, two outcomes
TRANSITIONS["production-verification-active"] = {"production-verification-failed", "post-deployment-verified"}
# Failure states can restart from specific earlier states
TRANSITIONS["correction-required"] = {"triage-ready", "research-a-ready", "verification-a-ready"}
TRANSITIONS["quarantined"] = set()  # dead end
TRANSITIONS["github-ci-failed"] = {"pr-creation-ready"}
TRANSITIONS["production-verification-failed"] = {"deployment-active"}

# Which agent role owns each active stage
STAGE_AGENT: dict[str, str] = {
    "triage-active": "intake",
    "duplicate-check-active": "intake",
    "research-a-active": "research-a",
    "research-b-active": "research-b",
    "comparison-active": "evidence-comparator",
    "verification-a-active": "verifier",
    "verification-b-active": "second-verifier",
    "policy-gate-active": "policy-engine",
    "artifact-generation-active": "director",
    "yaml-generation-active": "publisher",
    "local-validation-active": "ci",
    "pr-creation-active": "publisher",
    "github-ci-active": "ci",
    "merge-active": "ci",
    "deployment-active": "deployment-monitor",
    "production-verification-active": "deployment-monitor",
}


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def load_case(case_id: str) -> dict | None:
    path = CASES_DIR / f"{case_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_case(case: dict) -> None:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    path = CASES_DIR / f"{case['case_id']}.json"
    path.write_text(json.dumps(case, indent=2) + "\n")


def audit_transition(case_id: str, from_state: str, to_state: str, trigger: str, note: str = "") -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "case_id": case_id,
        "from_state": from_state,
        "to_state": to_state,
        "triggered_by": trigger,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
    }
    log_path = AUDIT_DIR / f"{case_id}.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def check_switches(config: dict, required: list[str] | None = None) -> list[str]:
    """Return list of disabled switches that block the requested action."""
    switches = config.get("safety_switches", {})
    blocked = []
    for key, val in switches.items():
        if val is False and (required is None or key in required):
            blocked.append(key)
    return blocked


def cmd_advance(args: list[str]) -> int:
    if len(args) < 3:
        print("Usage: advance <case-id> <expected-current-state> <next-state>")
        return 1

    case_id, expected, target = args[0], args[1], args[2]
    config = load_config()

    # Check mode
    if config.get("mode") != "manual_pilot":
        print(f"ERROR: mode is '{config.get('mode')}', not 'manual_pilot'. Aborting.")
        return 1

    # Check safety switches
    if not config["safety_switches"].get("auto_state_transitions", False):
        # Manual mode: transitions are only allowed via this controller
        pass  # That's the point — we ARE the controller

    # Load case
    case = load_case(case_id)
    if case is None:
        print(f"ERROR: case '{case_id}' not found")
        return 1

    # Check current state
    current = case.get("state")
    if current != expected:
        print(f"ERROR: case '{case_id}' is in state '{current}', not '{expected}'")
        return 1

    # Check transition is legal
    allowed = TRANSITIONS.get(current, set())
    if target not in allowed:
        print(f"ERROR: transition '{current}' -> '{target}' is not legal.")
        print(f"  Allowed next states: {sorted(allowed) if allowed else '(none — dead end)'}")
        return 1

    # Check pilot limits
    limits = config.get("pilot_limits", {})
    max_cases = limits.get("max_active_cases", 1)
    if max_cases:
        active = sum(
            1 for c in CASES_DIR.glob("*.json")
            if json.loads(c.read_text()).get("state", "").endswith("-active")
        )
        if active >= max_cases and target.endswith("-active"):
            print(f"ERROR: {active} case(s) already active (max {max_cases}). Finish current stage first.")
            return 1

    # Advance
    case["state"] = target
    case["updated_at"] = datetime.now(timezone.utc).isoformat()
    case.setdefault("history", []).append({
        "from": current,
        "to": target,
        "triggered_at": case["updated_at"],
    })
    save_case(case)
    audit_transition(case_id, current, target, "operator")

    print(f"OK: {case_id} advanced from '{current}' to '{target}'")

    # Print checkpoint hint
    if target.endswith("-active"):
        agent = STAGE_AGENT.get(target, "unknown")
        print(f"  Next: invoke agent role '{agent}' for this case")
    elif target.endswith("-complete") or target in ("comparison-complete",):
        print(f"  Next: inspect results, then advance to next '-ready' state")
    elif target == "monitoring":
        print(f"  Case is in monitoring. Pipeline complete for this resource.")

    return 0


def cmd_status(args: list[str]) -> int:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    cases = sorted(CASES_DIR.glob("*.json"))
    if not cases:
        print("No cases found.")
        return 0

    for p in cases:
        case = json.loads(p.read_text())
        cid = case.get("case_id", p.stem)
        state = case.get("state", "unknown")
        name = case.get("lead", {}).get("name", "unnamed")
        updated = case.get("updated_at", "unknown")
        print(f"  {cid}: state={state} name='{name}' updated={updated}")
    return 0


def cmd_status_all(args: list[str]) -> int:
    config = load_config()
    print("=== Beacon Manual Pilot Status ===")
    print(f"Mode: {config.get('mode', 'unknown')}")
    print(f"Execution level: {config.get('current_execution_level', 'unknown')}")
    print()

    print("Safety switches:")
    for key, val in config.get("safety_switches", {}).items():
        status = "ON" if val else "OFF"
        print(f"  {key}: {status}")
    print()

    print("Pilot limits:")
    for key, val in config.get("pilot_limits", {}).items():
        print(f"  {key}: {val}")
    print()

    print("Cases:")
    cmd_status([])
    print()

    # Check Paperclip agent states (best effort)
    print("Note: Paperclip agent states must be checked separately via:")
    print("  docker exec paperclip /usr/local/bin/paperclipai agent list -C 76e932b7-637f-4341-b40e-7e9bb18a27b0")
    return 0


def cmd_pause_all(args: list[str]) -> int:
    config = load_config()
    config["mode"] = "manual_pilot"
    for key in config["safety_switches"]:
        config["safety_switches"][key] = False
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")
    print("All safety switches set to OFF. All automation disabled.")
    print("Agents must be paused separately via Paperclip CLI:")
    print("  docker exec paperclip /usr/local/bin/paperclipai agent pause <agent-id>")
    return 0


def cmd_reset(args: list[str]) -> int:
    if len(args) < 2:
        print("Usage: reset <case-id> <target-state>")
        return 1
    case_id, target = args[0], args[1]
    if target not in STATES:
        print(f"ERROR: '{target}' is not a valid state")
        return 1

    case = load_case(case_id)
    if case is None:
        print(f"ERROR: case '{case_id}' not found")
        return 1

    old_state = case.get("state")
    case["state"] = target
    case["updated_at"] = datetime.now(timezone.utc).isoformat()
    case.setdefault("history", []).append({
        "from": old_state,
        "to": target,
        "triggered_at": case["updated_at"],
        "note": "operator reset",
    })
    save_case(case)
    audit_transition(case_id, old_state, target, "operator", "reset")
    print(f"OK: {case_id} reset from '{old_state}' to '{target}'")
    return 0


COMMANDS = {
    "advance": cmd_advance,
    "status": cmd_status,
    "status-all": cmd_status_all,
    "pause-all": cmd_pause_all,
    "reset": cmd_reset,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"Commands: {', '.join(COMMANDS.keys())}")
        sys.exit(2)
    cmd = sys.argv[1]
    sys.exit(COMMANDS[cmd](sys.argv[2:]))


if __name__ == "__main__":
    main()
