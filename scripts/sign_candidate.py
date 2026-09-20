#!/usr/bin/env python3
"""Compute and write the decision artifact for a candidate file.

Run by the Resource Operations Director (or its automation) at the
"decision-signed" workflow step, after policy-checked/trust-scored. Never
run by the same identity that authored the claims being scored.

Usage:
    python scripts/sign_candidate.py source/candidates/<file>.yaml [--signed-by NAME]
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import trust_scoring as ts  # noqa: E402
from validate_candidate import check_privacy, check_duplicate, check_geographic  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    path = Path(sys.argv[1])
    signed_by = "resource-operations-director"
    if "--signed-by" in sys.argv:
        signed_by = sys.argv[sys.argv.index("--signed-by") + 1]

    candidate = yaml.safe_load(path.read_text())
    claims = candidate["claims"]
    risk_tier = candidate["risk_tier"]
    record = ts.score_record(claims, risk_tier)

    privacy_pass, _ = check_privacy(candidate)
    duplicate_pass, _ = check_duplicate(candidate)
    geographic_pass, _ = check_geographic(candidate)

    verification = candidate.get("verification", {})
    verifiers = verification.get("verifiers", [])
    researchers = [p["researcher"] for p in candidate.get("research_packages", [])]
    verifier_distinct = all(v not in researchers for v in verifiers)
    two_verifiers_agree = verification.get("verifier_agreement") if len(verifiers) >= 2 else None

    decision = ts.decide_publication(
        claims=claims, risk_tier=risk_tier, record=record,
        privacy_pass=privacy_pass, duplicate_pass=duplicate_pass,
        schema_pass=True, geographic_pass=geographic_pass,
        verifier_distinct_from_researchers=verifier_distinct,
        two_verifiers_agree=two_verifiers_agree,
    )
    signature = ts.sign_decision(candidate["candidate_id"], claims, decision)
    decision["signature"] = signature
    decision["signed_by"] = signed_by
    decision["signed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # strip the private "_risk_tier" scratch field score_record injects into claims
    for c in claims:
        c.pop("_risk_tier", None)
        cr = record.claim_results[c["claim_id"]]
        c["status"] = cr.status
        c["score"] = cr.score
        c["score_breakdown"] = cr.breakdown

    candidate["decision"] = decision
    path.write_text(yaml.safe_dump(candidate, sort_keys=False, allow_unicode=True))
    print(f"signed {path}: outcome={decision['outcome']} record_trust={decision['record_trust_score']} "
          f"signature={signature[:16]}...")


if __name__ == "__main__":
    main()
