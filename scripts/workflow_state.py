"""Enforced state machine for the Beacon lead-to-published-record pipeline.

Every candidate carries a `workflow_state`. Agents may only move a candidate
along edges defined in TRANSITIONS, and only if the acting role is permitted
for that edge (ROLE_FOR_TRANSITION) and — for edges where the spec forbids an
agent working on its own prior output — the actor differs from the actor of
the state being left (see `transition`).

This is intentionally strict: skipping, combining, or reordering states is a
hard error, not a lint warning. Nothing here is advisory.
"""

from __future__ import annotations

from dataclasses import dataclass

STATES = [
    "lead-received",
    "intake-classified",
    "duplicate-checked",
    "research-a-locked",
    "research-b-locked",
    "evidence-compared",
    "verified",
    "risk-verification-complete",
    "policy-checked",
    "trust-scored",
    "decision-signed",
    "yaml-created",
    "pr-opened",
    "ci-passed",
    "merged",
    "deployed",
    "production-verified",
    "monitoring",
    "reverification-due",
    # Terminal/exception states, reachable from any working state:
    "quarantined",
    "temporarily-suppressed",
    "rejected",
    "system-paused",
]

# Linear happy-path edges (spec: "Required workflow", steps 1-19).
_HAPPY_PATH = [
    ("lead-received", "intake-classified"),
    ("intake-classified", "duplicate-checked"),
    ("duplicate-checked", "research-a-locked"),
    ("research-a-locked", "research-b-locked"),
    ("research-b-locked", "evidence-compared"),
    ("evidence-compared", "verified"),
    ("verified", "risk-verification-complete"),
    ("risk-verification-complete", "policy-checked"),
    ("policy-checked", "trust-scored"),
    ("trust-scored", "decision-signed"),
    ("decision-signed", "yaml-created"),
    ("yaml-created", "pr-opened"),
    ("pr-opened", "ci-passed"),
    ("ci-passed", "merged"),
    ("merged", "deployed"),
    ("deployed", "production-verified"),
    ("production-verified", "monitoring"),
    ("monitoring", "reverification-due"),
    ("reverification-due", "duplicate-checked"),  # scheduled reverification re-enters the pipeline
]

# Exception exits — any working state may fail closed into one of these.
_EXCEPTION_TARGETS = {"quarantined", "temporarily-suppressed", "rejected", "system-paused"}
_WORKING_STATES = [s for s in STATES if s not in _EXCEPTION_TARGETS]

TRANSITIONS: dict[str, set[str]] = {s: set() for s in STATES}
for a, b in _HAPPY_PATH:
    TRANSITIONS[a].add(b)
for s in _WORKING_STATES:
    TRANSITIONS[s] |= _EXCEPTION_TARGETS
# A production rollback returns a live record to suppressed, never silently to draft.
TRANSITIONS["production-verified"].add("temporarily-suppressed")
TRANSITIONS["monitoring"].add("temporarily-suppressed")
# Quarantine/suppression/rejection are dead ends for this candidate id; a fresh lead is required.
# system-paused blocks the whole pipeline until a human clears it (not modeled as an outgoing edge).

# Which role may perform each transition. A role NOT listed here may never make that transition.
ROLE_FOR_TRANSITION: dict[tuple[str, str], set[str]] = {
    ("lead-received", "intake-classified"): {"intake"},
    ("intake-classified", "duplicate-checked"): {"intake"},
    ("duplicate-checked", "research-a-locked"): {"research-a"},
    ("research-a-locked", "research-b-locked"): {"research-b"},
    ("research-b-locked", "evidence-compared"): {"evidence-comparator"},
    ("evidence-compared", "verified"): {"verifier"},
    ("verified", "risk-verification-complete"): {"verifier", "second-verifier"},
    ("risk-verification-complete", "policy-checked"): {"policy-engine"},
    ("policy-checked", "trust-scored"): {"scoring-engine"},
    ("trust-scored", "decision-signed"): {"director"},
    ("decision-signed", "yaml-created"): {"publisher"},
    ("yaml-created", "pr-opened"): {"publisher"},
    ("pr-opened", "ci-passed"): {"ci"},
    ("ci-passed", "merged"): {"ci"},
    ("merged", "deployed"): {"ci"},
    ("deployed", "production-verified"): {"deployment-monitor"},
    ("production-verified", "monitoring"): {"deployment-monitor"},
    ("monitoring", "reverification-due"): {"scheduler"},
    ("reverification-due", "duplicate-checked"): {"reverification-agent"},
}

# Roles that must differ from a preceding role for a transition to be legal
# (spec: "No agent may research, verify, approve, publish, and merge the same record").
DISTINCT_FROM: dict[str, set[str]] = {
    "research-b": {"research-a"},
    "verifier": {"research-a", "research-b"},
    "second-verifier": {"research-a", "research-b", "verifier"},
    "director": {"research-a", "research-b", "verifier", "second-verifier"},
    "publisher": {"research-a", "research-b", "verifier", "second-verifier", "director"},
}


class IllegalTransition(Exception):
    pass


@dataclass
class Actor:
    agent_id: str
    role: str


def transition(current_state: str, target_state: str, actor: Actor, prior_actors: dict[str, Actor]) -> None:
    """Validate a proposed state transition. Raises IllegalTransition on any violation.

    `prior_actors` maps role -> Actor for every role that has already acted on this
    candidate (e.g. {"research-a": Actor("agent-1", "research-a"), ...}).
    """
    if current_state not in STATES:
        raise IllegalTransition(f"unknown state '{current_state}'")
    if target_state not in TRANSITIONS.get(current_state, set()):
        raise IllegalTransition(f"'{current_state}' -> '{target_state}' is not a legal edge")

    allowed_roles = ROLE_FOR_TRANSITION.get((current_state, target_state))
    if allowed_roles is not None and actor.role not in allowed_roles:
        raise IllegalTransition(
            f"role '{actor.role}' may not perform transition '{current_state}' -> '{target_state}' "
            f"(allowed: {sorted(allowed_roles)})"
        )

    forbidden_roles = DISTINCT_FROM.get(actor.role, set())
    for prior_role, prior_actor in prior_actors.items():
        if prior_role in forbidden_roles and prior_actor.agent_id == actor.agent_id:
            raise IllegalTransition(
                f"agent '{actor.agent_id}' already acted as '{prior_role}' on this candidate; "
                f"cannot also act as '{actor.role}' (separation of duties)"
            )
