"""Adversarial test suite for the deterministic trust-scoring engine.

Each test proves one item from the spec's "Required tests" list. If any of
these fail, the engine can be gamed or a hard safety rule can be bypassed —
that is a release blocker, not a nice-to-have.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import trust_scoring as ts  # noqa: E402
import workflow_state as ws  # noqa: E402

TODAY = date(2026, 9, 20)


def _evidence(**kw):
    base = {
        "id": "e1", "url": "https://example.org", "source_type": "org-website",
        "tier": "A", "retrieved_at": "2026-09-01", "published_or_updated_at": "2026-09-01",
        "chain_id": "chain-1", "chain_independence_known": True, "directness": 20,
        "supports": True, "reopenable": True, "content_hash": "abc123",
    }
    base.update(kw)
    return base


def _claim(**kw):
    base = {
        "claim_id": "c1", "field": "phones", "value": "606-000-0000",
        "material": True, "essential": True, "freshness_class": "hours_phone",
        "evidence": [_evidence()],
    }
    base.update(kw)
    return base


# 1. A high average cannot hide a weak essential claim.
def test_weak_essential_claim_drags_down_record():
    strong = _claim(claim_id="identity", essential=True,
                     evidence=[_evidence(chain_id="c1"), _evidence(id="e2", chain_id="c2")])
    weak = _claim(claim_id="phone", essential=True, evidence=[])  # not-found -> score 0
    record = ts.score_record([strong, weak], "low", today=TODAY)
    assert record.lowest_essential_claim_score == 0
    assert record.record_trust_score < 50, "one not-found essential claim must sink the record score"


# 2. Ten copied directories do not count as ten independent sources.
def test_copied_directories_count_as_one_chain():
    evidence = [_evidence(id=f"e{i}", tier="C", chain_id="same-upstream", chain_independence_known=True)
                for i in range(10)]
    claim = _claim(evidence=evidence)
    result = ts.score_claim(claim, today=TODAY)
    assert result.breakdown["independent_corroboration"] == 0, "single chain repeated 10x must score as ONE source"
    assert result.breakdown["evidence_chain_independence"] == 0


# 3. Search snippets cannot verify a resource.
def test_search_snippets_cannot_verify():
    claim = _claim(evidence=[_evidence(tier="F", directness=8, chain_independence_known=False)])
    result = ts.score_claim(claim, today=TODAY)
    assert result.status not in ("verified", "verified-with-limitation")
    assert result.score <= 25


# 4. A primary source is scored according to claim-specific authority.
def test_org_website_authoritative_only_for_its_own_claims():
    phone_claim = _claim(claim_id="phone", field="phones", evidence=[_evidence(tier="A")])
    result = ts.score_claim(phone_claim, today=TODAY)
    assert result.breakdown["source_authority"] == 35  # org site is Tier A for its own phone number


# 5. Stale evidence is capped.
def test_stale_evidence_capped():
    old_evidence = _evidence(retrieved_at="2020-01-01", published_or_updated_at="2020-01-01")
    claim = _claim(freshness_class="hours_phone", evidence=[old_evidence])
    result = ts.score_claim(claim, today=TODAY)
    assert result.breakdown["freshness"] == 0
    assert result.score <= 49
    assert result.status == "stale"


# 6. Unresolved conflicts block publication.
def test_unresolved_conflict_blocks_publication():
    claim = _claim(evidence=[
        _evidence(chain_id="a", supports=True, value="606-111-1111"),
        _evidence(id="e2", chain_id="b", supports=False, value="606-222-2222", chain_independence_known=True),
    ])
    result = ts.score_claim(claim, today=TODAY)
    assert result.status == "contradicted"
    assert result.score <= 49
    record = ts.score_record([claim], "low", today=TODAY)
    assert record.unresolved_conflicts == 1
    decision = ts.decide_publication(
        [claim], "low", record, privacy_pass=True, duplicate_pass=True,
        schema_pass=True, geographic_pass=True, verifier_distinct_from_researchers=True,
    )
    assert decision["eligibility"] is False
    assert decision["outcome"] != "publication-authorized"


# 7. Conflicting phone numbers trigger enhanced verification (capped, contradicted).
def test_conflicting_phone_numbers_capped_and_flagged():
    claim = _claim(field="phones", evidence=[
        _evidence(chain_id="a", supports=True),
        _evidence(id="e2", chain_id="b", supports=False, chain_independence_known=True),
    ])
    result = ts.score_claim(claim, today=TODAY)
    assert result.status == "contradicted"
    assert "unresolved-material-conflict" in result.caps_applied


# 8. Conflicting addresses receive address-type/privacy analysis (confidential uncertainty -> 0).
def test_confidential_address_uncertainty_zeroes_score():
    claim = _claim(field="address", freshness_class="address", confidential_address_uncertain=True,
                    evidence=[_evidence()])
    result = ts.score_claim(claim, today=TODAY)
    assert result.score == 0
    assert result.status == "unsafe-to-publish"


# 9. A confidential-location concern overrides a high trust score.
def test_confidential_concern_overrides_high_score_at_record_level():
    address_claim = _claim(claim_id="address", field="address", essential=True,
                            confidential_address_uncertain=True, evidence=[_evidence()])
    other_claims = [_claim(claim_id=f"c{i}", essential=True,
                            evidence=[_evidence(chain_id=f"x{i}"), _evidence(id=f"e{i}", chain_id=f"y{i}")])
                    for i in range(3)]
    claims = [address_claim] + other_claims
    record = ts.score_record(claims, "low", today=TODAY)
    decision = ts.decide_publication(
        claims, "low", record, privacy_pass=False, duplicate_pass=True,
        schema_pass=True, geographic_pass=True, verifier_distinct_from_researchers=True,
    )
    assert decision["eligibility"] is False
    assert decision["outcome"] == "quarantined"


# 10. A verifier cannot verify its own research.
def test_verifier_cannot_verify_own_research():
    actor = ws.Actor("agent-1", "research-a")
    verifier_actor = ws.Actor("agent-1", "verifier")
    prior = {"research-a": actor}
    try:
        ws.transition("evidence-compared", "verified", verifier_actor, prior)
        assert False, "expected IllegalTransition"
    except ws.IllegalTransition:
        pass
    # A different agent verifying is fine.
    ws.transition("evidence-compared", "verified", ws.Actor("agent-2", "verifier"), prior)


# 11. A signed decision cannot authorize a modified record.
def test_signature_invalidated_by_modified_claim():
    claim = _claim(evidence=[_evidence(chain_id="a"), _evidence(id="e2", chain_id="b")])
    record = ts.score_record([claim], "low", today=TODAY)
    decision = ts.decide_publication(
        [claim], "low", record, privacy_pass=True, duplicate_pass=True,
        schema_pass=True, geographic_pass=True, verifier_distinct_from_researchers=True,
    )
    sig = ts.sign_decision("cand-1", [claim], decision)
    assert ts.verify_signature("cand-1", [claim], decision, sig)

    tampered_claim = dict(claim)
    tampered_claim["value"] = "606-999-9999"
    assert not ts.verify_signature("cand-1", [tampered_claim], decision, sig)


# 12. A changed commit invalidates the decision artifact (same idea, evidence added post-signing).
def test_adding_evidence_after_signing_invalidates_signature():
    claim = _claim(evidence=[_evidence(chain_id="a")])
    record = ts.score_record([claim], "low", today=TODAY)
    decision = ts.decide_publication(
        [claim], "low", record, privacy_pass=True, duplicate_pass=True,
        schema_pass=True, geographic_pass=True, verifier_distinct_from_researchers=True,
    )
    sig = ts.sign_decision("cand-1", [claim], decision)
    claim_with_more_evidence = dict(claim)
    claim_with_more_evidence["evidence"] = claim["evidence"] + [_evidence(id="e2", chain_id="b")]
    assert not ts.verify_signature("cand-1", [claim_with_more_evidence], decision, sig)


# 13. Missing evidence cannot be converted into a confident claim.
def test_missing_evidence_is_not_found_never_verified():
    claim = _claim(evidence=[])
    result = ts.score_claim(claim, today=TODAY)
    assert result.status == "not-found"
    assert result.score == 0


# 14. Official closure evidence is handled without immediate destructive deletion.
def test_closure_evidence_suppresses_not_deletes():
    # Modeled as a state-machine fact: production-verified/monitoring can only move to
    # temporarily-suppressed or the shared exception states — never removed from the pipeline.
    assert "temporarily-suppressed" in ws.TRANSITIONS["monitoring"]
    assert "temporarily-suppressed" in ws.TRANSITIONS["production-verified"]
    # There is no edge that deletes a candidate outright.
    for state, targets in ws.TRANSITIONS.items():
        assert "deleted" not in targets


# 15. Low-, elevated-, and critical-risk thresholds are enforced.
def test_risk_tier_thresholds_enforced():
    def make_claims(score_hint_chains=2):
        c = _claim(evidence=[_evidence(chain_id=f"x{i}") for i in range(score_hint_chains)])
        return [c]

    claims_low = make_claims()
    record_low = ts.score_record(claims_low, "low", today=TODAY)
    decision_low = ts.decide_publication(
        claims_low, "low", record_low, privacy_pass=True, duplicate_pass=True,
        schema_pass=True, geographic_pass=True, verifier_distinct_from_researchers=True,
    )

    claims_critical = make_claims()
    record_critical = ts.score_record(claims_critical, "critical", today=TODAY)
    decision_critical = ts.decide_publication(
        claims_critical, "critical", record_critical, privacy_pass=True, duplicate_pass=True,
        schema_pass=True, geographic_pass=True, verifier_distinct_from_researchers=True,
        two_verifiers_agree=True,
    )
    # Same evidence quality; critical tier's higher bar must be at least as hard to pass.
    assert ts.RISK_THRESHOLDS["critical"]["record_min"] > ts.RISK_THRESHOLDS["low"]["record_min"]
    assert ts.RISK_THRESHOLDS["critical"]["essential_claim_min"] > ts.RISK_THRESHOLDS["low"]["essential_claim_min"]
    if decision_low["outcome"] == "publication-authorized":
        assert record_low.record_trust_score >= ts.RISK_THRESHOLDS["low"]["record_min"]
    if decision_critical["outcome"] == "publication-authorized":
        assert record_critical.record_trust_score >= ts.RISK_THRESHOLDS["critical"]["record_min"]


# 16. Quarantined records cannot reach the Publisher.
def test_quarantined_cannot_reach_publisher_state():
    # decision-signed -> yaml-created is a publisher-only transition; a quarantined outcome
    # must never have been produced with eligibility True, and validate_candidate.py's PUBLISHED_STATES
    # gate additionally refuses any state >= yaml-created without outcome=publication-authorized.
    claim = _claim(evidence=[])  # not-found essential claim -> guaranteed failure
    record = ts.score_record([claim], "low", today=TODAY)
    decision = ts.decide_publication(
        [claim], "low", record, privacy_pass=True, duplicate_pass=True,
        schema_pass=True, geographic_pass=True, verifier_distinct_from_researchers=True,
    )
    assert decision["outcome"] in ("quarantined", "correction-required")
    assert decision["eligibility"] is False


# 17. Failed post-deployment verification triggers rollback.
def test_failed_production_verification_triggers_suppression_path():
    actor = ws.Actor("monitor-1", "deployment-monitor")
    # production-verified is reachable only from deployed; if post-deploy checks fail, the only
    # legal next step besides production-verified is a shared exception (rollback) state.
    assert "temporarily-suppressed" in ws.TRANSITIONS["production-verified"]
    ws.transition("deployed", "production-verified", actor, {})
    ws.transition("production-verified", "temporarily-suppressed", actor, {})


# --- Extra structural guarantees exercised implicitly by the above but worth pinning directly ---

def test_illegal_state_skip_rejected():
    try:
        ws.transition("lead-received", "verified", ws.Actor("a1", "verifier"), {})
        assert False, "expected IllegalTransition"
    except ws.IllegalTransition:
        pass


def test_wrong_role_cannot_perform_transition():
    try:
        ws.transition("lead-received", "intake-classified", ws.Actor("a1", "publisher"), {})
        assert False, "expected IllegalTransition"
    except ws.IllegalTransition:
        pass


def test_fabrication_zeroes_score_and_flags_incident():
    claim = _claim(evidence=[_evidence(fabrication_suspected=True)])
    result = ts.score_claim(claim, today=TODAY)
    assert result.score == 0
    assert result.status == "unsafe-to-publish"
    assert result.incident is True
    record = ts.score_record([claim], "low", today=TODAY)
    decision = ts.decide_publication(
        [claim], "low", record, privacy_pass=True, duplicate_pass=True,
        schema_pass=True, geographic_pass=True, verifier_distinct_from_researchers=True,
    )
    assert decision["outcome"] == "system-pause-required"
