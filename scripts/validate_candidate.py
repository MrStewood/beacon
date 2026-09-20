#!/usr/bin/env python3
"""CI gate for Beacon candidates.

Recomputes every score and the publication decision independently from the
committed claims/evidence and compares it byte-for-byte against the decision
artifact checked into the candidate file. Any of the following fails the
build (exit 1), which GitHub branch protection uses as a required check:

- Candidate fails schema validation.
- Recomputed decision.signature != committed decision.signature (tamper or
  stale artifact — e.g. someone hand-edited a score or evidence after
  signing, or forgot to re-run signing after an edit).
- Recomputed outcome/eligibility != committed outcome/eligibility.
- outcome == "publication-authorized" but any hard gate (privacy, duplicate,
  schema, geographic, essential-claim, conflict) fails.
- A yaml-created/pr-opened+ candidate whose outcome is not
  "publication-authorized" (quarantined candidates must never reach the
  Publisher step).

Usage:
    python scripts/validate_candidate.py source/candidates/<file>.yaml
    python scripts/validate_candidate.py --all   # every file under source/candidates/
"""

from __future__ import annotations

import sys
from pathlib import Path

import jsonschema
import yaml

REPO_ROOT = Path(__file__).parent.parent
CANDIDATE_SCHEMA_PATH = REPO_ROOT / "schema" / "candidate.schema.json"
CANDIDATES_DIR = REPO_ROOT / "source" / "candidates"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import trust_scoring as ts  # noqa: E402


PUBLISHED_STATES = {"yaml-created", "pr-opened", "ci-passed", "merged", "deployed", "production-verified", "monitoring"}


def load_schema() -> dict:
    import json
    return json.loads(CANDIDATE_SCHEMA_PATH.read_text())


def check_privacy(candidate: dict) -> tuple[bool, list[str]]:
    reasons = []
    for claim in candidate["claims"]:
        if claim.get("field") == "address" and claim.get("confidential_address_uncertain"):
            reasons.append(f"claim '{claim['claim_id']}': confidential-address safety uncertain")
    resource = candidate.get("resource", {})
    for loc in resource.get("locations", []) or []:
        if loc.get("location_type") == "confidential" and loc.get("publicly_displayed"):
            reasons.append(f"location '{loc.get('id')}' is confidential but publicly_displayed=true")
        if loc.get("location_type") == "confidential" and loc.get("latitude") is not None:
            reasons.append(f"location '{loc.get('id')}' is confidential but has been geocoded")
    return (len(reasons) == 0, reasons)


def check_duplicate(candidate: dict) -> tuple[bool, list[str]]:
    reasons = []
    for pkg in candidate.get("research_packages", []):
        if pkg.get("possible_duplicates"):
            reasons.append(f"unresolved possible duplicates flagged by {pkg['researcher']}: {pkg['possible_duplicates']}")
    return (len(reasons) == 0, reasons)


def check_geographic(candidate: dict) -> tuple[bool, list[str]]:
    resource = candidate.get("resource", {})
    reasons = []
    if resource.get("coverage_scope") in (None, "unknown") and resource.get("locations"):
        reasons.append("coverage_scope unresolved despite having location data")
    return (len(reasons) == 0, reasons)


def validate_one(path: Path) -> int:
    candidate = yaml.safe_load(path.read_text())
    schema = load_schema()

    schema_pass = True
    try:
        jsonschema.validate(candidate, schema)
    except jsonschema.ValidationError as exc:
        schema_pass = False
        print(f"[{path.name}] SCHEMA FAIL: {exc.message}")

    risk_tier = candidate["risk_tier"]
    claims = candidate["claims"]
    record = ts.score_record(claims, risk_tier)

    privacy_pass, privacy_reasons = check_privacy(candidate)
    duplicate_pass, dup_reasons = check_duplicate(candidate)
    geographic_pass, geo_reasons = check_geographic(candidate)

    verification = candidate.get("verification", {})
    verifiers = verification.get("verifiers", [])
    researchers = [p["researcher"] for p in candidate.get("research_packages", [])]
    verifier_distinct = all(v not in researchers for v in verifiers)
    two_verifiers_agree = verification.get("verifier_agreement") if len(verifiers) >= 2 else None

    decision = ts.decide_publication(
        claims=claims,
        risk_tier=risk_tier,
        record=record,
        privacy_pass=privacy_pass,
        duplicate_pass=duplicate_pass,
        schema_pass=schema_pass,
        geographic_pass=geographic_pass,
        verifier_distinct_from_researchers=verifier_distinct,
        two_verifiers_agree=two_verifiers_agree,
    )

    ok = True
    committed = candidate.get("decision")

    if not committed:
        if candidate["workflow_state"] in PUBLISHED_STATES:
            print(f"[{path.name}] FAIL: state '{candidate['workflow_state']}' requires a signed decision artifact")
            ok = False
        else:
            print(f"[{path.name}] OK (no decision yet, state={candidate['workflow_state']}): "
                  f"recomputed outcome would be '{decision['outcome']}'")
            return 0 if ok else 1

    else:
        recomputed_sig = ts.sign_decision(candidate["candidate_id"], claims, decision)
        committed_sig = committed.get("signature")
        if recomputed_sig != committed_sig:
            print(f"[{path.name}] FAIL: decision signature mismatch. "
                  f"committed={committed_sig} recomputed={recomputed_sig}. "
                  f"Candidate content changed since signing, or the artifact was hand-edited.")
            ok = False

        for field in ("outcome", "eligibility", "record_trust_score", "lowest_essential_claim_score"):
            if committed.get(field) != decision.get(field):
                print(f"[{path.name}] FAIL: committed decision.{field}={committed.get(field)!r} "
                      f"!= recomputed {decision.get(field)!r}")
                ok = False

        if committed.get("outcome") == "publication-authorized":
            if not (privacy_pass and duplicate_pass and schema_pass and geographic_pass):
                print(f"[{path.name}] FAIL: outcome is publication-authorized but a hard gate failed "
                      f"(privacy={privacy_pass} duplicate={duplicate_pass} schema={schema_pass} geo={geographic_pass})")
                ok = False
            if record.unresolved_conflicts > 0:
                print(f"[{path.name}] FAIL: outcome is publication-authorized with "
                      f"{record.unresolved_conflicts} unresolved conflict(s)")
                ok = False

        if candidate["workflow_state"] in ("pr-opened", "ci-passed", "merged", "deployed", "production-verified", "monitoring"):
            if committed.get("outcome") != "publication-authorized":
                print(f"[{path.name}] FAIL: candidate reached '{candidate['workflow_state']}' "
                      f"without outcome=publication-authorized (quarantined candidates must never reach the Publisher)")
                ok = False

    if not privacy_pass:
        print(f"[{path.name}] privacy issues: {privacy_reasons}")
    if not duplicate_pass:
        print(f"[{path.name}] duplicate issues: {dup_reasons}")
    if not geographic_pass:
        print(f"[{path.name}] geographic issues: {geo_reasons}")

    if ok:
        print(f"[{path.name}] OK: outcome={decision['outcome']} record_trust={record.record_trust_score} "
              f"lowest_essential={record.lowest_essential_claim_score}")
    return 0 if ok else 1


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    if sys.argv[1] == "--all":
        if not CANDIDATES_DIR.exists():
            print("no source/candidates/ directory yet — nothing to validate")
            sys.exit(0)
        paths = sorted(CANDIDATES_DIR.glob("**/*.yaml"))
    else:
        paths = [Path(p) for p in sys.argv[1:]]

    if not paths:
        print("no candidate files to validate")
        sys.exit(0)

    failures = 0
    for p in paths:
        failures += validate_one(p)

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
