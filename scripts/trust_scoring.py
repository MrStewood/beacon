"""Deterministic claim- and record-level trust scoring for Beacon candidates.

This module is the enforcement core described in TRUST_SCORING.md. It contains
no LLM calls and no agent judgment: given a candidate's claims and evidence it
always produces the same score, the same caps, and the same decision. GitHub
CI re-runs this module against the committed candidate file and rejects any
PR whose decision artifact does not match a fresh recomputation.

Nothing in here is a probability that information is true. It is a policy-
based evidence-quality score (see spec section "Trust score").
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

POLICY_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Source tiers (spec section "Source classifications")
# ---------------------------------------------------------------------------

TIER_AUTHORITY = {
    "A": 35,  # official government program page/license db/org website/API/closure notice
    "B": 30,  # government-maintained directory, accredited statewide directory
    "C": 24,  # established independent directory (211, nonprofit, professional assoc)
    "D": 17,  # local gov partner page, community foundation, news, referral page
    "E": 8,   # unverified submission / community report / user correction
    "F": 2,   # search snippet, social post, aggregated listing, AI summary, scrape
}

# Freshness windows in days, keyed by claim.freshness_class (spec: "Freshness: 0-15")
FRESHNESS_WINDOWS = {
    "operating_status": (90, 180),      # (preferred, max)
    "crisis": (30, 60),
    "hours_phone": (90, 180),
    "eligibility": (180, 365),
    "address": (180, 365),
    "service_description": (365, 730),
    "stable_program_identity": (365, 730),
}

# Record trust score weighting (spec: "Record trust score")
ESSENTIAL_WEIGHT = 0.70
MATERIAL_WEIGHT = 0.30

# Publication thresholds by risk tier (spec: "Publication thresholds")
RISK_THRESHOLDS = {
    "low": {"record_min": 80, "essential_claim_min": 75},
    "elevated": {"record_min": 90, "essential_claim_min": 85},
    "critical": {"record_min": 95, "essential_claim_min": 90},
}

# Conflict penalties (spec: "Conflict penalties") — (min, max) inclusive ranges
CONFLICT_PENALTIES = {
    "wording": (0, 5),
    "nonessential-detail": (5, 10),
    "hours-eligibility-coverage": (20, 20),
    "phone-address-status": (30, 30),
    "closure-evidence": (40, 40),
    "privacy-safety": (0, 0),  # not a score penalty: forces eligibility=False outright
}


class FabricationDetected(Exception):
    """Raised when evidence is flagged as fabricated or manipulated. Triggers an incident."""


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# Claim-level scoring
# ---------------------------------------------------------------------------

@dataclass
class ClaimScoreResult:
    claim_id: str
    score: int
    status: str
    breakdown: dict[str, Any]
    caps_applied: list[str] = field(default_factory=list)
    incident: bool = False


def _distinct_chains(evidence: list[dict], supports: bool | None = None) -> set[str]:
    items = evidence if supports is None else [e for e in evidence if e.get("supports") == supports]
    return {e["chain_id"] for e in items}


def _source_authority(evidence: list[dict]) -> tuple[int, dict | None]:
    """Strongest applicable supporting source's authority value and the evidence item itself."""
    supporting = [e for e in evidence if e.get("supports")]
    if not supporting:
        return 0, None
    best = max(supporting, key=lambda e: TIER_AUTHORITY.get(e["tier"], 0))
    return TIER_AUTHORITY.get(best["tier"], 0), best


def _directness(evidence: list[dict]) -> int:
    supporting = [e for e in evidence if e.get("supports")]
    if not supporting:
        return 0
    return max(e.get("directness", 0) for e in supporting)


def _freshness(claim: dict, primary: dict | None, today: date) -> int:
    if primary is None:
        return 0
    window = FRESHNESS_WINDOWS.get(claim["freshness_class"])
    if window is None:
        return 0
    preferred, maximum = window
    ref_date = _parse_date(primary.get("published_or_updated_at")) or _parse_date(primary.get("retrieved_at"))
    if ref_date is None:
        return 5  # date unclear
    age_days = (today - ref_date).days
    if age_days < 0:
        age_days = 0
    if age_days <= preferred:
        return 15
    if age_days <= maximum:
        return 10
    if age_days <= maximum * 1.25:
        return 5
    return 0


def _corroboration(evidence: list[dict]) -> tuple[int, bool]:
    """Returns (score, independence_known_for_all_corroborating_chains)."""
    supporting = [e for e in evidence if e.get("supports")]
    chains = _distinct_chains(supporting)
    if len(chains) < 2:
        return 0, True
    independence_known = all(
        e.get("chain_independence_known", False)
        for e in supporting
        if e["chain_id"] in chains
    )
    if independence_known:
        return 15, True
    return 8, False


def _evidence_chain_independence(evidence: list[dict]) -> int:
    supporting = [e for e in evidence if e.get("supports")]
    chains = _distinct_chains(supporting)
    if len(chains) < 2:
        return 0
    known = [e.get("chain_independence_known", False) for e in supporting]
    if all(known):
        return 10
    if any(known):
        return 5
    return 5  # multiple chains claimed but independence unverified -> partial


def _retrieval_integrity(primary: dict | None) -> int:
    if primary is None:
        return 0
    if not primary.get("reopenable", True):
        return 0
    has_timestamp = bool(primary.get("retrieved_at"))
    preserved = bool(primary.get("content_hash") or primary.get("archived_snapshot"))
    if has_timestamp and preserved:
        return 5
    if has_timestamp:
        return 3
    return 0


def score_claim(claim: dict, today: date | None = None) -> ClaimScoreResult:
    today = today or date.today()
    evidence = claim.get("evidence", [])

    for e in evidence:
        if e.get("fabrication_suspected"):
            return ClaimScoreResult(
                claim_id=claim["claim_id"], score=0, status="unsafe-to-publish",
                breakdown={"reason": "fabrication_suspected", "evidence_id": e["id"]},
                caps_applied=["fabrication"], incident=True,
            )

    authority, primary = _source_authority(evidence)
    directness = _directness(evidence)
    freshness = _freshness(claim, primary, today)
    corroboration, independence_known = _corroboration(evidence)
    chain_independence = _evidence_chain_independence(evidence)
    retrieval = _retrieval_integrity(primary)

    raw = authority + directness + freshness + corroboration + chain_independence + retrieval
    raw = min(raw, 100)

    breakdown = {
        "source_authority": authority,
        "directness": directness,
        "freshness": freshness,
        "independent_corroboration": corroboration,
        "evidence_chain_independence": chain_independence,
        "retrieval_integrity": retrieval,
        "raw_total": raw,
    }

    contradicting = [e for e in evidence if e.get("supports") is False]
    supporting = [e for e in evidence if e.get("supports")]
    tiers_used = {e["tier"] for e in supporting}

    caps: list[tuple[int, str]] = []
    if len(supporting) == 1:
        caps.append((79, "single-evidence-source"))
    if supporting and tiers_used.issubset({"D", "E", "F"}) and not tiers_used.issubset({"E"}) and not tiers_used.issubset({"F"}):
        caps.append((69, "only-unofficial-secondary-sources"))
    if supporting and tiers_used == {"E"}:
        caps.append((39, "only-unverified-submissions"))
    if supporting and tiers_used.issubset({"F"}):
        caps.append((25, "only-discovery-sources"))
    if corroboration == 8 and not independence_known:
        caps.append((74, "source-independence-unknown"))
    if freshness == 0 and primary is not None:
        caps.append((49, "stale-source"))
    unresolved_conflict = bool(contradicting) and not claim.get("_conflict_resolved", False)
    if unresolved_conflict:
        caps.append((49, "unresolved-material-conflict"))
    if primary is not None and not primary.get("reopenable", True):
        caps.append((39, "evidence-url-unreachable"))
    if claim.get("requires_inference") or (directness == 0 and supporting):
        caps.append((39, "requires-inference"))
    if claim.get("confidential_address_uncertain"):
        caps.append((0, "confidential-address-safety-uncertain"))

    score = raw
    applied = []
    for cap_value, name in caps:
        if score > cap_value:
            score = cap_value
        applied.append(name)

    # Status determination
    if not evidence:
        status = "not-found"
        score = 0
    elif claim.get("confidential_address_uncertain"):
        status = "unsafe-to-publish"
    elif unresolved_conflict:
        status = "contradicted"
    elif claim.get("requires_inference") and directness == 0:
        status = "uncertain"
    elif "stale-source" in applied:
        status = "stale"
    else:
        risk_tier = claim.get("_risk_tier", "low")
        threshold = RISK_THRESHOLDS.get(risk_tier, RISK_THRESHOLDS["low"])["essential_claim_min"]
        if score >= threshold and corroboration >= 15:
            status = "verified"
        elif score >= threshold:
            status = "verified-with-limitation"
        else:
            status = "uncertain"

    return ClaimScoreResult(
        claim_id=claim["claim_id"], score=score, status=status,
        breakdown=breakdown, caps_applied=applied, incident=False,
    )


# ---------------------------------------------------------------------------
# Record-level scoring
# ---------------------------------------------------------------------------

@dataclass
class RecordScoreResult:
    record_trust_score: int
    lowest_essential_claim_score: int
    average_essential_claim_score: float
    average_material_claim_score: float
    unresolved_conflicts: int
    stale_claims: int
    corroborated_claims: int
    claim_results: dict[str, ClaimScoreResult]
    incidents: list[str]


def score_record(claims: list[dict], risk_tier: str, today: date | None = None) -> RecordScoreResult:
    today = today or date.today()
    for c in claims:
        c["_risk_tier"] = risk_tier
    results = {c["claim_id"]: score_claim(c, today) for c in claims}

    incidents = [r.claim_id for r in results.values() if r.incident]

    essential = [c for c in claims if c.get("essential")]
    material = [c for c in claims if c.get("material")]

    essential_scores = [results[c["claim_id"]].score for c in essential] or [0]
    material_scores_weighted = [
        (results[c["claim_id"]].score, c.get("weight", 1.0)) for c in material
    ]
    total_weight = sum(w for _, w in material_scores_weighted) or 1.0
    avg_material = sum(s * w for s, w in material_scores_weighted) / total_weight

    lowest_essential = min(essential_scores)
    avg_essential = sum(essential_scores) / len(essential_scores)

    record_trust = int((ESSENTIAL_WEIGHT * lowest_essential) + (MATERIAL_WEIGHT * avg_material))
    # Round down explicitly per spec ("Round down to the nearest whole number").
    record_trust = int(record_trust)

    unresolved_conflicts = sum(1 for r in results.values() if "unresolved-material-conflict" in r.caps_applied)
    stale_claims = sum(1 for r in results.values() if r.status == "stale")
    corroborated = sum(1 for r in results.values() if r.breakdown.get("independent_corroboration", 0) >= 15)

    return RecordScoreResult(
        record_trust_score=record_trust,
        lowest_essential_claim_score=lowest_essential,
        average_essential_claim_score=avg_essential,
        average_material_claim_score=avg_material,
        unresolved_conflicts=unresolved_conflicts,
        stale_claims=stale_claims,
        corroborated_claims=corroborated,
        claim_results=results,
        incidents=incidents,
    )


# ---------------------------------------------------------------------------
# Publication decision
# ---------------------------------------------------------------------------

VALID_PUBLISHABLE_STATUSES = {"verified", "verified-with-limitation", "not-applicable"}


def decide_publication(
    claims: list[dict],
    risk_tier: str,
    record: RecordScoreResult,
    privacy_pass: bool,
    duplicate_pass: bool,
    schema_pass: bool,
    geographic_pass: bool,
    verifier_distinct_from_researchers: bool,
    two_verifiers_agree: bool | None = None,
    today: date | None = None,
) -> dict:
    """Deterministic gate. Returns a decision dict (not yet signed)."""
    reasons: list[str] = []
    thresholds = RISK_THRESHOLDS[risk_tier]

    if record.incidents:
        return _decision(record, risk_tier, False, "system-pause-required",
                          [f"fabrication/manipulation suspected on claim(s): {record.incidents}"])

    if not verifier_distinct_from_researchers:
        reasons.append("verifier was also a researcher on this candidate")
    if risk_tier in ("elevated", "critical") and not two_verifiers_agree:
        reasons.append("elevated/critical risk requires two independent verifiers in unanimous agreement")

    essential_claims = [c for c in claims if c.get("essential")]
    for c in essential_claims:
        status = record.claim_results[c["claim_id"]].status
        if status not in VALID_PUBLISHABLE_STATUSES:
            reasons.append(f"essential claim '{c['claim_id']}' has status '{status}'")

    if not privacy_pass:
        reasons.append("privacy/confidential-location check failed")
    if not duplicate_pass:
        reasons.append("duplicate check failed")
    if not schema_pass:
        reasons.append("schema validation failed")
    if not geographic_pass:
        reasons.append("geographic coverage check failed")
    if record.unresolved_conflicts > 0:
        reasons.append(f"{record.unresolved_conflicts} unresolved material conflict(s)")
    if record.lowest_essential_claim_score < thresholds["essential_claim_min"]:
        reasons.append(
            f"lowest essential claim score {record.lowest_essential_claim_score} "
            f"< required {thresholds['essential_claim_min']}"
        )
    if record.record_trust_score < thresholds["record_min"]:
        reasons.append(f"record trust score {record.record_trust_score} < required {thresholds['record_min']}")

    if not privacy_pass:
        # Privacy always overrides score per spec — never merely "correction-required".
        outcome = "quarantined"
        eligibility = False
    elif reasons:
        eligibility = False
        outcome = "correction-required" if record.record_trust_score >= 40 else "quarantined"
    else:
        eligibility = True
        outcome = "publication-authorized"

    return _decision(record, risk_tier, eligibility, outcome, reasons)


def _decision(record: RecordScoreResult, risk_tier: str, eligibility: bool, outcome: str, reasons: list[str]) -> dict:
    return {
        "record_trust_score": record.record_trust_score,
        "lowest_essential_claim_score": record.lowest_essential_claim_score,
        "average_essential_claim_score": record.average_essential_claim_score,
        "average_material_claim_score": record.average_material_claim_score,
        "unresolved_conflicts": record.unresolved_conflicts,
        "stale_claims": record.stale_claims,
        "corroborated_claims": record.corroborated_claims,
        "risk_tier": risk_tier,
        "eligibility": eligibility,
        "outcome": outcome,
        "reasons": reasons,
        "policy_version": POLICY_VERSION,
    }


# ---------------------------------------------------------------------------
# Signature (tamper-evidence, not identity) — spec: "Signed publication decision"
# ---------------------------------------------------------------------------

def canonicalize(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sign_decision(candidate_id: str, claims: list[dict], decision: dict) -> str:
    """Deterministic content hash over the exact evidence/claims that produced `decision`.

    This is an integrity signature, not a cryptographic identity signature: it proves the
    decision was computed from *this exact* claim/evidence content and policy version, and
    that nothing was hand-edited afterward. CI recomputes it independently (see
    scripts/validate_candidate.py) and fails the build on any mismatch.
    """
    _DERIVED_FIELDS = {"status", "score", "score_breakdown"}
    payload = {
        "candidate_id": candidate_id,
        "claims": [
            {k: v for k, v in c.items() if not k.startswith("_") and k not in _DERIVED_FIELDS}
            for c in claims
        ],
        "decision": {k: v for k, v in decision.items() if k not in ("signed_at", "signed_by", "signature")},
    }
    return hashlib.sha256(canonicalize(payload).encode("utf-8")).hexdigest()


def verify_signature(candidate_id: str, claims: list[dict], decision: dict, signature: str) -> bool:
    recomputed = sign_decision(candidate_id, claims, decision)
    return recomputed == signature
